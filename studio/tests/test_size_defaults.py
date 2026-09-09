import copy
import json
from pathlib import Path
import pytest
from studio.simulation import build_plan, SimulationConfig
from studio.simulation.inputs import inspect_inputs, InputError


def document():
    config=json.loads((Path(__file__).parents[1]/'examples/cutting-config.json').read_text())
    values={k:{'value':v['value'],'unit':v['unit'],'flags':['prototype']} for k,v in config['manual'].items()}
    values['front_back_width']={'value':None,'unit':'mm','flags':['arms_merged_at_chest_level']}
    return {'units':'mm','meta':{'garment_prototypes':values,'size':{'chart':'en13402-women','size':'XS'}}}


def test_assigned_size_fills_missing_balance_preserves_original():
    doc=document();original=copy.deepcopy(doc)
    plan=build_plan(doc)
    rows={r['key']:r for r in plan['inputs']}
    balance=rows['front_back_width']
    assert balance['value']==0 and balance['source']=='size_preset' and balance['usable']
    assert 'en13402-women / XS' in balance['auto_basis']
    assert balance['original']['value'] is None and 'arms_merged_at_chest_level' in balance['flags']
    assert rows['chest_circumference']['value']==1000
    assert rows['chest_circumference']['source']=='prototype'
    assert doc==original


def test_size_only_can_build_research_draft_and_manual_wins():
    doc={'units':'mm','sizing':{'chart':'en13402-women','size':'XS'}}
    plan=build_plan(doc)
    assert plan['inputs'][0]['source']=='size_chart'
    assert all(r['usable'] for r in plan['inputs'])
    cfg=SimulationConfig(manual={'front_back_width':{'value':10,'unit':'mm','reason':'user correction'}})
    row=next(r for r in inspect_inputs(doc,cfg) if r['key']=='front_back_width')
    assert row['value']==10 and row['source']=='manual' and row['auto_basis'] is None


@pytest.mark.parametrize('size',[None, 'not-a-size'])
def test_no_assigned_size_does_not_invent_values(size):
    doc=document();doc['meta']['size']['size']=size
    with pytest.raises(InputError,match='front_back_width'):build_plan(doc)


def test_wrong_units_are_not_hidden_by_size_defaults():
    doc=document();doc['meta']['garment_prototypes']['front_back_width']['unit']='cm'
    with pytest.raises(InputError):build_plan(doc)
    doc=document();doc['meta']['garment_prototypes']['front_back_width']['value']=float('nan')
    with pytest.raises(InputError):build_plan(doc)


def test_studio_size_assignment_reaches_shared_resolver():
    from types import SimpleNamespace
    from studio.simulation.service import document_for, input_view
    job=SimpleNamespace(simulation_document=None,params={},measurements={},prototypes={},
                        size_view={'chart':'en13402-women','size':'XS'})
    assert document_for(job)['sizing']==job.size_view
    row=next(r for r in input_view(job) if r['key']=='front_back_width')
    assert row['value']==0 and row['usable'] and row['source']=='size_preset'
