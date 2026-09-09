"""Consumer snapshots: real progress, durable replacement, and public boundaries."""
import copy
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from studio import passport_doc, passport_summary, sizing_map
from studio.jobs import Job
from studio.server import app
from studio.simulation import build_plan
from studio.simulation.playback import Playback
from app import codec, validation
from app.schemas import SCHEMAS

client = TestClient(app)


@pytest.fixture(scope='module')
def plans():
    config = json.loads((Path(__file__).parents[1] / 'examples/cutting-config.json').read_text())
    return {scope: build_plan({'sizing': {'override': {'size': 'm'}}}, {**config, 'scope': scope})
            for scope in ('through_cutting', 'through_sewing')}


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setattr(passport_doc, 'RUNS', tmp_path)
    result = Job('passport-test', {}, {})
    sizing_map.set_override(result, 'm', 'PRIVATE override reason')
    result.measurements = {'chest_circumference': {'value': 987.654, 'private': 'PRIVATE scan'}}
    result.document_path = 'C:/PRIVATE/body/measurement.json'
    result.prototypes = {'PRIVATE': {'coordinates': [1, 2, 3]}}
    return result


def generate(job):
    result = passport_doc.build(job, passport_doc.default_config(), 'http://testserver')
    response = client.get(f"/api/passports/{result['code']}/summary")
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def stages(summary):
    return {s['id']: s['status'] for s in summary['process']['stages']}


def test_unrun_snapshot_has_no_invented_production(job):
    summary = generate(job)
    assert summary['product']['size'] == 'M'
    assert summary['product']['care']['value'] == '40'
    assert summary['recorded'] and summary['generated_at']
    assert stages(summary) == dict(sizing='complete', pattern='not_started', cutting='not_started', sewing='not_started')
    assert summary['process']['metrics'] is None
    assert summary['process']['size_source'] == 'manual_override'
    assert summary['process']['measurement_recorded']
    assert not summary['finished_garment']
    assert summary['process']['finishing'] == summary['process']['quality_control'] == 'not_executed'


@pytest.mark.parametrize('scope,position,cutting,sewing', [
    ('through_sewing', 'zero', 'not_started', 'not_started'),
    ('through_sewing', 'cut', 'in_progress', 'not_started'),
    ('through_cutting', 'end', 'complete', 'excluded'),
    ('through_sewing', 'sew', 'complete', 'in_progress'),
    ('through_sewing', 'end', 'complete', 'complete'),
])
def test_captured_process_states_and_metrics(job, plans, scope, position, cutting, sewing):
    plan = plans[scope]
    if position in ('cut', 'sew'):
        op = next(o for o in plan['operations'] if o['kind'] == ('cut_outer' if position == 'cut' else 'stitch'))
        time = (op['start_s'] + op['end_s']) / 2
    else:
        time = 0 if position == 'zero' else plan['totals']['duration_s']
    job.simulation = Playback(plan, clock=lambda: 0)
    state = job.simulation.control('seek', time)
    summary = generate(job)
    assert stages(summary) == dict(sizing='complete', pattern='complete', cutting=cutting, sewing=sewing)
    metrics = summary['process']['metrics']
    for key in passport_summary.METRICS:
        assert metrics[key] == state['metrics'][key]
    assert metrics['process_time_s'] == time
    assert metrics['planned_time_s'] == plan['totals']['duration_s']
    assert metrics['total_pieces'] == len(plan['pieces'])
    assert summary['process']['is_simulation'] and not summary['finished_garment']
    assert summary['process']['finishing'] == summary['process']['quality_control'] == 'not_executed'


def test_snapshot_is_frozen_until_regeneration_and_survives_new_process(job, plans):
    job.simulation = Playback(plans['through_sewing'], clock=lambda: 0)
    first = generate(job)
    job.simulation.control('seek', job.simulation.plan['totals']['duration_s'])
    assert client.get(f"/api/passports/{first['code']}/summary").json() == first
    latest = generate(job)
    assert latest['code'] == first['code']
    assert latest['generated_at'] > first['generated_at']
    assert stages(latest)['sewing'] == 'complete'
    # A delayed older writer cannot regress a newer capture.
    passport_summary.save(first)
    assert passport_summary.read(latest['code']) == latest
    script = ('import sys,json; from pathlib import Path; from studio import passport_summary as p; '
              'p.DB_PATH=Path(sys.argv[1]); print(json.dumps(p.read(sys.argv[2])))')
    fresh = subprocess.run([sys.executable, '-c', script, str(passport_summary.DB_PATH), latest['code']],
                           cwd=Path(__file__).parents[1], capture_output=True, text=True, check=True)
    assert json.loads(fresh.stdout) == latest


