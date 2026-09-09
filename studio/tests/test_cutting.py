"""Geometry, provenance, deterministic playback and the web/CLI contract."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, box

from studio import paths
from studio.server import app
from studio.simulation import SimulationConfig, build_plan, snapshot
from studio.simulation.inputs import InputError, inspect_inputs
from studio.simulation.playback import Playback, terminal_lines
from studio.simulation import service
from studio.jobs import REGISTRY

EXAMPLES=paths.STUDIO_ROOT/'examples'


@pytest.fixture
def config():
    return json.loads((EXAMPLES/'cutting-config.json').read_text(encoding='utf-8'))


@pytest.fixture
def plan(config):
    return build_plan({'units':'mm','measurements':{}},config)


def test_geometry_is_valid_and_nesting_has_clearance(plan):
    assert len(plan['pieces'])==9
    assert {w['material'] for w in plan['windows']}=={'pique','rib'}
    placed=[]
    for w in plan['windows']:
        polygons=[Polygon(p['contour']) for p in w['placements']]
        assert all(p.is_valid for p in polygons)
        for i,p in enumerate(polygons):
            assert box(0,0,w['width_mm'],w['length_mm']+.001).covers(p)
            assert all(p.distance(q)>=plan['config']['machine']['gap_mm']-.001 for q in polygons[i+1:])
        placed.extend(p['piece_id'] for p in w['placements'])
    assert len(placed)==len(set(placed))==9
    assert max(c['delta_mm'] for c in plan['seam_checks'])<.5
    assert all(p['rotation_deg'] in (0,180) for w in plan['windows'] for p in w['placements'])


def test_internal_cuts_before_outer_and_no_premature_completion(plan):
    for w in plan['windows']:
        ops=[o for o in plan['operations'] if o['window']==w['id']]
        internal=[o['end_s'] for o in ops if o['kind']=='cut_internal']
        outer=[o for o in ops if o['kind']=='cut_outer']
        if internal:assert max(internal)<min(o['start_s'] for o in outer)
        for o in outer:
            assert snapshot(plan,o['end_s']-1e-6)['pieces'][o['piece_id']]=='cutting'
            assert snapshot(plan,o['end_s'])['pieces'][o['piece_id']]=='cut'
    final=snapshot(plan,plan['totals']['duration_s'])
    assert final['finished'] and set(final['pieces'].values())=={'sewn'}
    assert final['metrics']['cut_length_mm']==pytest.approx(plan['totals']['cut_length_mm'])
    assert final['metrics']['travel_mm']==pytest.approx(plan['totals']['travel_mm'])
    assert final['machines']['pfaff']=='complete'
    assert final['machines']['zsk']=='optional'


def test_every_path_is_on_window_and_speed_drives_time(plan):
    for o in plan['operations']:
        if o['path_id'] is None:continue
        p=plan['paths'][o['path_id']]
        assert p['distance_mm']==pytest.approx(p['cumulative_mm'][-1])
        speed=plan['config']['machine'][{'travel':'travel_speed_mm_s','mark':'mark_speed_mm_s'}.get(o['kind'],'cut_speed_mm_s')]
        assert o['end_s']-o['start_s']==pytest.approx(p['distance_mm']/speed)
        for x,y in p['points']:
            assert 0<=x<=plan['config']['machine']['bed_width_mm']
            assert 0<=y<=plan['config']['machine']['bed_length_mm']


def test_parameter_sensitivity_and_window_splitting(config,plan):
    assert build_plan({'units':'mm','measurements':{}},config)==plan
    for change in ({'design':{'seam_mm':15}},{'manual':{**config['manual'],'chest_circumference':{'value':1080,'unit':'mm','reason':'test change'}}}):
        changed=build_plan({}, {**config,**change})
        assert changed['totals']['cut_length_mm']!=plan['totals']['cut_length_mm']
        assert changed['pieces'][0]['area_mm2']!=plan['pieces'][0]['area_mm2']
    narrow=build_plan({}, {**config,'machine':{'fabric_width_mm':850,'rib_width_mm':800,'bed_width_mm':1000,'bed_length_mm':850}})
    assert len(narrow['windows'])>len(plan['windows'])
    assert narrow['totals']['yield_pct']!=plan['totals']['yield_pct']
    fast=build_plan({}, {**config,'machine':{'cut_speed_mm_s':200}})
    assert fast['totals']['cut_length_mm']==plan['totals']['cut_length_mm']
    assert fast['totals']['duration_s']<plan['totals']['duration_s']


def test_measurement_quality_units_and_provenance(config):
    original={'units':'mm','measurements':{'chest_circumference':{
        'selected_value_mm':1000,'disposition':'manual_review','quality':['surface_path_detour']}}}
    saved=copy.deepcopy(original)
    no_override=copy.deepcopy(config);del no_override['manual']['chest_circumference']
    with pytest.raises(InputError,match='manual_review'):build_plan(original,no_override)
    plan=build_plan(original,config)
    row=next(r for r in plan['inputs'] if r['key']=='chest_circumference')
    assert row['source']=='manual' and row['original']['disposition']=='manual_review'
    assert original==saved
    accepted={'units':'mm','measurements':{'chest_circumference':{'selected_value_mm':1000,'disposition':'accepted','quality':['ok']}}}
    assert build_plan(accepted,no_override)['inputs'][0]['source']=='measurement'
    accepted['units']='m'
    with pytest.raises(InputError,match='expected mm'):build_plan(accepted,no_override)
    accepted['units']='mm';accepted['pathway']='measured_clothed'
    with pytest.raises(InputError,match='clothed'):build_plan(accepted,no_override)


@pytest.mark.parametrize('change',[
    {'design':{'seam_mm':float('nan')}}, {'speed':float('inf')},
    {'machine':{'cut_speed_mm_s':0}}, {'machine':{'fabric_width_mm':300}},
    {'machine':{'bed_width_mm':1000}}, {'design':{'length_mm':350}},
    {'design':{'sleeve_length_mm':150}},
])
def test_invalid_geometry_and_settings_block(config,change):
    with pytest.raises(ValueError):build_plan({}, {**config,**change})


def test_missing_inputs_not_defaulted():
    with pytest.raises(InputError) as exc:build_plan({'units':'mm','measurements':{}})
    assert len(exc.value.issues)==11
    assert all(not r['usable'] for r in inspect_inputs({},SimulationConfig()))


def test_clock_pause_seek_and_duplicate_reads(plan):
    clock=[0.];events=[];p=Playback(plan,events.append,clock=lambda:clock[0])
    p.control('play');clock[0]=1;p.tick()
    assert p.get()['sim_time_s']==10
    p.control('pause');clock[0]=20;p.tick();assert p.get()['sim_time_s']==10
    old=p.get();assert p.get()==old
    p.control('seek',100);a=p.get();p.control('seek',20);p.control('seek',100);b=p.get()
    for key in ('pieces','metrics','head_mm','completed_paths','operation_index'):assert a[key]==b[key]
    assert b['seq']>a['seq'] and b['revision']>a['revision']
    p.control('speed',2);p.control('play');clock[0]=21;p.tick();assert p.get()['sim_time_s']==102
    p.control('seek',plan['totals']['duration_s']);assert p.get()['finished']
    p.control('restart');assert p.get()['sim_time_s']==0 and not p.get()['finished']
    with pytest.raises(ValueError):p.control('seek',float('nan'))
    with pytest.raises(ValueError):p.control('speed',0)
    p.close()


def test_cli_matches_python_engine(tmp_path,config,plan):
    dest=tmp_path/'simulation.json';log=tmp_path/'states.jsonl'
    run=subprocess.run([sys.executable,'-m','studio.simulate','--measurements',str(EXAMPLES/'cutting-measurements.json'),
                        '--config',str(EXAMPLES/'cutting-config.json'),'--instant','--no-color',
                        '--out',str(dest),'--jsonl',str(log)],cwd=paths.STUDIO_ROOT,capture_output=True,text=True,encoding='utf-8')
    assert run.returncode==0,run.stderr
    document=json.loads(dest.read_text(encoding='utf-8'))
    assert document['plan']==plan
    final=snapshot(plan,plan['totals']['duration_s'])
    assert document['result']['metrics']==final['metrics']
    assert document['result']['pieces']==final['pieces']
    lines=[json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert lines[-1]['finished'] and lines[0]['sim_time_s']==0
    assert '\n'.join(terminal_lines(document['result'])) in run.stdout


def test_api_replay_alias_controls_and_export(tmp_path,monkeypatch,config,plan):
    monkeypatch.setattr(service,'RUNS',tmp_path)
    c=TestClient(app)
    example=c.post('/api/simulation/example').json();job=example['job_id'];base=f'/api/jobs/{job}'
    try:
        bad=c.post(base+'/run/simulate',json={})
        assert bad.status_code==422 and len(bad.json()['detail']['issues'])==11
        r=c.post(base+'/run/replay',json={**config,'delay':0,'embroidery':True})
        assert r.status_code==200,r.text
        run=r.json()['run_id']
        pause=c.post(base+'/simulation/control',json={'run_id':run,'action':'pause'}).json()
        data=c.get(base+'/simulation').json()
        assert data['plan']==build_plan(service.document_for(REGISTRY.get(job)),config)
        assert data['state']==pause
        assert data['state']['terminal_lines']==terminal_lines(pause)
        assert c.post(base+'/simulation/control',json={'run_id':'old','action':'play'}).status_code==409
        assert c.post(base+'/simulation/control',json={'run_id':run,'action':'speed','value':0}).status_code==422
        end=c.post(base+'/simulation/control',json={'run_id':run,'action':'seek','value':plan['totals']['duration_s']}).json()
        artifact=c.get(base+'/simulation/download').json()
        assert end['metrics']==artifact['result']['metrics']
        assert artifact['result']['finished']
        assert (tmp_path/job/'simulation'/'plan.json').is_file()
        result=json.loads((tmp_path/job/'simulation'/'result.json').read_text(encoding='utf-8'))
        assert result['is_simulation'] and not result['finished_garment']
        assert result['cutting_complete']
    finally:
        if REGISTRY.get(job).simulation:REGISTRY.get(job).simulation.close()


def test_equipment_inventory(plan):
    names={m['id'] for m in plan['machines']}
    assert names=={'zund','laser','pfaff','veit','qc','zsk','epson','kornit','overlock','coverstitch','rib','button'}


def test_passport_cannot_claim_a_finished_garment(measured_job,plan,tmp_path,monkeypatch):
    from studio import passport_doc
    monkeypatch.setattr(passport_doc,'RUNS',tmp_path)
    job=measured_job
    player=Playback(build_plan({'sizing': job.size_view}, plan['config']))
    previous=job.simulation
    job.simulation=player
    try:
        result=passport_doc.build(job,passport_doc.default_config(),'http://testserver')
        data=result['passport']['manufacturing_data']
        assert data['is_simulation'] and not data['cutting_complete']
        player.control('seek',plan['totals']['duration_s'])
        result=passport_doc.build(job,passport_doc.default_config(),'http://testserver')
        data=result['passport']['manufacturing_data']
        assert data['cutting_complete'] and data['finished_garment'] is False
        assert data['scope']=='through_sewing' and data['pattern_status']=='research_draft_unverified'
        assert data['sewing_complete']
        encoded=json.dumps(data)
        assert not any(k in encoded for k in ('chest_circumference','manual_reason','contour','head_mm','inputs'))
    finally:job.simulation=previous;player.close()


def test_remeasurement_invalidates_the_previous_plan(tmp_path,monkeypatch,plan):
    from studio import server
    c=TestClient(app)
    job=REGISTRY.create({}, {'id':'unit-test'})
    job.mesh=object()
    job.simulation=Playback(plan)
    job.simulation.control('pause')
    old=job.simulation
    monkeypatch.setitem(server._STAGES,'measure',lambda j: None)
    r=c.post(f'/api/jobs/{job.id}/run/measure',json={})
    assert r.status_code==200
    job.worker.join(timeout=1)
    assert job.simulation is None and old.closed.is_set()
    assert any(e['type']=='simulation_reset' for e in job.events)


@pytest.mark.parametrize('document',[[],{'measurements':[]},{'measurements':{'chest_circumference':1000}}, {'meta':{'garment_prototypes':[]}}])
def test_malformed_measurement_document_is_actionable(document,config):
    with pytest.raises(InputError):build_plan(document,config)
