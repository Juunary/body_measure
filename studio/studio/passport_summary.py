"""Public QR snapshots: allowlisted data only, durable and independent of jobs."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from .paths import RUNS
from app.schemas import SCHEMAS, COLOURS, COLOUR_HEX, FIBRES, FIBRE_LABELS
from app.validation import derived

DB_PATH = RUNS / 'passport-summaries.sqlite3'
VERSION = 'studio-passport-summary/2'
METRICS = ('cut_length_mm', 'yield_pct', 'collected_pieces', 'sewn_length_mm',
           'stitches', 'seams_complete', 'seams_total')


def public_resources(value):
    if value is None: return None
    result = {k: value[k] for k in ('flow_time_s', 'energy_kwh', 'co2e_g', 'cost_eur',
                                   'labour_time_s', 'thread_used_m')}
    for field, keys in {'cost_breakdown_eur': ('fabric', 'thread', 'labour', 'electricity', 'equipment'),
                        'energy_breakdown_kwh': ('zund', 'pfaff', 'vacuum', 'overhead'),
                        'fabric_used_m2': ('body', 'rib')}.items():
        result[field] = {k: value[field][k] for k in keys}
    return result


def product(config, version):
    fields = {f.key: f for f in SCHEMAS[version].fields}
    def choice(key):
        field = fields[key]
        value = config[key]
        return {'value': value, 'labels': {lang: labels[field.options.index(value)]
                                         for lang, labels in field.labels.items()}}
    return {'kind': 'polo', 'source': 'qr_configuration', 'size': config['size'].upper(),
            'colour': {**choice('colour'), 'hex': COLOUR_HEX[COLOURS.index(config['colour'])]},
            'fit': choice('fit'), 'care': choice('wash_temp'),
            'composition': [{'fibre': c['fibre'], 'percentage': c['percentage'],
                             'labels': {lang: labels[FIBRES.index(c['fibre'])] for lang, labels in FIBRE_LABELS.items()}}
                            for c in derived(config, version)['fibre_composition']],
            'recycled_content_pct': float(config['recycled_pct'])}


def configuration_only(code, version, config):
    return {'schema_version': VERSION, 'code': code, 'qr_schema_version': version,
            'recorded': False, 'generated_at': None, 'product': product(config, version),
            'process': None, 'finished_garment': False}


def build(code, version, config, job, size_source, state=None, plan=None):
    summary = configuration_only(code, version, config)
    summary.update(recorded=True, generated_at=datetime.now(timezone.utc).isoformat(timespec='microseconds'))
    stages = [{'id': 'sizing', 'status': 'complete'}, {'id': 'pattern', 'status': 'not_started'},
              {'id': 'cutting', 'status': 'not_started'}, {'id': 'sewing', 'status': 'not_started'}]
    process = {'is_simulation': True, 'source': 'studio_qr_snapshot',
               'measurement_recorded': bool(job.measurements), 'size_source': size_source,
               'scope': None, 'status': 'not_started', 'stages': stages, 'metrics': None,
               'finishing': 'not_executed', 'quality_control': 'not_executed',
               'resources': None, 'planned_resources': None, 'run_size': None, 'estimation': None}
    if state is not None and plan is not None:
        cut_done = state.get('cutting_complete', state['finished'])
        sew_done = state.get('sewing_complete', False)
        scope = plan['scope']
        stages[1]['status'] = 'complete'
        stages[2]['status'] = 'complete' if cut_done else 'in_progress' if state['sim_time_s'] > 0 else 'not_started'
        stages[3]['status'] = ('excluded' if scope == 'through_cutting' else
                               'complete' if sew_done else 'in_progress' if cut_done else 'not_started')
        metrics = {key: state['metrics'].get(key, 0) for key in METRICS}
        metrics.update(total_pieces=len(plan['pieces']), process_time_s=state['sim_time_s'],
                       planned_time_s=plan['totals']['duration_s'])
        process.update(scope=scope, status=('sewing_complete' if sew_done else 'cutting_complete' if state['finished'] else state['status']), metrics=metrics)
        process['resources'] = public_resources(state.get('resources'))
        process['planned_resources'] = public_resources(plan['totals'].get('resources'))
        size = plan.get('size')
        process['run_size'] = {k: size.get(k) for k in ('label', 'source', 'chart')} if size else None
        if plan.get('resource_model'):
            from .simulation.config import Resources
            process['estimation'] = {'model': plan['resource_model']['version'], 'is_estimate': True,
                                     'co2_scope': 'process_electricity_only', 'labour_model': 'attended_operations',
                                     'preset': {k: plan['config']['resources'][k] for k in Resources.model_fields}}
    summary['process'] = process
    return summary


def save(summary):
    payload = json.dumps(summary, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH, timeout=10)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS summaries (code TEXT PRIMARY KEY, generated_at TEXT NOT NULL, payload TEXT NOT NULL)')
        db.execute('INSERT INTO summaries VALUES (?, ?, ?) ON CONFLICT(code) DO UPDATE SET generated_at=excluded.generated_at, payload=excluded.payload WHERE excluded.generated_at >= summaries.generated_at',
                   (summary['code'], summary['generated_at'], payload))


def read(code):
    if not DB_PATH.exists(): return None
    with closing(sqlite3.connect(DB_PATH, timeout=10)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='summaries'").fetchone(): return None
        row = db.execute('SELECT payload FROM summaries WHERE code=?', (code,)).fetchone()
    return json.loads(row[0]) if row else None
