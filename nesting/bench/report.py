"""Render docs/<doc>.md from the benchmark summary; every number comes from the run records."""
import subprocess

from .instance import MODE_LABELS, MODES

TOOLS = ('ours', 'sparrow', 'deepnest', 'svgnest')


def machine_info():
    query = ('$c = Get-CimInstance Win32_Processor | Select-Object -First 1; '
             '"$($c.Name.Trim()), $($c.NumberOfCores) cores / $($c.NumberOfLogicalProcessors) threads"')
    out = subprocess.run(['powershell', '-NoProfile', '-Command', query], capture_output=True, text=True)
    return out.stdout.strip() or 'unknown'


def _rules(summary):
    """Grain rules of a summary; older summaries name none, so take them from their rows."""
    return summary.get('rules') or [m for m in MODES if any(r['mode'] == m for r in summary['rows'])]


def _mm(v):
    return '-' if v is None else f'{v:.0f}'


def _table(rows, mode, zone_mm):
    lines = ['| nester | budget | runs (valid) | best mm | median mm | worst mm | median efficiency | min gap mm | '
             f'fits one {zone_mm:g} mm zone | threads | evaluations/s |',
             '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        if r['mode'] != mode:
            continue
        budget = f"{r['budget_s']} s" + (' *' if r['from_longer_run'] else '')
        runs = f"{r['runs']} ({r['valid_runs']})"
        if r['no_result_yet']:
            runs += f", {r['no_result_yet']} without a marker yet"
        eff = '-' if r['median_efficiency_pct'] is None else f"{r['median_efficiency_pct']:.1f} %"
        gap = '-' if r['min_distance_mm'] is None else f"{r['min_distance_mm']:.2f}"
        zone = f"{r['zone_fit_runs']} of {r['valid_runs']}" if r['valid_runs'] else '-'
        evals = '-' if r['evaluations_per_s'] is None else f"{r['evaluations_per_s']:.2f}"
        lines.append(f"| {r['label']} | {budget} | {runs} | {_mm(r['best_mm'])} | {_mm(r['median_mm'])} | "
                     f"{_mm(r['worst_mm'])} | {eff} | {gap} | {zone} | {r['workers'] or '-'} | {evals} |")
    return '\n'.join(lines)


def _pick(rows, mode, tool, budget):
    return next((r for r in rows if r['mode'] == mode and r['tool'] == tool and r['budget_s'] == budget), None)


def _findings(summary, budgets, reference_s):
    rows, lower = summary['rows'], summary['instance']['lower_bound_length_mm']
    out = []
    for mode in _rules(summary):
        for budget in budgets:
            ranked = sorted((r for r in rows if r['mode'] == mode and r['budget_s'] == budget and r['median_mm']
                             and r['tool'] != 'sparrow-1w'), key=lambda r: r['median_mm'])
            if not ranked:
                continue
            order = ' < '.join(f"{r['label']} {r['median_mm']:.0f}" for r in ranked)
            line = f"- **{MODE_LABELS[mode]}, {budget} s**, median length in mm: {order}."
            ours = next((r for r in ranked if r['tool'] == 'ours'), None)
            if ours and ranked[0]['tool'] != 'ours':
                d = ours['median_mm'] - ranked[0]['median_mm']
                if d < 0.5:
                    line += f" This study ties with {ranked[0]['label']} ({d:.1f} mm apart)."
                else:
                    line += f" This study is {d:.0f} mm ({100 * d / ranked[0]['median_mm']:.1f} %) longer than {ranked[0]['label']}."
            elif ours and len(ranked) > 1:
                d = ranked[1]['median_mm'] - ours['median_mm']
                line += f" This study is {d:.0f} mm shorter than the next nester."
            out.append(line)
        ref = _pick(rows, mode, 'sparrow', reference_s)
        if ref and ref['best_mm']:
            out.append(f"- **{MODE_LABELS[mode]}, reference**: sparrow given {reference_s} s reached {ref['best_mm']:.0f} mm "
                       f"({ref['best_efficiency_pct']:.1f} %). The area lower bound is {lower:.0f} mm.")
    return '\n'.join(out)


def _zone_findings(summary):
    """Which markers need more than one conveyor window of the cutter."""
    zone, out = summary['instance']['cutting_zone_mm'], []
    for mode in _rules(summary):
        valid = [r for r in summary['rows'] if r['mode'] == mode and r['valid_runs']]
        if not valid:
            continue
        over = [r for r in valid if r['zone_fit_runs'] < r['valid_runs']]
        if over:
            listed = '; '.join(f"{r['label']} {r['budget_s']} s, {r['valid_runs'] - r['zone_fit_runs']} of "
                               f"{r['valid_runs']} runs (worst {r['worst_mm']:.0f} mm)" for r in over)
            out.append(f"- **{MODE_LABELS[mode]}, cutting zone**: longer than one {zone:g} mm window: {listed}. "
                       'Every other valid marker fits one window.')
        else:
            longest = max(r['worst_mm'] for r in valid)
            out.append(f"- **{MODE_LABELS[mode]}, cutting zone**: every valid marker fits one {zone:g} mm conveyor "
                       f"window; the longest is {longest:.0f} mm, {zone - longest:.0f} mm inside the zone.")
    return out


def _rolls(summary, others, budget):
    """The same shirt on every roll setup that has a report: median length and fabric per shirt."""
    setups = sorted([summary, *others.values()], key=lambda s: s['instance']['fabric_width_mm'])
    if len(setups) < 2:
        return []
    widths = [s['instance']['fabric_width_mm'] for s in setups]
    out = ['## The same shirt on both rolls', '',
           f'Median {budget} s marker of each setup. Fabric per shirt is roll width times marker length: what one',
           'shirt takes off the roll when it is cut on its own.', '']
    rules = [m for m in _rules(summary) if all(m in _rules(s) for s in others.values())]
    for mode in rules:
        out += [f'**{MODE_LABELS[mode]}**', '',
                '| nester | ' + ' | '.join(f'{w:g} mm roll: median mm | fabric m2' for w in widths) + ' |',
                '|---|' + '---|---|' * len(setups)]
        least = []
        for key in TOOLS:
            label = next((r['label'] for s in setups for r in s['rows'] if r['tool'] == key), key)
            cells = []
            for s in setups:
                r = _pick(s['rows'], mode, key, budget)
                cells += ([f"{r['median_mm']:.0f}", f"{s['instance']['fabric_width_mm'] * r['median_mm'] / 1e6:.2f}"]
                          if r and r['median_mm'] else ['-', '-'])
            out.append(f"| {label} | {' | '.join(cells)} |")
        for s in setups:
            m2 = [(s['instance']['fabric_width_mm'] * r['median_mm'] / 1e6, r['label']) for r in s['rows']
                  if r['mode'] == mode and r['budget_s'] == budget and r['median_mm'] and r['tool'] in TOOLS]
            if m2:
                least.append(f"{s['instance']['fabric_width_mm']:g} mm roll {min(m2)[0]:.2f} m2 ({min(m2)[1]})")
        out += ['', 'Least fabric per shirt: ' + ', '.join(least) + '.', '']
    return out


def _gauge(summary):
    gauge = summary.get('gauge')
    if not gauge or not gauge['runs']:
        return []
    parts = [f"{MODE_LABELS[mode].split(' (')[0]} {min(v):.1f}-{max(v):.1f} s" for mode, v in gauge['beam_s'].items() if v]
    lines = ["- This study's beam search is deterministic, so its duration gauges the machine during the runs: "
             + '; '.join(parts) + '.']
    if gauge['steady_runs']:
        lines.append(f"  {gauge['steady_runs']} of its {gauge['runs']} runs used `--steady` (above-normal priority, no power "
                     'throttling) because other applications were loading the machine.')
    return lines


def _failures(summary):
    failed = summary.get('failed_attempts') or []
    if not failed:
        return []
    listed = '; '.join(f"`{f['id']}` ({f['error'].split(':')[0]})" for f in failed)
    return [f'- {len(failed)} run attempt(s) failed and were repeated once: {listed}. The tables count only the',
            f"  repeated runs; the failed records are kept in `{summary.get('failed_dir', 'out/bench/failed/')}`."]


def render(summary, budgets, reference_s, others=None):
    inst, v, fig = summary['instance'], summary['versions'], summary['figures']
    zone, spec = inst['cutting_zone_mm'], inst['spec']
    if _rules(summary) == ['4rot']:
        grain = ['- Grain rule: every grain line (FDL) along or across the roll, never tilted: rotations',
                 '  0/90/180/270, the rule set for this study on 2026-10-01. 90/270 cut a piece cross-grain;',
                 '  `--rules 2rot` keeps every grain line along the roll.']
    elif _rules(summary) == ['2rot']:
        grain = ['- Grain rule: every grain line (FDL) along the roll, rotations 0/180 only. Turning a piece',
                 '  90 degrees would cut it cross-grain, so the rule does not allow it.']
    else:
        grain = ['- Grain rules: ' + '; '.join(MODE_LABELS[m] for m in _rules(summary)) + '. Rotations 90/270 cut',
                 '  a piece cross-grain.']
    turns = ' or '.join(str(len(MODES[m])) for m in _rules(summary))
    flag = '' if spec == 'roll1007' else f' --spec {spec}'
    parts = [
        f"# Open-source nesting comparison, {inst['fabric_width_mm']:g} mm roll",
        '',
        'Research benchmark for one shirt pattern (six shapes, nine copies) on one roll width. It compares this',
        "study's nester with three open-source nesters on exactly the same polygons, checked by one evaluator.",
        'It says nothing about other garments or production markers.',
        '',
        "The markers are for ITA's Bullmer PremiumCut 1620 CV (offer 0912241527), which takes rolls up to 1600 mm",
        f'wide and cuts a {zone:g} mm zone on a conveyor, so a longer marker is cut in several conveyor windows. The',
        f"roll here is {inst['fabric_width_mm']:g} mm wide, {inst['roll']}.",
        '',
        f"Generated by `python -m bench.compare report{flag}` from the run records in `{summary['runs_dir']}`; no",
        f"number below is typed by hand. Machine: {summary['machine']}.",
        '',
        '## Setup',
        '',
        f"- Roll {inst['fabric_width_mm']:g} mm wide, gap {inst['gap_mm']:g} mm between cut lines and {inst['margin_mm']:g} mm to the selvedges.",
        f"- {inst['copies']} copies with a total cut-line area of {inst['piece_area_mm2'] / 1e6:.4f} m2, so no marker can be shorter than {inst['lower_bound_length_mm']:.0f} mm.",
        f'- Cutting zone {zone:g} mm: a marker up to {zone:g} mm long, margins included, is cut in one conveyor window.',
        '- Copy 2 of every 2x piece is mirrored before nesting (single-ply left and right). The external tools cannot',
        '  mirror, so every tool receives the same pre-mirrored polygons, and this study runs with `--mirror pairs`.',
        '- Each tool packs the cut line simplified with 0.25 mm tolerance and grown back by 0.25 mm, so the packed',
        '  polygon always contains the true cut line. The evaluation uses the true cut lines only.',
        *grain,
        '- One evaluator for every tool (`bench/evaluate.py`): all nine copies exactly once, allowed rotations only,',
        f"  pairwise distance of at least {inst['gap_mm']:g} mm minus 0.1 mm, fit across the roll. Length is the extent",
        '  along the roll plus both margins.',
        '- Runs execute one at a time on the same machine. Times are wall-clock from the moment a tool has the instance.',
        '',
        '| nester | version | settings used |',
        '|---|---|---|',
        f"| This study | {v['ours']} | single copies (no pre-nested pairs), beam 16, window 4, iterated local search with "
        "restarts until the time limit, seeds 0-2, one thread |",
        f"| sparrow | {v['sparrow']} | `--min-item-separation 5`, allowed orientations per rule, seeds 0-2, default 3 separator workers, also 1 worker |",
        f"| Deepnest | {v['deepnest']} | spacing 5 mm, placement `gravity`, merge lines off, rotations {turns}, population 10, mutation 10 |",
        f"| SVGnest | {v['svgnest']} | spacing 5 mm, rotations {turns}, population 10, mutation 10, curve tolerance 0.05 mm |",
        '',
    ]
    for mode in _rules(summary):
        parts += [f'## Results: {MODE_LABELS[mode]}', '', _table(summary['rows'], mode, zone), '']
    parts += [
        '`*` Deepnest and SVGnest have no time budget of their own. Their 30 s row is the best marker of each 120 s',
        'run at 30 s, re-evaluated from the stored placements. sparrow and this study plan their search around the',
        'budget, so they ran separately at 30 s and at 120 s.',
        '',
        '## Findings',
        '',
        _findings(summary, budgets, reference_s),
        *_zone_findings(summary),
        '',
        '## Convergence',
        '',
        f"![Best marker length over time for every nester](figures/{fig['convergence']})",
        '',
        "sparrow's curve uses the strip widths it logs. They are measured on the packed polygons and sit up to 1 mm",
        'above the evaluated length. The other curves are evaluated lengths.',
        '',
        '## Best markers',
        '',
    ]
    for mode in _rules(summary):
        if mode in fig:
            parts += [f"![Best marker of every nester, {MODE_LABELS[mode]}](figures/{fig[mode]})", '']
    parts += _rolls(summary, others or {}, budgets[-1])
    parts += [
        '## Caveats',
        '',
        '- Three runs per setting show the spread, not a statistical test.',
        '- The runs used a laptop with other applications open. Wall-clock times include whatever else the',
        '  machine was doing, which affects every tool alike only on average.',
        *_failures(summary),
        *_gauge(summary),
        '- Threads differ. This study and Deepnest use one worker, sparrow uses three separator workers by default',
        '  (the 1-worker rows isolate that), and SVGnest spreads its no-fit-polygon work over web workers.',
        '- Deepnest 1.5.6 evaluates one individual at a time whatever `threads` says, and it does not shrink the',
        '  sheet by half the spacing. The sheet is therefore given as roll width minus the gap.',
        '- SVGnest and Deepnest were set up for strip packing (gravity placement, no merged cut lines). Their',
        '  defaults target sheet nesting and laser cutting time and would score worse on this objective.',
        '',
        '## Reproduce',
        '',
        '```powershell',
        r'.\.venv\Scripts\python -m pip install -r bench\requirements.txt',
        r'.\.venv\Scripts\python -m bench.fetch_tools',
        r'.\.venv\Scripts\python -m nesting import examples\schnittteile-hemd.pdf -o out\pieces.json',
        r'.\.venv\Scripts\python -m bench.compare run' + flag,
        r'.\.venv\Scripts\python -m bench.compare report' + flag,
        '```',
        '',
        '`bench.fetch_tools` pins SVGnest to its last commit, downloads the Deepnest 1.5.6 Windows release (SHA-256',
        'checked) and builds sparrow v0.2.0 with a Rust toolchain installed under `.bench/rust`. Chrome runs SVGnest',
        'headless. Deepnest opens its own window while it works.',
        '',
    ]
    return '\n'.join(parts)
