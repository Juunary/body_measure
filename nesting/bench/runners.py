"""Run one nester once on the benchmark instance and return a run record.

Every runner returns the same record: tool, version, mode, time budget, the
settings used, a convergence trace [[seconds, length_mm], ...] of the tool's
own best-so-far marker, the final placements in the tool frame, and the
common evaluation from bench.evaluate. Wall-clock time counts everything the
tool does after it has the instance (its NFP or collision set-up included).
"""
from functools import partial
import http.server
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time

from nesting.search import Settings, nest

from . import fetch_tools
from .cdp import Page, Process, free_port
from .evaluate import evaluate, length_only
from .instance import MODES, SPECS, deepnest_svgs, sparrow_json, svgnest_svg, write_json

BENCH = Path(__file__).resolve().parent
CHROME = Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
SVGNEST_DIR = fetch_tools.TOOLS / 'SVGnest'
DEEPNEST_EXE = fetch_tools.TOOLS / 'deepnest' / 'deepnest.exe'
SPARROW_EXE = fetch_tools.TOOLS / 'sparrow' / 'target' / 'release' / 'sparrow.exe'
WORK = fetch_tools.BENCH / 'work'
BIN_LENGTH_MM = 3000.0
PT_PER_MM = 72.0 / 25.4
VERSIONS = {
    'svgnest': f"SVGnest {fetch_tools.SVGNEST['commit'][:7]} (2019, last commit)",
    'deepnest': f"Deepnest {fetch_tools.DEEPNEST['version']} (deepnest-next release)",
    'sparrow': f"sparrow {fetch_tools.SPARROW['tag']} ({fetch_tools.SPARROW['commit']})",
    'ours': 'this study (nesting/)',
}
BROWSER_FLAGS = ['--disable-background-timer-throttling', '--disable-renderer-backgrounding',
                 '--disable-backgrounding-occluded-windows', '--no-first-run', '--no-default-browser-check']


def _rot(v, degrees):
    a = math.radians(degrees)
    return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a))


def _work(inst):
    """Scratch folder of the instance's roll setup, so two setups never share tool files."""
    return WORK / SPECS[inst.spec]['folder']


def _remove_profile(profile, attempts=10):
    """Delete a temporary browser profile; files stay locked for a moment after the process tree dies."""
    for _ in range(attempts):
        shutil.rmtree(profile, ignore_errors=True)
        if not profile.exists():
            return
        time.sleep(1.0)


def _snapshots(snapshots):
    """Every new best of an anytime tool, so a shorter budget can be evaluated from a longer run."""
    return [{'t': round(t, 3), 'placements': {k: list(v) for k, v in pl.items()}} for t, pl in snapshots]


def _record(tool, inst, mode, budget_s, run, settings, trace, placements, wall_s, extra=None):
    evaluation = evaluate(inst, placements, mode)
    return {'tool': tool, 'version': VERSIONS[tool], 'mode': mode, 'budget_s': budget_s, 'run': run,
            'settings': settings, 'wall_s': round(wall_s, 2), 'trace': trace,
            'final_placements': {k: list(v) for k, v in placements.items()}, 'evaluation': evaluation,
            **(extra or {})}


# ---------------------------------------------------------------- SVGnest

class _Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path.split('?')[0] == '/__harness__.html':
            return str(BENCH / 'svgnest_harness.html')
        return super().translate_path(path)

    def log_message(self, *args):
        pass


_TRANSFORM = re.compile(r'translate\(\s*([-0-9.eE]+)[ ,]+([-0-9.eE]+)\s*\)\s*rotate\(\s*([-0-9.eE]+)\s*\)')


def _svgnest_placements(entry, offsets):
    out = {}
    for p in entry['placements']:
        if p['bin'] != 0:
            raise RuntimeError('SVGnest opened a second bin')
        x, y, r = (float(v) for v in _TRANSFORM.search(p['transform']).groups())
        dx, dy = _rot(offsets[p['id']], r)
        out[p['id']] = (r, x + dx, y + dy)
    return out


