"""Seam dependencies, dimensional feed, playback and scope regressions."""
import copy
import json
from pathlib import Path
import pytest
from studio.simulation import build_plan, snapshot
from studio.simulation.playback import Playback
from studio.simulation.sewing import schedule
from studio.simulation.config import SimulationConfig


@pytest.fixture
def config():
    return json.loads((Path(__file__).parents[1]/'examples/cutting-config.json').read_text())


def test_sewing_follows_all_pickups_and_only_finishes_after_trim(config):
    plan=build_plan({},config)
    ops=plan['operations']
    start=next(o['start_s'] for o in ops if o['kind']=='transfer_to_sewing')
    assert start==max(o['end_s'] for o in ops if o['kind']=='pickup')
    assert len(plan['sewing_seams'])==18
    at_cut=snapshot(plan,start)
    assert at_cut['cutting_complete'] and not at_cut['finished']
    assert set(at_cut['pieces'].values())=={'collected'}
    for o in ops:
        if o['kind']=='stitch':
            halfway=snapshot(plan,(o['start_s']+o['end_s'])/2)
            assert halfway['sewing']['seams'][o['seam_id']]=='sewing'
            end=snapshot(plan,o['end_s'])
            assert end['sewing']['seams'][o['seam_id']]=='stitched'
        if o['kind']=='thread_trim':
            assert snapshot(plan,o['end_s'])['sewing']['seams'][o['seam_id']]=='sewn'
    final=snapshot(plan,plan['totals']['duration_s'])
    assert final['sewing_complete'] and final['metrics']['seams_complete']==18
    assert final['metrics']['stitches']==plan['totals']['stitches']
    assert final['metrics']['sewn_length_mm']==pytest.approx(plan['totals']['sewn_length_mm'])
    assert final['machines']['pfaff']=='complete' and final['machines']['qc']=='downstream'
    assert final['metrics']['cut_pieces']==final['metrics']['collected_pieces']==9


def test_stitch_rate_and_length_change_time_not_pattern(config):
    base=build_plan({},config)
    fast=build_plan({},{**config,'machine':{'stitches_per_min':1200}})
    dense=build_plan({},{**config,'machine':{'stitch_length_mm':2}})
    assert base['pieces']==fast['pieces']==dense['pieces']
    assert base['totals']['stitches']==fast['totals']['stitches']<dense['totals']['stitches']
    assert fast['totals']['sewing_duration_s']<base['totals']['sewing_duration_s']<dense['totals']['sewing_duration_s']
    longer=build_plan({},{**config,'design':{'length_mm':760,'shrink_pct':5}})
    assert longer['totals']['sewn_length_mm']>base['totals']['sewn_length_mm']


def test_cut_only_compatibility_and_rewind(config):
    cut=build_plan({},{**config,'scope':'through_cutting'})
    end=snapshot(cut,cut['totals']['duration_s'])
    assert end['finished'] and end['cutting_complete'] and not end['sewing_complete']
    assert end['machines']['pfaff']=='downstream' and not cut['sewing_seams']
    plan=build_plan({},config)
    player=Playback(plan,clock=lambda:0)
    stitch=next(o for o in plan['operations'] if o['kind']=='stitch')
    time=(stitch['start_s']+stitch['end_s'])/2
    first=player.control('seek',time)
    player.control('seek',plan['totals']['duration_s'])
    again=player.control('seek',time)
    assert first['sewing']==again['sewing'] and first['pieces']==again['pieces']
    assert first['metrics']==again['metrics']
    player.control('seek',0)
    assert set(player.get()['sewing']['seams'].values())=={'waiting'}
    assert player.get()['metrics']['stitches']==0


def test_bad_paired_seam_stops_plan(config):
    plan=build_plan({},config)
    pieces=copy.deepcopy(plan['pieces'])
    next(p for p in pieces if p['id']=='cuff_left')['seams']['attach'][1][0]+=30
    with pytest.raises(ValueError,match='seam mismatch'):
        schedule(pieces,SimulationConfig(**config),[],0,0)


def test_every_feed_side_is_inside_its_piece(config):
    from shapely.geometry import Polygon,LineString
    plan=build_plan({},config)
    shapes={p['id']:Polygon(p['contour']) for p in plan['pieces']}
    for seam in plan['sewing_seams']:
        for side in seam['sides']:
            assert shapes[side['piece_id']].covers(LineString(side['points']))
