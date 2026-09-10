from copy import deepcopy
from collections import defaultdict
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys

import pytest

from studio.factory import Scenario, simulate, Replay, save, load
from studio.factory.__main__ import scenario_file
from studio.factory.ledger import Ledger, quantities
from studio.factory.template import COLUMNS, COL
from studio.factory.replay import apply_event, initial_state
from studio.factory.stages import STAGES, stage_rates
from studio.simulation.engine import snapshot as legacy_snapshot

ROOT = Path(__file__).resolve().parents[1]


def scenario(orders=None, factory=None, scope=None, stages=None):
    data = scenario_file(ROOT/'examples/factory-scenario.json')
    data['orders'] = orders or [{'id':'one','quantity':1}]
    data['factory'] = factory or {}
    if scope: data['scope'] = scope
    if stages: data['stages'] = stages
    return data


QC = 'through_qc'


CASES = {
    'one': scenario(),
    'two_orders': scenario([{'id':'a','quantity':2},{'id':'b','quantity':2,'release_s':60}]),
    'limited_worker': scenario([{'id':'a','quantity':4}],{'zund':3,'cutting_workers':1}),
    'multiple_machines': scenario([{'id':'a','quantity':4}],{'zund':2,'pfaff':2,'cutting_workers':2,'sewing_workers':2}),
    'batch': scenario([{'id':'a','quantity':4}],{'batch_size':2,'buffer_capacity':2}),
    'remainder': scenario([{'id':'a','quantity':3},{'id':'b','quantity':1}],{'batch_size':2,'buffer_capacity':2}),
    'one_qc': scenario(scope=QC),
    # Two presses share one finishing worker; one QC station takes what they release.
    'qc_line': scenario([{'id':'a','quantity':4}],{'zund':2,'pfaff':2,'cutting_workers':2,'sewing_workers':2,
                                                   'veit':2,'finishing_workers':1,'qc':1,'qc_workers':1},scope=QC),
}


@pytest.fixture(scope='module')
def runs():
    return {k:simulate(v) for k,v in CASES.items()}


def close(actual,expected):
    if isinstance(expected,dict):
        assert actual.keys() == expected.keys()
        for key in expected: close(actual[key],expected[key])
    elif isinstance(expected,list):
        assert len(actual) == len(expected)
        for a,b in zip(actual,expected): close(a,b)
    elif isinstance(expected,float): assert actual == pytest.approx(expected,rel=1e-9,abs=1e-6)
    else: assert actual == expected


def golden(run):
    # Ordered station/worker allocation and domain event vocabulary are frozen,
    # alongside numbers independently checked by reference tests below.
    return {'duration_s':run['duration_s'], 'result':run['result'],
            'segments':[{**{k:r[k] for k in ('kind','station','start_s','end_s','garments','machine','worker','cart')},
                         'step':r.get('step')} for r in run['rows']],
            'events':[{k:e[k] for k in ('kind','garments','buffer_used')} for e in run['events']]}


@pytest.mark.parametrize('name',list(CASES))
def test_golden(name,runs):
    expected = json.loads((ROOT/'factory_tests/golden'/f'{name}.json').read_text(encoding='utf-8'))
    close(golden(runs[name]),expected)


def test_single_garment_equivalence(runs):
    run = runs['one']; plan = run['template']; result = run['result']['resources']
    old = plan['totals']['resources']; rates = run['scenario']['config']['resources']
    transfer = run['scenario']['factory']['transport_s']
    assert len(plan['operations']) == 188
    assert len(run['template_index']['segments']) == 12
    assert run['duration_s'] == plan['totals']['duration_s']
    for row in run['rows']:
        assert row['start_s'] == row['template_start_s']
        assert row['end_s'] == row['template_end_s']
    expected = deepcopy(old)
    energy_delta = transfer*rates['pfaff_idle_kw']/3600
    equipment_delta = transfer*rates['pfaff_eur_h']/3600
    expected['energy_kwh'] -= energy_delta
    expected['co2e_g'] -= energy_delta*rates['grid_gco2e_kwh']
    expected['energy_breakdown_kwh']['pfaff'] -= energy_delta
    expected['cost_breakdown_eur']['electricity'] -= energy_delta*rates['electricity_eur_kwh']
    expected['cost_breakdown_eur']['equipment'] -= equipment_delta
    expected['cost_eur'] -= equipment_delta+energy_delta*rates['electricity_eur_kwh']
    # The legacy engine has no finishing or QC; those columns must be exactly zero here.
    actual = deepcopy(result)
    for key in ('veit','qc'): assert actual['energy_breakdown_kwh'].pop(key) == 0
    for key in ('pressed','inspected'): assert actual['metrics'].pop(key) == 0
    close({k:actual[k] for k in expected},expected)
    player = Replay(run)
    times = [0,run['duration_s']]+[o['end_s'] for o in plan['operations']]+[(o['start_s']+o['end_s'])/2 for o in plan['operations']]
    for t in times:
        old_state = legacy_snapshot(plan,t)
        state = player.snapshot(t,'one:0001'); selected = state['selected_garment']
        for key in ('operation_index','operation','operation_progress','window','tool','head_mm','completed_paths','pieces','vacuum'):
            close(selected[key],old_state[key])
        close(selected['seams'],old_state['sewing']['seams'])
        for key in ('cut_length_mm','travel_mm','mark_length_mm','sewn_length_mm','stitches','collected_pieces','seams_complete'):
            close(state['resources']['metrics'][key],old_state['metrics'][key])
    assert run['result']['queues']['cut_worker_wait']['peak'] == 0


