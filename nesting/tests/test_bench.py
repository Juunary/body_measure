"""The benchmark instance and the common evaluator agree with the study's own geometry."""
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Polygon

from bench import report
from bench.evaluate import evaluate
from bench.instance import CUTTING_ZONE_MM, MODES, build, build_spec, deepnest_svgs, sparrow_json, svgnest_svg
from nesting.pattern_pdf import import_pdf
from nesting.pieces import save_pieces
from nesting.polygons import orient_coords
from nesting.search import Settings, nest

PDF = Path(__file__).resolve().parents[1] / 'examples' / 'schnittteile-hemd.pdf'


@pytest.fixture(scope='module')
def pieces_path(tmp_path_factory):
    meta, pieces = import_pdf(PDF)
    path = tmp_path_factory.mktemp('bench') / 'pieces.json'
    save_pieces(path, meta, pieces)
    return path


@pytest.fixture(scope='module')
def inst(pieces_path):
    return build(pieces_path)


def test_copies_are_mirrored_pairs_that_contain_the_cut_line(inst):
    assert len(inst.copies) == 9
    assert {c.key for c in inst.copies if c.mirrored} == {'VORDERTEIL-2', 'AERMEL-2', 'PASSE-2'}
    for c in inst.copies:
        piece = inst.pieces[c.piece_id]
        true = Polygon(orient_coords(np.asarray(piece.contour), c.mirrored, -90.0))
        packed = Polygon(c.tool)
        assert packed.is_valid and packed.exterior.is_ccw
        assert packed.covers(true)
        assert packed.area < 1.01 * true.area
        (x0, y0), (x1, y1) = orient_coords(np.asarray(piece.grain_line), c.mirrored, -90.0)
        assert abs(y1 - y0) < 1e-6 and abs(x1 - x0) > 100       # grain runs along the roll (+x)


def test_evaluator_reproduces_the_study_marker(inst):
    pieces = sorted(inst.pieces.values(), key=lambda p: (-p.area_mm2, p.id))
    result = nest(pieces, Settings(beam=2, window=2, iterations=5, time_limit_s=600.0))
    placements = {f"{p['piece_id']}-{p['copy']}": (p['rotation_deg'], p['y_mm'], inst.fabric_width_mm - p['x_mm'])
                  for p in result['placements']}
    ev = evaluate(inst, placements, '4rot')
    assert ev['valid'], ev['issues']
    assert ev['length_mm'] == pytest.approx(result['totals']['length_mm'], abs=0.05)
    assert ev['min_distance_mm'] == pytest.approx(result['totals']['min_distance_mm'], abs=0.01)
    assert not evaluate(inst, placements, '2rot')['valid'] or all(
        p['rotation_deg'] in MODES['2rot'] for p in result['placements'])


def test_evaluator_rejects_overlap_forbidden_rotation_and_missing_copies(inst):
    stacked = {c.key: (0.0, 0.0, 0.0) for c in inst.copies}
    ev = evaluate(inst, stacked, '4rot')
    assert not ev['valid'] and any('apart' in i for i in ev['issues'])
    # one copy per metre of roll, each pushed against the same selvedge: valid by construction
    spread = {c.key: (0.0, 1000.0 * i - c.tool_bounds[0], inst.margin_mm - c.tool_bounds[1])
              for i, c in enumerate(inst.copies)}
    ev = evaluate(inst, spread, '4rot')
    assert ev['valid'], ev['issues']
    assert ev['length_mm'] > 8000
    turned = dict(spread, **{inst.copies[0].key: (90.0, 0.0, 700.0)})
    assert not evaluate(inst, turned, '2rot')['valid']
    missing = dict(spread)
    missing.pop(inst.copies[-1].key)
    assert any('missing' in i for i in evaluate(inst, missing, '4rot')['issues'])


def test_tool_inputs_hold_the_same_instance(inst):
    data = sparrow_json(inst, '2rot', 'hemd')
    assert data['strip_height'] == inst.fabric_width_mm and len(data['items']) == 9
    for item in data['items']:
        ring = item['shape']['data']
        assert item['demand'] == 1 and item['allowed_orientations'] == [0.0, 180.0] and ring[0] == ring[-1]
    svg, offsets = svgnest_svg(inst, 3000.0)
    assert svg.count('<polygon') == 9 and 'id="bin"' in svg
    placed = [Polygon(c.tool + np.asarray(offsets[c.key])) for c in inst.copies]
    for i, a in enumerate(placed):                   # SVGnest would read overlapping parts as holes
        assert a.bounds[1] > inst.fabric_width_mm
        assert all(not a.intersects(b) for b in placed[i + 1:])


def test_bullmer_setup_gives_every_tool_the_full_working_width(pieces_path):
    wide = build_spec('bullmer1600', pieces_path)
    assert (wide.spec, wide.fabric_width_mm) == ('bullmer1600', 1600.0)
    assert sparrow_json(wide, '4rot', 'hemd')['strip_height'] == 1600.0
    assert 'height="1600.0"' in svgnest_svg(wide, 3000.0)[0]
    assert deepnest_svgs(wide, 3000.0, 1.0)[3] == pytest.approx(1600.0 - wide.gap_mm)


def test_report_names_markers_longer_than_the_cutting_zone():
    over = {'mode': '4rot', 'tool': 'svgnest', 'label': 'SVGnest', 'budget_s': 30, 'valid_runs': 3,
            'zone_fit_runs': 2, 'worst_mm': 2007.0}
    inside = dict(over, tool='ours', label='This study', zone_fit_runs=3, worst_mm=1658.0)
    lines = report._zone_findings({'instance': {'cutting_zone_mm': CUTTING_ZONE_MM}, 'rows': [over, inside]})
    assert len(lines) == 1 and 'SVGnest 30 s, 1 of 3 runs (worst 2007 mm)' in lines[0]
    lines = report._zone_findings({'instance': {'cutting_zone_mm': CUTTING_ZONE_MM}, 'rows': [inside]})
    assert 'every valid marker fits one 2000 mm' in lines[0] and '342 mm inside' in lines[0]
