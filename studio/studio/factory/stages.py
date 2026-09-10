"""Post-sewing stages: steam finishing and vision QC, ending before the DPP label.

Timings, rated power and attended fractions follow the earlier analytical line
model (polo-line-sim/polo_line/spec.py, itself derived from the Maß-DPP plan's
Table 4 and the Seite 38 flow). Every number here is a research assumption:
the plan states 6 minutes of finishing and gives QC no time of its own.
"""

# Ordered chain after `sewing_complete`. Each step holds the stage machine;
# attended steps also hold one worker from the stage's worker pool. The
# machine stays assigned across steps, exactly like a cutter between segments.
STAGES = (
    {'name': 'finishing', 'machine_pool': 'veit', 'worker_pool': 'finishing_workers',
     'queue': 'finish_queue', 'worker_wait': 'finishing_worker_wait', 'status': 'finishing',
     'complete_event': 'finishing_complete', 'count_column': 'pressed',
     'steps': (('press_load', True, 'load_s'), ('press_cycle', False, 'cycle_s'), ('press_unload', True, 'unload_s'))},
    {'name': 'qc', 'machine_pool': 'qc', 'worker_pool': 'qc_workers',
     'queue': 'qc_queue', 'worker_wait': 'qc_worker_wait', 'status': 'inspecting',
     'complete_event': 'qc_complete', 'count_column': 'inspected',
     'steps': (('qc_load', True, 'load_s'), ('qc_scan', False, 'scan_s'), ('qc_release', True, 'release_s'))},
)

STAGE_POOLS = ('veit', 'qc', 'finishing_workers', 'qc_workers')
QC_VERDICT_MODEL = 'deterministic_pass_no_defect_model'


def stage_plan(scenario):
    """Expand the scenario's stage parameters into timed steps (seconds)."""
    if scenario.get('scope') != 'through_qc': return []
    result = []
    for stage in STAGES:
        params = scenario['stages'][stage['name']]
        steps = [{'index': i, 'name': name, 'attended': attended, 'duration_s': params[key]}
                 for i, (name, attended, key) in enumerate(stage['steps'])]
        result.append({**{k: v for k, v in stage.items() if k != 'steps'}, 'steps': steps,
                       'duration_s': sum(s['duration_s'] for s in steps)})
    return result


def stage_rates(scenario):
    """Flatten stage power and equipment rates next to the shared resource rates."""
    rates = dict(scenario['config']['resources'])
    for stage in STAGES:
        params = (scenario.get('stages') or {}).get(stage['name'])
        pool = stage['machine_pool']
        rates[pool+'_active_kw'] = params['active_kw'] if params else 0.
        rates[pool+'_idle_kw'] = params['idle_kw'] if params else 0.
        rates[pool+'_eur_h'] = params['equipment_eur_h'] if params else 0.
    return rates


def press_temp_c(p):
    """Veit finisher temperature curve: warm-up, hold, cooling (legacy spec)."""
    if p < .25: return 25+(164-25)*(p/.25)
    if p < .8: return 164.
    return 164-(164-70)*((p-.8)/.2)


def press_bar(p):
    if p < .2: return 4.8*(p/.2)
    if p < .8: return 4.8
    return 4.8*(1-(p-.8)/.2)


def press_humidity_pct(p):
    return 45+40*(p/.5) if p < .5 else 85-55*((p-.5)/.5)


QC_FRAMES = 96


def readouts(station, step, progress):
    """Display values for one active step; never inputs to the accounting."""
    p = min(1., max(0., progress))
    if station == 'veit':
        if step == 'press_cycle':
            return {'press_temp_c': press_temp_c(p), 'steam_bar': press_bar(p), 'humidity_pct': press_humidity_pct(p)}
        return {'press_temp_c': 25. if step == 'press_load' else 70., 'steam_bar': 0., 'humidity_pct': 45.}
    if step == 'qc_scan':
        return {'frames': int(QC_FRAMES*p), 'verdict': 'scanning'}
    return {'frames': 0 if step == 'qc_load' else QC_FRAMES, 'verdict': 'waiting' if step == 'qc_load' else 'pass'}