def test_simultaneous_allocation_does_not_depend_on_creation_order():
    data = scenario([{'id':'z','quantity':2},{'id':'a','quantity':2},{'id':'m','quantity':1}],
                    {'zund':2,'pfaff':2,'cutting_workers':2,'sewing_workers':2})
    a = simulate(data,release_order=[0,1,2]); b = simulate(data,release_order=[2,0,1])
    assert a['content_hash'] == b['content_hash']
    first = [r for r in a['rows'] if r['start_s']==0]
    assert [r['machine'] for r in first] == ['zund-001','zund-002']
    assert [r['garments'] for r in first] == [[0],[1]]
    assert a['run_id'] != b['run_id']
    data['config']['speed'] = 99
    assert simulate(data)['content_hash'] == a['content_hash']


def test_shifted_garment_operation_boundaries_are_exact(runs):
    run=runs['multiple_machines'];player=Replay(run)
    for row in run['rows']:
        if row['kind']!='template':continue
        garment_id=run['garments'][row['garments'][0]]['id']
        for op in run['template']['operations']:
            if not row['template_start_s']<op['end_s']<row['template_end_s']:continue
            world_end=(op['end_s'] if row['start_s']==row['template_start_s'] else
                       row['start_s']+(op['end_s']-row['template_start_s']))
            for offset in (-1e-7,0,1e-7):
                selected=player.snapshot(world_end+offset,garment_id)['selected_garment']
                expected=legacy_snapshot(run['template'],op['end_s']+offset)
                assert selected['operation_index']==expected['operation_index']
                close(selected['pieces'],expected['pieces'])
                close(selected['seams'],expected['sewing']['seams'])


@pytest.mark.parametrize('name',list(CASES))
def test_resource_and_buffer_invariants(name,runs):
    run = runs[name]
    assert run['result']['completed_garments'] == len(run['garments'])
    assert run['result']['finished_garment'] is False
    intervals = defaultdict(list)
    for row in run['rows']:
        assert row['end_s'] > row['start_s']
        for rid in (row['machine'],row['worker'],row['cart']):
            if rid: intervals[rid].append((row['start_s'],row['end_s']))
        if row['kind']=='transport':
            assert row['machine'] is None
            assert len(row['garments']) <= run['scenario']['factory']['batch_size']
            assert len({run['garments'][gi]['order_index'] for gi in row['garments']}) == 1
    for values in intervals.values():
        values.sort()
        assert all(a[1] <= b[0]+1e-8 for a,b in zip(values,values[1:]))
    for e in run['events']: assert 0 <= e['buffer_used'] <= run['scenario']['factory']['buffer_capacity']
    state = initial_state(len(run['garments']))
    for event in run['events']: apply_event(state,event)
    assert not state['resources'] and state['buffer_used']==0
    assert set(state['garments']) == {'complete'}
    if name=='remainder':
        assert sorted(len(r['garments']) for r in run['rows'] if r['kind']=='transport') == [1,1,2]


