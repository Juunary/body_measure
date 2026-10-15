"""Run the open-source comparison and write its report.

    python -m bench.compare run [--spec bullmer1600]      # every planned run; finished runs are skipped
    python -m bench.compare report [--spec bullmer1600]   # docs/<doc>.md, <doc>.json, figures/<doc>_*.png

--spec picks the roll setup of bench.instance.SPECS: roll1007 (default, the pattern PDF's plot
width) or bullmer1600 (the full working width of the Bullmer PremiumCut 1620 CV).
Runs execute one after another so no tool competes with another for the CPU.
Raw run records go to out/bench/[<folder>/]runs/ (gitignored); the report only reads them.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

from .evaluate import evaluate, marker_document
from .instance import CUTTING_ZONE_MM, DEFAULT_RULES, MODE_LABELS, MODES, ROOT, SPECS, build_spec, write_json
from .runners import RUNNERS, VERSIONS

DOCS = ROOT / 'docs'
FIGURES = DOCS / 'figures'
REPEATS = 3
SHORT_S, LONG_S, REFERENCE_S = 30, 120, 300
OVERRUN_S = 30.0          # a timed run this far past its budget did not get the machine it was given
TOOL_ORDER = ['ours', 'sparrow', 'sparrow-1w', 'deepnest', 'svgnest']
LABELS = {'ours': 'This study', 'sparrow': 'sparrow v0.2.0', 'sparrow-1w': 'sparrow v0.2.0, 1 worker',
          'deepnest': 'Deepnest v1.5.6', 'svgnest': 'SVGnest (2019)'}


def out_dir(spec):
    """Run records of one roll setup; roll1007 keeps the original out/bench/runs and failed folders."""
    return ROOT / 'out' / 'bench' / SPECS[spec]['folder']


def plan(rules=DEFAULT_RULES):
    """(tool, variant, mode, budget_s, run, kwargs). Anytime GA tools run once at the long budget;
    their short-budget result is their best-so-far at that time."""
    entries = []
    for mode in rules:
        for run in range(REPEATS):
            entries += [('ours', '', mode, SHORT_S, run, {'seed': run}),
                        ('ours', '', mode, LONG_S, run, {'seed': run}),
                        ('sparrow', '', mode, SHORT_S, run, {'seed': run}),
                        ('sparrow', '', mode, LONG_S, run, {'seed': run}),
                        ('deepnest', '', mode, LONG_S, run, {}),
                        ('svgnest', '', mode, LONG_S, run, {})]
    for run in range(REPEATS):
        entries.append(('sparrow', '1w', rules[0], LONG_S, run, {'seed': run, 'workers': 1}))
    for mode in rules:
        entries.append(('sparrow', '', mode, REFERENCE_S, 0, {'seed': 100}))
    return entries


def overran(record):
    """A timed run whose wall clock ran far past its budget: the machine slept or stalled, so the
    run is not comparable. cmd_run keeps it as a failed attempt and repeats it."""
    return record.get('wall_s', 0.0) > record['budget_s'] + OVERRUN_S


def run_id(tool, variant, mode, budget, run):
    return f"{tool}{'-' + variant if variant else ''}_{mode}_{budget}s_r{run}"


def cmd_run(args):
    inst = build_spec(args.spec)
    entries = plan(args.rules)
    runs_dir, failed_dir = out_dir(args.spec) / 'runs', out_dir(args.spec) / 'failed'
    runs_dir.mkdir(parents=True, exist_ok=True)
    for i, (tool, variant, mode, budget, run, kwargs) in enumerate(entries, 1):
        rid = run_id(tool, variant, mode, budget, run)
        path = runs_dir / f'{rid}.json'
        if path.exists():
            previous = json.loads(path.read_text(encoding='utf-8'))
            if 'error' not in previous and not overran(previous):
                continue
            if 'error' not in previous:
                previous['error'] = (f"Overrun: {previous['wall_s']:.0f} s wall clock for a {previous['budget_s']} s "
                                     'budget (machine asleep or stalled)')
                write_json(path, previous)
            failed_dir.mkdir(parents=True, exist_ok=True)       # keep the failed attempt, then retry
            attempt = len(list(failed_dir.glob(f'{rid}_attempt*.json'))) + 1
            path.replace(failed_dir / f'{rid}_attempt{attempt}.json')
        print(f'[{i}/{len(entries)}] {rid}', flush=True)
        started = time.time()
        try:
            record = RUNNERS[tool](inst, mode, budget, run, **kwargs)
        except Exception as exc:  # a failed run is recorded as a failure, never silently dropped
            record = {'tool': tool, 'version': VERSIONS[tool], 'mode': mode, 'budget_s': budget, 'run': run,
                      'error': f'{type(exc).__name__}: {exc}'}
        record.update({'id': rid, 'variant': variant, 'steady': bool(args.steady)})
        if 'error' not in record and overran(record):
            record['error'] = (f"Overrun: {record['wall_s']:.0f} s wall clock for a {budget} s budget "
                               '(machine asleep or stalled)')
        write_json(path, record)
        ev = record.get('evaluation')
        status = (f"L={ev['length_mm']} mm, {ev['efficiency_pct']} %, valid={ev['valid']}" if ev
                  else f"FAILED {record['error']}")
        print(f'    {status} ({time.time() - started:.0f} s)', flush=True)
    return 0


# ---------------------------------------------------------------- report

def load_records(runs_dir):
    return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(runs_dir.glob('*.json'))]


def tool_key(record):
    return record['tool'] + ('-' + record['variant'] if record.get('variant') else '')


def snapshot(inst, record, seconds):
    """Evaluation of an anytime run's best marker at `seconds` (None if it had none yet)."""
    if seconds >= record['budget_s'] or 'trace_placements' not in record:
        return record['evaluation']
    before = [s for s in record['trace_placements'] if s['t'] <= seconds]
    if not before:
        return None
    return evaluate(inst, {k: tuple(v) for k, v in before[-1]['placements'].items()}, record['mode'])