def test_public_allowlist_excludes_private_data_and_geometry(job, plans):
    job.simulation = Playback(plans['through_sewing'], clock=lambda: 0)
    summary = generate(job)
    encoded = json.dumps(summary)
    for forbidden in ('PRIVATE', '987.654', 'customer_spec', 'document_path', 'measurement.json',
                      'chest_circumference', 'prototypes', 'contour', 'coordinates',
                      'head_mm', 'plan_id', 'job_id', 'machine_id', 'production_date',
                      'manufacturing_data', 'events', 'warranty'):
        assert forbidden not in encoded
    # Only these public top-level fields can reach the page and JSON download.
    assert set(summary) == {'schema_version', 'code', 'qr_schema_version', 'recorded',
                            'generated_at', 'product', 'process', 'finished_garment'}


def test_old_url_and_unrecorded_codes_use_configuration_only():
    url = '/c/xxxxxxxxxxxxxxxxxxx2AAADwAUEA'
    response = client.get(url, follow_redirects=False)
    assert response.status_code == 302 and response.headers['location'] == '/view/2AAADwAUEA'
    html = client.get(response.headers['location']).text
    assert '/static/passport.js' in html and '/static/passport.css' in html
    assert 'dppview' not in html and 'three' not in html.lower()
    summary = client.get('/api/passports/2AAADwAUEA/summary').json()
    assert not summary['recorded'] and summary['generated_at'] is None and summary['process'] is None
    assert summary['product']['kind'] == 'polo'
    assert not passport_summary.DB_PATH.exists()  # A scan does not invent a record.


@pytest.mark.parametrize('version', SCHEMAS)
def test_each_qr_schema_decodes_without_a_stored_record(version):
    config = {field.key: field.options[0] for field in SCHEMAS[version].fields}
    config['fibre_primary_pct' if version == '1' else 'fibre_1_pct'] = '100'
    validation.validate(config, version)
    code = codec.encode(config, version)
    response = client.get(f'/api/passports/{code}/summary')
    assert response.status_code == 200
    summary = response.json()
    assert summary['qr_schema_version'] == version
    assert sum(f['percentage'] for f in summary['product']['composition']) == 100
    assert all(set(f['labels']) == {'en', 'de', 'ko'} for f in summary['product']['composition'])


def test_invalid_codes_and_failed_save_do_not_publish(job, monkeypatch):
    assert client.get('/api/passports/not-valid/summary').status_code == 404
    monkeypatch.setattr(passport_doc, 'STORE', {})
    def fail(_):
        raise sqlite3.OperationalError('disk full')
    monkeypatch.setattr(passport_summary, 'save', fail)
    with pytest.raises(passport_doc.PassportError, match='could not save'):
        generate(job)
    assert not passport_doc.STORE and not job.passport


def test_http_generation_refuses_changing_inputs_but_allows_playback(job, plans, monkeypatch):
    from types import SimpleNamespace
    from studio import server
    monkeypatch.setattr(server, '_job', lambda _: job)
    job.worker = SimpleNamespace(is_alive=lambda: True)
    request = {'config': passport_doc.default_config(), 'base_url': 'http://testserver'}
    assert client.post(f'/api/jobs/{job.id}/passport', json=request).status_code == 409
    assert not passport_summary.DB_PATH.exists()
    job.worker = None
    job.simulation = Playback(plans['through_sewing'], clock=lambda: 0)
    job.simulation.control('play')
    response = client.post(f'/api/jobs/{job.id}/passport', json=request)
    assert response.status_code == 200
    assert passport_summary.read(response.json()['code'])['process']['status'] == 'playing'


def test_parallel_saves_never_mix_product_and_process(job):
    from concurrent.futures import ThreadPoolExecutor
    first = generate(job)
    variants = []
    for index in range(8):
        record = copy.deepcopy(first)
        record['generated_at'] = f'2026-09-09T12:00:0{index}+00:00'
        record['process']['metrics'] = {'marker': index}
        variants.append(record)
    # Start from a clean DB so the fixed timestamps above are ordered locally.
    passport_summary.DB_PATH.unlink()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(passport_summary.save, reversed(variants)))
    assert passport_summary.read(first['code']) == variants[-1]