def slow_reference(run,t,order=None,garment=None):
    """Deliberately expands every operation, independent of the production indexes."""
    plan = run['template']; rates = stage_rates(run['scenario'])
    values = dict.fromkeys(COLUMNS,0.)
    seams = {s['id']:s for s in plan['sewing_seams']}
    def raw(local):
        result = dict.fromkeys(COLUMNS,0.)
        for op,row in zip(plan['operations'],plan['resource_ledger']):
            if local <= op['start_s']: continue
            f = min(1.,(local-op['start_s'])/(op['end_s']-op['start_s']))
            kind = op['kind']
            if kind == 'transfer_to_sewing': continue
            result[row['machine']+'_kwh'] += row['machine_kwh']*f
            result['vacuum_kwh'] += row['vacuum_kwh']*f
            result['labour_s'] += row['labour_s']*f
            result['equipment_eur'] += row['equipment_eur']*f
            result['thread_m'] += row['thread_m']*f
            if local >= op['end_s']:
                result['thread_m'] += row['tail_m_at_end']
                result[row['material']+'_m2'] += row['area_m2_at_end']
                result['fabric_eur'] += row['fabric_eur_at_end']
                if kind=='pickup': result['collected_pieces'] += 1
                if kind=='thread_trim': result['seams_complete'] += 1
            if op['path_id'] is not None:
                key = 'cut_length_mm' if kind.startswith('cut') else 'travel_mm' if kind=='travel' else 'mark_length_mm'
                result[key] += plan['paths'][op['path_id']]['distance_mm']*f
            if kind=='stitch':
                seam=seams[op['seam_id']]
                result['sewn_length_mm'] += seam['length_mm']*f
                result['stitches'] += math.floor(seam['stitches']*f+1e-8)
        return result
    for row in run['rows']:
        if row['start_s'] >= t: continue
        if order is not None and run['garments'][row['garments'][0]]['order_index'] != order: continue
        if garment is not None and garment not in row['garments']: continue
        elapsed = min(t,row['end_s'])-row['start_s']
        d = dict.fromkeys(COLUMNS,0.)
        if row['kind']=='template':
            local = row['template_end_s'] if t>=row['end_s'] else t+(row['template_start_s']-row['start_s'])
            a,b = raw(local),raw(row['template_start_s'])
            d = {key:a[key]-b[key] for key in values}
        elif row['kind']=='transport': d['labour_s'] = elapsed
        elif row['kind']=='stage':
            station=row['station']
            d[station+'_kwh'] = elapsed/3600*rates[station+'_active_kw']
            d['equipment_eur'] = elapsed/3600*rates[station+'_eur_h']
            if row['attended']: d['labour_s'] = elapsed
            if t>=row['end_s'] and row['step_index']==2: d['pressed' if station=='veit' else 'inspected'] = 1
        else:
            station=row['station']
            d[station+'_kwh'] = elapsed/3600*rates[station+'_idle_kw']
            d['equipment_eur'] = elapsed/3600*rates[station+'_eur_h']
            vacuum=False
            for op in plan['operations']:
                if op['end_s'] > row['template_start_s']: break
                if op['kind']=='vacuum_on': vacuum=True
                if op['kind']=='vacuum_off': vacuum=False
            if vacuum and station=='zund': d['vacuum_kwh']=elapsed/3600*rates['vacuum_kw']
        weight = 1/len(row['garments']) if garment is not None else 1
        for key in values: values[key] += d[key]*weight
    boundaries=sorted({0.,t}|{min(t,x) for r in run['rows'] for x in (r['start_s'],r['end_s']) if x<t})
    overhead=0.
    for a,b in zip(boundaries,boundaries[1:]):
        active=[gi for r in run['rows'] if r['kind']!='wait' and r['start_s'] <= (a+b)/2 < r['end_s'] for gi in r['garments']]
        if not active: continue
        fraction = (sum(run['garments'][gi]['order_index']==order for gi in active)/len(active) if order is not None
                    else int(garment in active)/len(active) if garment is not None else 1)
        overhead += (b-a)*rates['overhead_kw']/3600*fraction
    return values,overhead


def test_index_matches_slow_reference_and_rewind(runs,tmp_path):
    run=runs['limited_worker']; player=Replay(run); ledger=player.ledger
    rng=random.Random(17)
    times=[0,run['duration_s']]+[rng.random()*run['duration_s'] for _ in range(30)]
    times += [r['end_s'] for r in run['rows']]
    for t in times:
        state=player.snapshot(t,'a:0002')
        assert player.applied_last <= 255
        for scope in ({},{'garment':1},{'order':0}):
            vector,oh=slow_reference(run,t,**scope)
            actual=ledger.at(t,**scope)
            expected=quantities([vector[k] for k in COLUMNS],oh,ledger.rates,actual['flow_time_s'])
            close(actual,expected)
    state=initial_state(len(run['garments']))
    for event in run['events']:
        assert apply_event(state,event)
        before=deepcopy(state)
        assert not apply_event(state,event)
        assert state==before
    save(tmp_path/'run.json',run); loaded=load(tmp_path/'run.json')
    close(Replay(loaded).snapshot(120,'a:0002'),player.snapshot(120,'a:0002'))
    loaded['duration_s']+=1
    save(tmp_path/'corrupt.json',loaded)
    with pytest.raises(ValueError,match='hash'):load(tmp_path/'corrupt.json')