def summarise(inst, records, rules=DEFAULT_RULES):
    rows = []
    for mode in rules:
        for key in TOOL_ORDER:
            for budget in (SHORT_S, LONG_S, REFERENCE_S):
                group = []
                for r in records:
                    if r['mode'] != mode or tool_key(r) != key or 'error' in r:
                        continue
                    if r['budget_s'] == budget:
                        group.append((r, r['evaluation']))
                    elif budget == SHORT_S and r['budget_s'] == LONG_S and 'trace_placements' in r:
                        group.append((r, snapshot(inst, r, SHORT_S)))
                failed = [r for r in records if r['mode'] == mode and tool_key(r) == key
                          and r['budget_s'] == budget and 'error' in r]
                if not group and not failed:
                    continue
                evs = [ev for _, ev in group if ev is not None]
                valid = [ev for ev in evs if ev['valid']]
                lengths = sorted(ev['length_mm'] for ev in valid)
                rows.append({
                    'mode': mode, 'tool': key, 'label': LABELS[key], 'budget_s': budget,
                    'runs': len(group) + len(failed), 'valid_runs': len(valid),
                    'no_result_yet': sum(1 for _, ev in group if ev is None), 'failed_runs': len(failed),
                    'best_mm': lengths[0] if lengths else None,
                    'median_mm': statistics.median(lengths) if lengths else None,
                    'worst_mm': lengths[-1] if lengths else None,
                    'zone_fit_runs': sum(1 for length in lengths if length <= CUTTING_ZONE_MM),
                    'best_efficiency_pct': round(100 * inst.total_area_mm2 / (inst.fabric_width_mm * lengths[0]), 2) if lengths else None,
                    'median_efficiency_pct': round(100 * inst.total_area_mm2 / (inst.fabric_width_mm * statistics.median(lengths)), 2) if lengths else None,
                    'min_distance_mm': min((ev['min_distance_mm'] for ev in valid), default=None),
                    'workers': group[0][0]['settings'].get('workers') if group else None,
                    'evaluations_per_s': (round(statistics.mean(r['evaluations'] / r['budget_s'] for r, _ in group), 2)
                                          if group and 'evaluations' in group[0][0] else None),
                    'from_longer_run': bool(group) and group[0][0]['budget_s'] != budget,
                })
    return rows


def best_record(records, mode, key, budget):
    group = [r for r in records if r['mode'] == mode and tool_key(r) == key and r['budget_s'] == budget
             and 'error' not in r and r['evaluation']['valid']]
    return min(group, key=lambda r: r['evaluation']['length_mm']) if group else None


