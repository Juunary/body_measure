"""Operation integration, sensitivity, historical absence and shared outputs."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import pytest
from studio.simulation import build_plan, snapshot
from studio.simulation.config import SimulationConfig
from studio.simulation.playback import Playback, terminal_lines
from studio.simulation.resources import ATTENDED
from studio import passport_doc, passport_summary, sizing_map
from studio.jobs import Job


@pytest.fixture(scope='module')
def config():
    return json.loads((Path(__file__).parents[1]/'examples/cutting-config.json').read_text())


@pytest.fixture(scope='module')
def plan(config):
    return build_plan({'sizing': {'override': {'size': 'm'}}}, config)


def test_material_purchase_and_direct_labour_boundaries(plan):
    load = plan['operations'][0]
    assert load['kind'] == 'load'
    half = snapshot(plan, load['end_s']/2)['resources']
    end = snapshot(plan, load['end_s'])['resources']
    window = plan['windows'][0]
    assert half['cost_breakdown_eur']['fabric'] == 0
    assert end['cost_breakdown_eur']['fabric'] == pytest.approx(window['width_mm']*window['length_mm']/1e6*5)
    assert half['labour_time_s'] == load['end_s']/2
    # During loading only standby and common load are powered: no vacuum, no Pfaff.
    assert end['energy_kwh'] == pytest.approx((.1+.3)*load['end_s']/3600)
    automatic = next(o for o in plan['operations'] if o['kind'] == 'cut_outer')
    before = snapshot(plan, automatic['start_s'])['resources']
    after = snapshot(plan, automatic['end_s'])['resources']
    assert after['labour_time_s'] == before['labour_time_s']
    assert after['energy_kwh']-before['energy_kwh'] == pytest.approx(2.1*(automatic['end_s']-automatic['start_s'])/3600)


def test_totals_are_sum_of_actual_occupancy_and_materials(plan):
    end = snapshot(plan, plan['totals']['duration_s'])['resources']
    assert end == plan['totals']['resources']
    assert end['cost_eur'] == sum(end['cost_breakdown_eur'].values())
    assert end['energy_kwh'] == sum(end['energy_breakdown_kwh'].values())
    assert end['co2e_g'] == pytest.approx(end['energy_kwh']*380)
    direct = sum(o['end_s']-o['start_s'] for o in plan['operations'] if o['kind'] in ATTENDED)
    assert end['labour_time_s'] == pytest.approx(direct)
    assert 0 < direct < end['flow_time_s']
    assert end['cost_breakdown_eur']['labour'] == pytest.approx(direct/3600*22)
    assert end['thread_used_m'] == pytest.approx(plan['totals']['sewn_length_mm']/1000*3 + len(plan['sewing_seams'])*.1)
    assert end['cost_breakdown_eur']['equipment'] == pytest.approx((plan['totals']['cutting_duration_s']*6 + plan['totals']['sewing_duration_s'])/3600)


def test_price_and_grid_factor_are_independent_of_geometry(config, plan):
    pricey = build_plan({'sizing': {'override': {'size': 'm'}}}, {**config, 'resources': {'electricity_eur_kwh': .5}})
    greener = build_plan({'sizing': {'override': {'size': 'm'}}}, {**config, 'resources': {'grid_gco2e_kwh': 190}})
    assert plan['pieces'] == pricey['pieces'] == greener['pieces']
    assert plan['paths'] == pricey['paths'] == greener['paths']
    base = plan['totals']['resources']; p = pricey['totals']['resources']; g = greener['totals']['resources']
    assert p['energy_kwh'] == g['energy_kwh'] == base['energy_kwh']
    assert p['co2e_g'] == base['co2e_g'] == g['co2e_g']*2
    assert p['cost_eur']-base['cost_eur'] == pytest.approx(base['cost_breakdown_eur']['electricity'])
    assert g['cost_breakdown_eur'] == base['cost_breakdown_eur']


@pytest.mark.parametrize('changes', [{'design': {'length_mm': 800}}, {'design': {'seam_mm': 20}}, {'machine': {'fabric_width_mm': 1200}}])
def test_geometry_changes_material_cost(config, plan, changes):
    other = build_plan({}, {**config, **changes})
    assert other['totals']['resources']['cost_breakdown_eur']['fabric'] != plan['totals']['resources']['cost_breakdown_eur']['fabric']


def test_sewing_length_changes_thread_cost(config, plan):
    other = build_plan({}, {**config, 'design': {'length_mm': 800}})
    assert other['totals']['resources']['cost_breakdown_eur']['thread'] > plan['totals']['resources']['cost_breakdown_eur']['thread']


def test_cutting_only_does_not_consume_sewing_resources(config):
    p = build_plan({}, {**config, 'scope': 'through_cutting'})
    r = p['totals']['resources']
    assert r['energy_breakdown_kwh']['pfaff'] == r['thread_used_m'] == r['cost_breakdown_eur']['thread'] == 0
    assert r['cost_breakdown_eur']['equipment'] == pytest.approx(p['totals']['duration_s']/3600*6)


def test_random_access_pause_and_speed_cannot_change_resources(plan):
    now = [0.]
    player = Playback(plan, clock=lambda: now[0])
    first = player.control('seek', 250)
    player.control('speed', 100);now[0] = 500
    assert player.get()['resources'] == first['resources']
    player.control('seek', plan['totals']['duration_s'])
    again = player.control('seek', 250)
    assert first['resources'] == again['resources']
    assert 'Energy' in '\n'.join(terminal_lines(again)) and 'Size: M' in terminal_lines(again)[0]


def test_old_plan_is_not_recalculated_with_new_assumptions(plan):
    old = copy.deepcopy(plan);old['schema_version'] = 'garment-simulation/2'
    for key in ('resource_ledger', 'resource_model', 'size'):old.pop(key)
    old['totals'].pop('resources');old['config'].pop('resources')
    assert snapshot(old, 100)['resources'] is None
    job = Job('old', {}, {})
    summary = passport_summary.build('code', '2', passport_doc.default_config(), job, 'unknown', {**snapshot(old,100),'status':'paused'}, old)
    assert summary['process']['resources'] is summary['process']['estimation'] is None


@pytest.mark.parametrize('bad', [{'currency':'USD'}, {'zund_active_kw': '1 W'}, {'labour_eur_h':-1}, {'grid_gco2e_kwh':float('nan')}, {'thread_eur_m':float('inf')}])
def test_invalid_resource_inputs_are_refused(bad):
    with pytest.raises(ValueError): SimulationConfig(resources=bad)


def test_size_change_refuses_qr_and_does_not_change_snapshot(plan, tmp_path, monkeypatch):
    monkeypatch.setattr(passport_doc,'RUNS',tmp_path)
    job=Job('resources',{},{});sizing_map.set_override(job,'m');job.simulation=Playback(plan)
    first=passport_doc.build(job,passport_doc.default_config(),'http://testserver')
    sizing_map.set_override(job,'l')
    with pytest.raises(passport_doc.PassportError,match='simulation size differs'):
        passport_doc.build(job,passport_doc.default_config(),'http://testserver')
    assert passport_summary.read(first['code']) == first['public_summary']
    doc=first['passport']
    assert not set(('manufacturing_date','production_events','garment_measurements','warranty')) & set(doc)


def test_cli_and_library_export_identical_plan_and_resources(config, tmp_path):
    document={'sizing':{'override':{'size':'m'}}}
    measurements=tmp_path/'input.json';measurements.write_text(json.dumps(document))
    settings=tmp_path/'config.json';settings.write_text(json.dumps(config))
    output=tmp_path/'result.json'
    cli=subprocess.run([sys.executable,'-m','studio.simulate','--measurements',str(measurements),'--config',str(settings),
                        '--instant','--no-color','--out',str(output)],cwd=Path(__file__).parents[1],capture_output=True,check=True)
    saved=json.loads(output.read_text(encoding='utf-8'));expected=build_plan(document,config)
    assert saved['plan']==expected
    assert saved['result']['resources']==expected['totals']['resources']
    assert b'Energy' in cli.stdout and b'Cost' in cli.stdout