def test_cost_conservation_and_common_load_union(runs):
    for run in runs.values():
        total=run['result']['resources']
        close(total['cost_eur'],sum(total['cost_breakdown_eur'].values()))
        for owners in ('orders','garments'):
            for key in ('energy_kwh','co2e_g','cost_eur','labour_time_s','thread_used_m'):
                close(sum(g['resources'][key] for g in run['result'][owners]),total[key])
        merged=[]
        for row in sorted((r for r in run['rows'] if r['kind']!='wait'),key=lambda r:r['start_s']):
            if merged and row['start_s']<=merged[-1][1]: merged[-1][1]=max(merged[-1][1],row['end_s'])
            else: merged.append([row['start_s'],row['end_s']])
        expected=sum(b-a for a,b in merged)*run['scenario']['config']['resources']['overhead_kw']/3600
        close(total['energy_breakdown_kwh']['overhead'],expected)
    run=simulate(scenario([{'id':'a','quantity':1},{'id':'b','quantity':1,'release_s':1000}]))
    ledger=Ledger(run)
    assert ledger.at(900)['energy_kwh'] == ledger.at(600)['energy_kwh']
    assert Replay(run).snapshot(900)['active_resources']=={}


def test_vacuum_wait_is_billed_but_worker_wait_is_not(runs):
    run=runs['limited_worker']; waits=[r for r in run['rows'] if r['kind']=='wait']
    assert waits
    # Force a long attended pickup on one cutter while another waits with vacuum on.
    data=scenario([{'id':'a','quantity':6}],{'zund':3})
    data['config'].setdefault('machine',{}).update(pickup_s=60,align_s=60)
    run=simulate(data); ledger=Ledger(run)
    vacuum_waits=[r for r in run['rows'] if r['kind']=='wait' and ledger.template.vacuum_at_boundary(r['template_start_s'])]
    assert vacuum_waits
    row=vacuum_waits[0];gi=row['garments'][0]
    a=ledger.at(row['start_s'],garment=gi);b=ledger.at(row['end_s'],garment=gi)
    dt=row['end_s']-row['start_s']
    close(b['energy_breakdown_kwh']['vacuum']-a['energy_breakdown_kwh']['vacuum'],dt*ledger.rates['vacuum_kw']/3600)
    close(b['labour_time_s'],a['labour_time_s'])


@pytest.mark.parametrize('field,value',[('electricity_eur_kwh',.75),('grid_gco2e_kwh',800)])
def test_rate_parameter_isolation(field,value,runs):
    data=scenario();data['config']['resources']={field:value}
    other=simulate(data)['result']['resources'];base=runs['one']['result']['resources']
    close(other['energy_kwh'],base['energy_kwh'])
    if field=='grid_gco2e_kwh':close(other['cost_eur'],base['cost_eur']);assert other['co2e_g']!=base['co2e_g']
    else:
        close(other['co2e_g'],base['co2e_g'])
        for k in ('fabric','thread','labour','equipment'):close(other['cost_breakdown_eur'][k],base['cost_breakdown_eur'][k])


@pytest.mark.parametrize('kind,field,value',[('design','seam_mm',15),('design','length_mm',780),('machine','fabric_width_mm',1400)])
def test_geometry_changes_material_cost(kind,field,value,runs):
    data=scenario();data['config'].setdefault(kind,{})[field]=value
    result=simulate(data)['result']['resources']
    assert result['cost_breakdown_eur']['fabric'] != runs['one']['result']['resources']['cost_breakdown_eur']['fabric']


@pytest.mark.parametrize('change',[
    {'factory':{'batch_size':3,'buffer_capacity':2}}, {'factory':{'carts':0}},
    {'factory':{'zund':True}}, {'factory':{'pfaff':1.5}}, {'factory':{'transport_s':float('nan')}},
    {'factory':{'transport_s':-1}}, {'factory':{'distance_km':1}},
    {'orders':[{'id':'a','quantity':1001}]}, {'orders':[{'id':'a','quantity':1},{'id':'a','quantity':1}]},
    {'orders':[{'id':'a','quantity':1,'release_s':float('inf')}]},
])
def test_invalid_scenarios(change):
    data=scenario();data.update(change)
    with pytest.raises(ValueError):Scenario.model_validate(data)


def test_size_capture_and_mismatch():
    data=scenario();data['measurements']['sizing']={'size':'S'}
    with pytest.raises(ValueError,match='size'):simulate(data)


def test_checkpoints_beyond_first_block_and_duplicate_reconnect(tmp_path):
    run=simulate(scenario([{'id':'many','quantity':50}],{'zund':2,'pfaff':3,'sewing_workers':3}))
    assert len(run['checkpoints'])>3
    player=Replay(run);rng=random.Random(113)
    for t in [run['duration_s'],0]+[rng.random()*run['duration_s'] for _ in range(40)]:
        snapshot=player.snapshot(t,'many:0025')
        assert player.applied_last <= 255
        expected=initial_state(50)
        for event in run['events']:
            if event['time_s']>t:break
            apply_event(expected,event)
        assert player.state==expected
        assert player.snapshot(t,'many:0025')==snapshot
        assert player.applied_last==0
    save(tmp_path/'run.json',run)
    close(Replay(load(tmp_path/'run.json')).snapshot(600,'many:0025'),player.snapshot(600,'many:0025'))