def cmd_report(args):
    from . import figures, report
    spec, folder = SPECS[args.spec], out_dir(args.spec)
    inst = build_spec(args.spec)
    records = load_records(folder / 'runs')
    rows = summarise(inst, records, args.rules)
    lower = inst.total_area_mm2 / (inst.fabric_width_mm - 2 * inst.margin_mm) + 2 * inst.margin_mm
    prefix = spec['doc']
    FIGURES.mkdir(parents=True, exist_ok=True)
    figures.convergence(records, lower, FIGURES / f'{prefix}_convergence.png', LABELS,
                        width_mm=inst.fabric_width_mm, zone_mm=CUTTING_ZONE_MM, rules=args.rules)
    markers = {}
    for mode in args.rules:
        chosen = []
        for key in ('ours', 'sparrow', 'deepnest', 'svgnest'):
            r = best_record(records, mode, key, LONG_S)
            if r:
                chosen.append((LABELS[key], marker_document(inst, r['evaluation'], mode, LABELS[key])))
        if chosen:
            path = FIGURES / f'{prefix}_markers_{mode}.png'
            figures.markers(chosen, path, f'Best {LONG_S} s marker per tool, {inst.fabric_width_mm:g} mm roll, '
                                          f'{MODE_LABELS[mode]}')
            markers[mode] = path.name
    summary = {'instance': {'spec': args.spec, 'roll': spec['roll'], 'fabric_width_mm': inst.fabric_width_mm,
                            'gap_mm': inst.gap_mm, 'margin_mm': inst.margin_mm, 'cutting_zone_mm': CUTTING_ZONE_MM,
                            'copies': len(inst.copies), 'piece_area_mm2': round(inst.total_area_mm2, 1),
                            'lower_bound_length_mm': round(lower, 1)},
               'runs_dir': (folder / 'runs').relative_to(ROOT).as_posix() + '/',
               'failed_dir': (folder / 'failed').relative_to(ROOT).as_posix() + '/',
               'rules': list(args.rules), 'versions': VERSIONS, 'rows': rows,
               'figures': {'convergence': f'{prefix}_convergence.png', **markers}}
    summary['failed_attempts'] = [{'id': d['id'], 'error': d['error']} for d in
                                  (json.loads(f.read_text(encoding='utf-8')) for f in sorted((folder / 'failed').glob('*.json')))]
    summary['machine'] = report.machine_info()
    # this study's beam search is deterministic, so its duration gauges the machine during the runs
    ours = [r for r in records if r['tool'] == 'ours' and 'error' not in r]
    summary['gauge'] = {'beam_s': {mode: sorted(r['stages']['beam_s'] for r in ours if r['mode'] == mode) for mode in args.rules},
                        'steady_runs': sum(1 for r in ours if r.get('steady')), 'runs': len(ours)}
    # the other setups' summaries, to set the same shirt on every roll side by side
    others = {name: json.loads((DOCS / f"{s['doc']}.json").read_text(encoding='utf-8')) for name, s in SPECS.items()
              if name != args.spec and (DOCS / f"{s['doc']}.json").exists()}
    write_json(DOCS / f'{prefix}.json', summary)
    (DOCS / f'{prefix}.md').write_text(report.render(summary, (SHORT_S, LONG_S), REFERENCE_S, others),
                                       encoding='utf-8')
    print(json.dumps(rows, indent=1))
    return 0


def steady():
    """Windows: above-normal priority and no power throttling (EcoQoS) for this process, so other
    applications or an idle-looking session do not slow the timed runs. No-op elsewhere."""
    if sys.platform != 'win32':
        return
    import ctypes
    from ctypes import wintypes

    class ThrottlingState(ctypes.Structure):
        _fields_ = [('Version', wintypes.ULONG), ('ControlMask', wintypes.ULONG), ('StateMask', wintypes.ULONG)]

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.SetProcessInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    process = kernel32.GetCurrentProcess()
    kernel32.SetPriorityClass(process, 0x00008000)                        # ABOVE_NORMAL_PRIORITY_CLASS
    state = ThrottlingState(1, 0x1, 0x0)                                  # execution speed: never throttled
    kernel32.SetProcessInformation(process, 4, ctypes.byref(state), ctypes.sizeof(state))  # ProcessPowerThrottling


def _rules(text):
    rules = tuple(t.strip() for t in text.split(',') if t.strip())
    unknown = [r for r in rules if r not in MODES]
    if not rules or unknown:
        raise argparse.ArgumentTypeError(f'grain rules are a comma list of {", ".join(MODES)}')
    return rules


def main(argv=None):
    parser = argparse.ArgumentParser(prog='bench.compare', description=__doc__)
    parser.add_argument('command', choices=('run', 'report'))
    parser.add_argument('--spec', choices=tuple(SPECS), default='roll1007', help='roll setup (bench.instance.SPECS)')
    parser.add_argument('--rules', type=_rules, default=DEFAULT_RULES,
                        help='grain rules to run or report: 2rot (default, grain along the roll) or 2rot,4rot')
    parser.add_argument('--steady', action='store_true',
                        help='Windows: above-normal priority and no power throttling for the timed runs')
    args = parser.parse_args(argv)
    if args.steady:
        steady()
    return {'run': cmd_run, 'report': cmd_report}[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
