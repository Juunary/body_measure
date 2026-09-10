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
from studio.simulation.engine import snapshot as legacy_snapshot

ROOT = Path(__file__).resolve().parents[1]


def scenario(orders=None, factory=None):
    data = scenario_file(ROOT/'examples/factory-scenario.json')
    data['orders'] = orders or [{'id':'one','quantity':1}]
    data['factory'] = factory or {}
    return data


CASES = {
    'one': scenario(),
    'two_orders': scenario([{'id':'a','quantity':2},{'id':'b','quantity':2,'release_s':60}]),
    'limited_worker': scenario([{'id':'a','quantity':4}],{'zund':3,'cutting_workers':1}),
    'multiple_machines': scenario([{'id':'a','quantity':4}],{'zund':2,'pfaff':2,'cutting_workers':2,'sewing_workers':2}),
    'batch': scenario([{'id':'a','quantity':4}],{'batch_size':2,'buffer_capacity':2}),
    'remainder': scenario([{'id':'a','quantity':3},{'id':'b','quantity':1}],{'batch_size':2,'buffer_capacity':2}),
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
            'segments':[{k:r[k] for k in ('kind','station','start_s','end_s','garments','machine','worker','cart')}
                        for r in run['rows']],
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
    close({k:result[k] for k in expected},expected)
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
    plan = run['template']; rates = run['scenario']['config']['resources']
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
        else:
            d['zund_kwh'] = elapsed/3600*rates['zund_idle_kw']
            d['equipment_eur'] = elapsed/3600*rates['zund_eur_h']
            vacuum=False
            for op in plan['operations']:
                if op['end_s'] > row['template_start_s']: break
                if op['kind']=='vacuum_on': vacuum=True
                if op['kind']=='vacuum_off': vacuum=False
            if vacuum: d['vacuum_kwh']=elapsed/3600*rates['vacuum_kw']
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