def test_long_sewing_and_minimum_buffer_complete():
    data=scenario([{'id':'long','quantity':7}],{'zund':3,'batch_size':3,'buffer_capacity':3})
    data['config']['machine']={'stitches_per_min':60}
    run=simulate(data)
    assert run['result']['completed_garments']==7
    assert run['result']['queues']['buffer_reserved_or_occupied']['peak']==3
    assert max(g['waits']['before_transport_s'] for g in run['result']['garments'])>0


def test_thread_and_direct_labour_sensitivity(runs):
    data=scenario();data['config']['design']={'length_mm':800}
    longer=simulate(data)['result']['resources'];base=runs['one']['result']['resources']
    assert longer['thread_used_m']>base['thread_used_m']
    assert longer['cost_breakdown_eur']['thread']>base['cost_breakdown_eur']['thread']
    data=scenario();data['config']['machine']={'seam_align_s':5}
    slower=simulate(data)['result']['resources']
    close(slower['labour_time_s']-base['labour_time_s'],18.)
    close(slower['cost_breakdown_eur']['labour']-base['cost_breakdown_eur']['labour'],18*22/3600)
    close(slower['thread_used_m'],base['thread_used_m'])


@pytest.mark.parametrize('variant',['missing','rejected','wrong_unit','angle_unit','impossible_width'])
def test_measurement_and_pattern_failures(variant):
    data=scenario()
    if variant=='angle_unit': data['config']['manual']['shoulder_slope']['unit']='mm'
    elif variant=='impossible_width': data['config']['machine']={'bed_width_mm':300,'fabric_width_mm':300}
    else:
        del data['config']['manual']['chest_circumference']
        if variant!='missing':
            data['measurements']['measurements']['chest_circumference']={
                'selected_value_mm':1000,'disposition':'rejected' if variant=='rejected' else 'accepted','quality':[]}
            data['measurements']['units']='m' if variant=='wrong_unit' else 'mm'
    original=deepcopy(data)
    with pytest.raises(ValueError):simulate(data)
    assert data==original


@pytest.mark.parametrize('at',[float('nan'),float('inf'),-1,1e8,True])
def test_invalid_replay_time(at,runs):
    with pytest.raises(ValueError):Replay(runs['one']).snapshot(at)