def run_svgnest(inst, mode, budget_s, run=0):
    svg, offsets = svgnest_svg(inst, BIN_LENGTH_MM)
    cfg = {'spacing': inst.gap_mm, 'rotations': len(MODES[mode]), 'curveTolerance': 0.05,
           'populationSize': 10, 'mutationRate': 10, 'useHoles': False, 'exploreConcave': False}
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), partial(_Handler, directory=str(SVGNEST_DIR)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = Path(tempfile.mkdtemp(prefix='svgnest-chrome-'))
    proc = Process(CHROME, ['--headless=new', f'--user-data-dir={profile}', '--disable-extensions', *BROWSER_FLAGS,
                            'about:blank'], free_port())
    page = None
    try:
        page = Page(proc.wait_target(lambda t: True, 60))
        page.send('Page.enable')
        page.send('Page.navigate', {'url': f'http://127.0.0.1:{server.server_address[1]}/__harness__.html'})
        page.wait_for('window.harnessReady === true && typeof SvgNest === "object"', 60)
        t0 = time.perf_counter()
        result = page.evaluate(f'runNest({json.dumps(svg)}, {json.dumps(cfg)}, {budget_s})',
                               await_promise=True, timeout=budget_s + 180)
        wall = time.perf_counter() - t0
    finally:
        if page:
            page.close()
        proc.close()
        server.shutdown()
        _remove_profile(profile)
    if not result['trace']:
        raise RuntimeError('SVGnest produced no placement within the budget')
    snapshots = [(e['t'], _svgnest_placements(e, offsets)) for e in result['trace']]
    trace = [[round(t, 3), round(length_only(inst, pl), 2)] for t, pl in snapshots]
    settings = {**cfg, 'bin_length_mm': BIN_LENGTH_MM, 'workers': result.get('hardwareConcurrency')}
    return _record('svgnest', inst, mode, budget_s, run, settings, trace, snapshots[-1][1], wall,
                   {'evaluations': result['evaluations'], 'trace_placements': _snapshots(snapshots)})


# ---------------------------------------------------------------- Deepnest

DEEPNEST_JS = r"""
window.__benchRun = function (partsSvg, sheetSvg, cfg, seconds) {
  return new Promise(function (resolve, reject) {
    try {
      var ipc = require('electron').ipcRenderer, DN = window.DeepNest;
      DN.importsvg('bench-parts.svg', null, partsSvg, 1, false);
      var sheet = DN.importsvg(null, null, sheetSvg, 1, false)[0];
      sheet.sheet = true; sheet.quantity = 1;
      DN.config(cfg);
      var meta = DN.parts.map(function (p, i) {
        var el = p.svgelements && p.svgelements[0];
        return {index: i, id: el && el.getAttribute ? el.getAttribute('id') : null,
                sheet: !!p.sheet, quantity: p.quantity, bounds: p.bounds};
      });
      var evaluations = 0;
      ipc.on('background-response', function () { evaluations++; });
      var t0 = performance.now(), trace = [];
      DN.start(null, function () {
        var n = DN.nests[0];
        trace.push({t: (performance.now() - t0) / 1000, evaluations: evaluations,
                    fitness: n.fitness, placements: JSON.parse(JSON.stringify(n.placements))});
      });
      setTimeout(function () {
        ipc.send('background-stop'); DN.stop();
        resolve({meta: meta, trace: trace, evaluations: evaluations, seconds: (performance.now() - t0) / 1000});
      }, seconds * 1000);
    } catch (e) { reject(String((e && e.stack) || e)); }
  });
};
true;
"""


def _deepnest_frame(inst, meta, offsets):
    """Part index -> (copy key, layout offset in mm). The import is a pure scaling by
    PT_PER_MM; each part's bounds are checked against that before the run is trusted."""
    frame = {}
    for m in meta:
        if m['sheet']:
            continue
        c, (dx, dy) = inst.copy(m['id']), offsets[m['id']]
        bx, by = m['bounds']['x'] / PT_PER_MM, m['bounds']['y'] / PT_PER_MM
        if abs(bx - (c.tool_bounds[0] + dx)) > 0.5 or abs(by - (c.tool_bounds[1] + dy)) > 0.5:
            raise RuntimeError(f"{m['id']}: Deepnest imported the part away from its SVG position")
        frame[m['index']] = (m['id'], dx, dy)
    return frame


def _deepnest_placements(entry, frame):
    if len(entry['placements']) != 1:
        raise RuntimeError(f"Deepnest used {len(entry['placements'])} sheets")
    out = {}
    for p in entry['placements'][0]['sheetplacements']:
        key, dx, dy = frame[p['source']]
        r = float(p['rotation'])
        rx, ry = _rot((dx, dy), r)
        out[key] = (r, p['x'] / PT_PER_MM + rx, p['y'] / PT_PER_MM + ry)
    return out


def run_deepnest(inst, mode, budget_s, run=0):
    parts_svg, sheet_svg, offsets, sheet_h = deepnest_svgs(inst, BIN_LENGTH_MM, PT_PER_MM)
    cfg = {'spacing': inst.gap_mm * PT_PER_MM, 'rotations': len(MODES[mode]), 'populationSize': 10,
           'mutationRate': 10, 'threads': 4, 'placementType': 'gravity', 'mergeLines': False,
           'timeRatio': 0.5, 'simplify': False, 'curveTolerance': 0.72, 'scale': 72}
    profile = Path(tempfile.mkdtemp(prefix='deepnest-profile-'))
    _work(inst).mkdir(parents=True, exist_ok=True)
    log_path = _work(inst) / f'deepnest_{mode}_{budget_s}_{run}.log'
    launched = time.perf_counter()
    proc = Process(DEEPNEST_EXE, [f'--user-data-dir={profile}', *BROWSER_FLAGS], free_port(),
                   cwd=DEEPNEST_EXE.parent, log_path=log_path)
    page = None
    try:
        page = Page(proc.wait_target(lambda t: t['url'].endswith('index.html'), 120))
        page.wait_for('!!(window.DeepNest && window.config && document.querySelector("#startnest"))', 120)
        background = Page(proc.wait_target(lambda t: 'background.html' in t['url'], 120))
        background.wait_for('document.readyState === "complete"', 120)
        background.close()
        time.sleep(2.0)
        page.evaluate(DEEPNEST_JS)
        startup_s = time.perf_counter() - launched
        t0 = time.perf_counter()
        result = page.evaluate(f'__benchRun({json.dumps(parts_svg)}, {json.dumps(sheet_svg)}, {json.dumps(cfg)}, {budget_s})',
                               await_promise=True, timeout=budget_s + 180)
        wall = time.perf_counter() - t0
    finally:
        if page:
            page.close()
        proc.close()
        _remove_profile(profile)
    if not result['trace']:
        raise RuntimeError('Deepnest produced no placement within the budget')
    frame = _deepnest_frame(inst, result['meta'], offsets)
    snapshots = [(e['t'], _deepnest_placements(e, frame)) for e in result['trace']]
    trace = [[round(t, 3), round(length_only(inst, pl), 2)] for t, pl in snapshots]
    settings = {**cfg, 'sheet_mm': [BIN_LENGTH_MM, sheet_h], 'units_per_mm': round(PT_PER_MM, 5),
                'workers': 1}
    return _record('deepnest', inst, mode, budget_s, run, settings, trace, snapshots[-1][1], wall,
                   {'evaluations': result['evaluations'], 'trace_placements': _snapshots(snapshots),
                    'startup_s': round(startup_s, 1)})


# ---------------------------------------------------------------- sparrow

_SPARROW_WIDTH = [re.compile(r'feasible solution found! \(width: ([0-9.]+)'),
                  re.compile(r'\[CMPR\] success at [0-9.]+% \(([0-9.]+) \|')]


def run_sparrow(inst, mode, budget_s, run=0, seed=0, workers=None):
    name = f'hemd_{mode}'
    work = _work(inst) / f'sparrow_{mode}_{budget_s}_{run}_{workers or "default"}'
    if work.exists():
        shutil.rmtree(work)
    write_json(work / 'instance.json', sparrow_json(inst, mode, name))
    args = [str(SPARROW_EXE), '-i', 'instance.json', '-t', str(int(budget_s)), '-s', str(seed),
            '--min-item-separation', f'{inst.gap_mm:g}']
    if workers:
        args += ['--workers', str(workers)]
    t0 = time.perf_counter()
    proc = subprocess.Popen(args, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace')
    trace, log = [], []
    for line in proc.stdout:
        t = time.perf_counter() - t0
        log.append(line.rstrip())
        for pattern in _SPARROW_WIDTH:
            m = pattern.search(line)
            if m:
                trace.append([round(t, 3), float(m.group(1))])
    proc.wait()
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError('sparrow failed:\n' + '\n'.join(log[-20:]))
    output = json.loads((work / 'output' / f'final_{name}.json').read_text(encoding='utf-8'))
    placed = output['solution']['layout']['placed_items']
    final = {}
    for p in placed:
        tf = p['transformation']
        final[inst.copies[int(p['item_id'])].key] = (float(tf['rotation']), float(tf['translation'][0]),  # degrees
                                                     float(tf['translation'][1]))
    # the log reports strip widths of the packed (conservative) polygons: within 1 mm of the evaluated length
    record = _record('sparrow', inst, mode, budget_s, run,
                     {'min_item_separation': inst.gap_mm, 'seed': seed, 'workers': workers or 3,
                      'allowed_orientations': list(MODES[mode])}, trace, final, wall,
                     {'strip_width_reported': output['solution'].get('strip_width'),
                      'log_tail': log[-8:]})
    return record


# ---------------------------------------------------------------- this study

def run_ours(inst, mode, budget_s, run=0, seed=0, iterations=10 ** 9):
    pieces = list(inst.pieces.values())
    pieces.sort(key=lambda p: (-p.area_mm2, p.id))
    settings = Settings(fabric_width_mm=inst.fabric_width_mm, gap_mm=inst.gap_mm, edge_margin_mm=inst.margin_mm,
                        rotations=MODES[mode], mirror='pairs', beam=16, window=4, iterations=iterations,
                        seed=seed, time_limit_s=float(budget_s))
    trace = []
    t0 = time.perf_counter()
    result = nest(pieces, settings, on_improve=lambda t, length: trace.append([round(t, 3), round(length, 2)]))
    wall = time.perf_counter() - t0
    final = {f"{p['piece_id']}-{p['copy']}": (p['rotation_deg'], p['y_mm'], inst.fabric_width_mm - p['x_mm'])
             for p in result['placements']}
    return _record('ours', inst, mode, budget_s, run, {**settings.to_dict(), 'workers': 1}, trace, final, wall,
                   {'stages': result['stages'], 'time_limit_hit': result['totals']['time_limit_hit']})


RUNNERS = {'svgnest': run_svgnest, 'deepnest': run_deepnest, 'sparrow': run_sparrow, 'ours': run_ours}