def test_cli_rejects_input_overwrite_and_invalid_output(tmp_path):
    path=tmp_path/'scenario.json';path.write_text(json.dumps(scenario()),encoding='utf-8')
    raw=path.read_bytes()
    proc=subprocess.run([sys.executable,'-m','studio.factory','--scenario',str(path),'--out',str(path)],
                        cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==2 and path.read_bytes()==raw
    data=scenario();data['factory']={'batch_size':11,'buffer_capacity':10}
    path.write_text(json.dumps(data),encoding='utf-8');out=tmp_path/'invalid.json'
    proc=subprocess.run([sys.executable,'-m','studio.factory','--scenario',str(path),'--out',str(out)],
                        cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==2 and not out.exists()


def test_clean_public_checkout_and_cli(tmp_path):
    # No QR/polo/web code exists in this checkout. Block accidental imports too.
    checkout=tmp_path/'public'; checkout.mkdir()
    ignore=shutil.ignore_patterns('__pycache__','*.pyc')
    shutil.copytree(ROOT/'studio',checkout/'studio/studio',ignore=ignore)
    shutil.copytree(ROOT.parent/'body_measure',checkout/'body_measure',ignore=ignore)
    data=scenario(); (checkout/'studio/scenario.json').write_text(json.dumps(data),encoding='utf-8')
    script="""
import importlib.abc, sys, runpy
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
class BlockPrivate(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in ('studio.paths','studio.server') or fullname.split('.')[0] in ('app','polo_line','fastapi'):
            raise ImportError('Private or web dependency imported: '+fullname)
sys.meta_path.insert(0,BlockPrivate())
sys.argv=['factory','--scenario','scenario.json','--out','run.json','--jsonl','events.jsonl','--no-color']
runpy.run_module('studio.factory',run_name='__main__')
"""
    proc=subprocess.run([sys.executable,'-I','-c',script],cwd=checkout/'studio',capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==0,proc.stderr
    assert 'RESEARCH SIMULATION' in proc.stdout and '\x1b' not in proc.stdout
    run=load(checkout/'studio/run.json')
    assert run['result']['completed_garments']==1
    assert run['content_hash']==simulate(data)['content_hash']
    events=[json.loads(line) for line in (checkout/'studio/events.jsonl').read_text().splitlines()]
    assert len(events)==len(run['events'])
    assert all(e['run_id']==run['run_id'] for e in events)
    proc=subprocess.run([sys.executable,'-m','studio.factory','--replay','run.json','--at','120','--garment','one:0001'],
                        cwd=checkout/'studio',capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==0,proc.stderr
    assert 'one:0001' in proc.stdout
    assert str(checkout) not in (checkout/'studio/run.json').read_text(encoding='utf-8')


# --- Finishing and QC (scope through_qc), ending before the DPP label / QR ---

def stage_rows(run,gi=None):
    return [r for r in run['rows'] if r['kind']=='stage' and (gi is None or gi in r['garments'])]


def test_qc_scope_extends_the_sewing_run_without_changing_it(runs):
    base,run=runs['one'],runs['one_qc']
    assert base['scope']=='through_sewing' and run['scope']=='through_qc'
    assert run['result']['finished_garment'] is False and run['result']['qc']['dpp_label_or_qr_issued']==0
    # Cutting, transport and sewing rows are identical; the ledger agrees up to sewing completion.
    sewn=base['duration_s']
    for a,b in zip(base['rows'],run['rows'][:len(base['rows'])]):
        close({k:a[k] for k in ('kind','station','start_s','end_s','machine','worker','cart')},
              {k:b[k] for k in ('kind','station','start_s','end_s','machine','worker','cart')})
    close(Ledger(run).at(sewn),Ledger(base).at(sewn))
    steps=stage_rows(run)
    assert [r['step'] for r in steps]==['press_load','press_cycle','press_unload','qc_load','qc_scan','qc_release']
    assert [r['worker'] is not None for r in steps]==[True,False,True,True,False,True]
    stages=run['scenario']['stages']
    finishing=stages['finishing']['load_s']+stages['finishing']['cycle_s']+stages['finishing']['unload_s']
    qc=stages['qc']['load_s']+stages['qc']['scan_s']+stages['qc']['release_s']
    close(run['duration_s'],sewn+finishing+qc)
    g=run['garments'][0]
    close(g['finishing_start_s'],sewn); close(g['finishing_end_s'],sewn+finishing)
    close(g['qc_start_s'],sewn+finishing); close(g['end_s'],run['duration_s'])
    assert g['qc_verdict']=='pass' and run['result']['garments'][0]['qc_verdict']=='pass'
    for r in steps: assert r['template_start_s']==r['template_end_s']==base['duration_s']
    assert all(w==0 for w in run['result']['garments'][0]['waits'].values())
    kinds=[e['kind'] for e in run['events']]
    assert kinds[kinds.index('sewing_complete'):]==['sewing_complete','finishing_start','finishing_step_complete',
        'finishing_start','finishing_step_complete','finishing_start','finishing_complete','qc_start',
        'qc_step_complete','qc_start','qc_step_complete','qc_start','qc_complete']
    statuses=[status for e in run['events'] for _,status in e['garments']]
    assert statuses[-13:]==['finish_queue','finishing','finishing_worker_wait','finishing','finishing_worker_wait','finishing',
                            'qc_queue','inspecting','qc_worker_wait','inspecting','qc_worker_wait','inspecting','complete']


def test_stage_accounting_matches_rated_power_and_attended_labour(runs):
    base,run=runs['one'],runs['one_qc']
    rates=stage_rates(run['scenario']); stages=run['scenario']['stages']
    a,b=base['result']['resources'],run['result']['resources']
    finishing=stages['finishing']['load_s']+stages['finishing']['cycle_s']+stages['finishing']['unload_s']
    qc=stages['qc']['load_s']+stages['qc']['scan_s']+stages['qc']['release_s']
    close(b['energy_breakdown_kwh']['veit'],finishing/3600*stages['finishing']['active_kw'])
    close(b['energy_breakdown_kwh']['qc'],qc/3600*stages['qc']['active_kw'])
    for key in ('zund','pfaff','vacuum'): close(b['energy_breakdown_kwh'][key],a['energy_breakdown_kwh'][key])
    close(b['energy_breakdown_kwh']['overhead']-a['energy_breakdown_kwh']['overhead'],(finishing+qc)/3600*rates['overhead_kw'])
    attended=stages['finishing']['load_s']+stages['finishing']['unload_s']+stages['qc']['load_s']+stages['qc']['release_s']
    close(b['labour_time_s']-a['labour_time_s'],attended)
    close(b['cost_breakdown_eur']['equipment']-a['cost_breakdown_eur']['equipment'],
          finishing/3600*stages['finishing']['equipment_eur_h']+qc/3600*stages['qc']['equipment_eur_h'])
    for key in ('fabric','thread'): close(b['cost_breakdown_eur'][key],a['cost_breakdown_eur'][key])
    close(b['fabric_used_m2'],a['fabric_used_m2']); close(b['thread_used_m'],a['thread_used_m'])
    assert b['metrics']['pressed']==1 and b['metrics']['inspected']==1
    assert a['metrics']['pressed']==0 and a['metrics']['inspected']==0
    # Counts land only at the end of the last step of each stage.
    ledger=Ledger(run); g=run['garments'][0]
    for t,pressed,inspected in ((g['finishing_end_s']-1,0,0),(g['finishing_end_s'],1,0),(g['qc_end_s']-1,1,0),(g['qc_end_s'],1,1)):
        m=ledger.at(t)['metrics']; assert (m['pressed'],m['inspected'])==(pressed,inspected)


def test_qc_line_shares_one_finishing_worker_across_two_presses(runs):
    run=runs['qc_line']; result=run['result']
    assert result['completed_garments']==4 and result['qc']=={'inspected':4,'passed':4,'failed':0,
        'verdict_model':'deterministic_pass_no_defect_model','ready_for_dpp_label':4,'dpp_label_or_qr_issued':0}
    assert set(run['inventory'])>={'veit','qc','finishing_workers','qc_workers'}
    assert run['inventory']['veit']==['veit-001','veit-002'] and run['inventory']['finishing_workers']==['finishing_workers-001']
    # Two garments finish sewing together; both presses load in turn, and while
    # one cycles unattended the single worker loads the other.
    loads=[r for r in stage_rows(run) if r['step']=='press_load']
    assert {r['machine'] for r in loads}=={'veit-001','veit-002'}
    cycles=[r for r in stage_rows(run) if r['step']=='press_cycle']
    overlap=any(a['start_s']<b['end_s'] and b['start_s']<a['end_s'] for a in cycles for b in cycles if a is not b)
    assert overlap
    for r in cycles: assert r['worker'] is None
    # A press whose unload waits for the busy worker is recorded as a held wait on that press.
    waits=[r for r in run['rows'] if r['kind']=='wait' and r['station']=='veit']
    assert waits and all(r['machine'].startswith('veit') for r in waits)
    assert result['queues']['finishing_worker_wait']['peak']>=1
    assert sum(g['waits']['finishing_worker_s'] for g in result['garments'])==pytest.approx(sum(r['end_s']-r['start_s'] for r in waits))
    # Standby power and equipment occupancy are billed for the held press; no labour.
    ledger=Ledger(run); row=waits[0]; gi=row['garments'][0]; rates=stage_rates(run['scenario'])
    a=ledger.at(row['start_s'],garment=gi); b=ledger.at(row['end_s'],garment=gi); dt=row['end_s']-row['start_s']
    close(b['energy_breakdown_kwh']['veit']-a['energy_breakdown_kwh']['veit'],dt*rates['veit_idle_kw']/3600)
    close(b['cost_breakdown_eur']['equipment']-a['cost_breakdown_eur']['equipment'],dt*rates['veit_eur_h']/3600)
    close(b['labour_time_s'],a['labour_time_s'])
    for instance in ('veit-001','veit-002'):
        assert result['instances'][instance]['held_wait_s']>=0 and result['instances'][instance]['pool']=='veit'
    assert result['instances']['finishing_workers-001']['held_wait_s']==0
    # Every garment leaves QC in order of arrival on the single station.
    qc_rows=sorted((r for r in stage_rows(run) if r['step']=='qc_load'),key=lambda r:r['start_s'])
    assert [r['garments'][0] for r in qc_rows]==sorted(range(4),key=lambda gi:(run['garments'][gi]['finishing_end_s'],gi))


def test_qc_index_matches_slow_reference(runs):
    run=runs['qc_line']; player=Replay(run); ledger=player.ledger
    rng=random.Random(23)
    times=[0,run['duration_s']]+[rng.random()*run['duration_s'] for _ in range(20)]+[r['end_s'] for r in run['rows']]
    for t in times:
        player.snapshot(t,'a:0003')
        for scope in ({},{'garment':2},{'order':0}):
            vector,oh=slow_reference(run,t,**scope)
            actual=ledger.at(t,**scope)
            close(actual,quantities([vector[k] for k in COLUMNS],oh,ledger.rates,actual['flow_time_s']))


def test_qc_replay_reports_stage_readouts(runs):
    run=runs['one_qc']; player=Replay(run); g=run['garments'][0]
    stages=run['scenario']['stages']
    during_cycle=g['finishing_start_s']+stages['finishing']['load_s']+stages['finishing']['cycle_s']/2
    state=player.snapshot(during_cycle,'one:0001'); selected=state['selected_garment']
    assert state['scope']=='through_qc' and selected['status']=='finishing'
    assert selected['stage']['step']=='press_cycle' and selected['stage']['attended'] is False
    assert selected['operation']=='press_cycle' and selected['operation_progress']==pytest.approx(.5)
    assert selected['stage']['readouts']['press_temp_c']==164. and selected['stage']['readouts']['steam_bar']==4.8
    assert set(selected['pieces'].values())=={'sewn'} and set(selected['seams'].values())=={'sewn'}
    during_scan=g['qc_start_s']+stages['qc']['load_s']+stages['qc']['scan_s']*.25
    selected=player.snapshot(during_scan,'one:0001')['selected_garment']
    assert selected['status']=='inspecting' and selected['stage']['step']=='qc_scan'
    assert selected['stage']['readouts']=={'frames':24,'verdict':'scanning'}
    released=player.snapshot(g['qc_end_s']-1e-6,'one:0001')['selected_garment']
    assert released['stage']['step']=='qc_release' and released['stage']['readouts']['verdict']=='pass'
    done=player.snapshot(run['duration_s'],'one:0001')['selected_garment']
    assert done['status']=='complete' and done['stage'] is None
    before=player.snapshot(g['sewing_end_s']-1e-6,'one:0001')['selected_garment']
    assert before['status']=='sewing' and before['stage'] is None and before['operation']=='assembly_pickup'
    # A held press waiting for its worker reports the wait, not a step.
    line=runs['qc_line']; wait=next(r for r in line['rows'] if r['kind']=='wait' and r['station']=='veit')
    waiting=Replay(line).snapshot((wait['start_s']+wait['end_s'])/2,line['garments'][wait['garments'][0]]['id'])['selected_garment']
    assert waiting['status']=='finishing_worker_wait' and waiting['stage']['step']=='worker_wait'


@pytest.mark.parametrize('change',[
    {'stages':{'finishing':{'cycle_s':100}}}, {'factory':{'veit':2}}, {'factory':{'qc_workers':1}},
])
def test_stage_inputs_require_qc_scope(change):
    data=scenario(); data.update(change)
    with pytest.raises(ValueError,match='through_qc'): Scenario.model_validate(data)


@pytest.mark.parametrize('change',[
    {'factory':{'veit':0}}, {'factory':{'finishing_workers':65}}, {'stages':{'qc':{'scan_s':0}}},
    {'stages':{'finishing':{'active_kw':-1}}}, {'stages':{'finishing':{'press_s':10}}}, {'scope':'through_packing'},
])
def test_invalid_qc_scenarios(change):
    data=scenario(scope=QC); data.update(change)
    with pytest.raises(ValueError): Scenario.model_validate(data)


def test_stage_parameters_change_only_their_stage(runs):
    base=runs['one_qc']['result']['resources']
    data=scenario(scope=QC,stages={'finishing':{'cycle_s':400}})
    longer=simulate(data)['result']['resources']
    close(longer['energy_breakdown_kwh']['veit']-base['energy_breakdown_kwh']['veit'],175/3600*4.5)
    close(longer['labour_time_s'],base['labour_time_s'])
    close(longer['energy_breakdown_kwh']['qc'],base['energy_breakdown_kwh']['qc'])
    data=scenario(scope=QC,stages={'qc':{'release_s':30}})
    slower=simulate(data)['result']['resources']
    close(slower['labour_time_s']-base['labour_time_s'],20.)
    close(slower['energy_breakdown_kwh']['veit'],base['energy_breakdown_kwh']['veit'])
    # Through-sewing identity ignores stage inputs entirely.
    assert simulate(scenario())['content_hash']==runs['one']['content_hash']


def test_qc_cli_reports_readiness_for_the_label(tmp_path):
    path=tmp_path/'scenario.json'; path.write_text(json.dumps(scenario(scope=QC)),encoding='utf-8')
    out=tmp_path/'run.json'
    proc=subprocess.run([sys.executable,'-m','studio.factory','--scenario',str(path),'--out',str(out),'--no-color'],
                        cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==0,proc.stderr
    assert 'scope through_qc' in proc.stdout and 'Ready for DPP label: 1' in proc.stdout
    assert 'DPP label / QR / packing / shipping: not executed' in proc.stdout
    run=load(out); g=run['garments'][0]
    proc=subprocess.run([sys.executable,'-m','studio.factory','--replay',str(out),'--at',str(g['finishing_start_s']+100),'--garment','one:0001'],
                        cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==0,proc.stderr
    assert 'finishing | press_cycle | veit-001' in proc.stdout and 'press_temp_c' in proc.stdout
