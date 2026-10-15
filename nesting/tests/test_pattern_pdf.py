"""The importer reads the shirt sheet into the documented piece contract."""
import json
from pathlib import Path

import pytest
from shapely.geometry import LineString, Polygon

from nesting.pattern_pdf import import_pdf, pieces_svg
from nesting.pieces import load_pieces, rotate_points, save_pieces, transform_points

PDF = Path(__file__).resolve().parents[1] / 'examples' / 'schnittteile-hemd.pdf'
EXPECTED = {'RUECKEN': 1, 'VORDERTEIL': 2, 'AERMEL': 2, 'PASSE': 2, 'OBERKRAGEN': 1, 'UNTERKRAGEN': 1}


@pytest.fixture(scope='module')
def imported():
    return import_pdf(PDF)


def test_shapes_quantities_and_exclusions(imported):
    meta, pieces = imported
    assert {p.id: p.quantity for p in pieces} == EXPECTED
    assert sum(p.quantity for p in pieces) == 9
    assert meta['excluded'] == ['SCHABLONE']
    assert meta['unassigned_marks'] == 0
    assert abs(meta['scale_check_mm'] - 100.0) <= 0.2
    assert meta['page_size_mm'][0] == pytest.approx(1007.0, abs=0.5)


def test_grain_is_axis_aligned_and_vertical_locally(imported):
    _, pieces = imported
    for p in pieces:
        assert p.grain_angle_deg in (0.0, 90.0)
        (x0, y0), (x1, y1) = p.grain_line
        assert x0 == pytest.approx(x1, abs=1e-6) and y1 > y0 + 100
        assert p.bounds[0] == pytest.approx(0.0, abs=1e-6) and p.bounds[1] == pytest.approx(0.0, abs=1e-6)
    by_id = {p.id: p for p in pieces}
    assert by_id['RUECKEN'].grain_angle_deg == 90.0 and by_id['OBERKRAGEN'].grain_angle_deg == 0.0
    # a collar is drawn lying flat; in the local frame its grain runs along the long side (+y)
    assert by_id['OBERKRAGEN'].height_mm > by_id['OBERKRAGEN'].width_mm * 3


def test_contours_are_valid_and_contain_their_net_line(imported):
    _, pieces = imported
    for p in pieces:
        cut = Polygon(p.contour)
        assert cut.is_valid and cut.exterior.is_ccw
        net = Polygon(p.seam_line)
        assert net.is_valid and cut.buffer(0.5).covers(net)
        assert 0.6 * cut.area < net.area < cut.area
    sizes = {p.id: (round(p.width_mm), round(p.height_mm)) for p in pieces}
    assert sizes['RUECKEN'] == (602, 759) and sizes['VORDERTEIL'] == (369, 793)


def test_marks_are_assigned(imported):
    _, pieces = imported
    kinds = {p.id: {} for p in pieces}
    for p in pieces:
        for m in p.marks:
            kinds[p.id][m['kind']] = kinds[p.id].get(m['kind'], 0) + 1
            assert Polygon(p.contour).buffer(6.0).covers(LineString(m['points']))
    assert sum(k.get('notch', 0) for k in kinds.values()) == 42
    assert kinds['AERMEL'].get('fold') == 1
    assert kinds['OBERKRAGEN'].get('fold') == 2 and kinds['OBERKRAGEN'].get('centre') == 1
    assert kinds['UNTERKRAGEN'].get('fold') == 2 and kinds['UNTERKRAGEN'].get('centre') == 1


def test_json_round_trip_and_svg(imported, tmp_path):
    meta, pieces = imported
    path = tmp_path / 'pieces.json'
    save_pieces(path, meta, pieces)
    meta2, pieces2 = load_pieces(path)
    assert meta2['excluded'] == meta['excluded']
    for before, after in zip(pieces, pieces2):
        a, b = before.to_dict(), after.to_dict()
        for key in ('id', 'quantity', 'flags', 'grain_angle_deg', 'contour', 'seam_line', 'grain_line', 'marks'):
            assert a[key] == b[key], key
        assert b['area_mm2'] == pytest.approx(a['area_mm2'], abs=0.05)
    # a second round trip is exact: the file is the canonical form
    save_pieces(path, meta2, pieces2)
    assert [p.to_dict() for p in load_pieces(path)[1]] == [p.to_dict() for p in pieces2]
    svg = pieces_svg(pieces, 1007.0)
    assert svg.count('<polygon') == 9 and 'id="bin"' in svg
    assert json.loads(json.dumps([p.to_dict() for p in pieces]))


def test_exact_quarter_turns_and_transform_order():
    assert rotate_points([[1, 0]], 90) == [[0, 1]]
    assert rotate_points([[1, 0]], 180) == [[-1, 0]]
    assert rotate_points([[1, 0]], 270) == [[0, -1]]
    assert rotate_points([[3, 4]], 360) == [[3.0, 4.0]]
    # mirror first (x -> -x), then rotate 90, then translate
    assert transform_points([[2, 1]], True, 90, 10, 20) == [[10 - 1, 20 - 2]]
    assert transform_points([[2, 1]], False, 90, 10, 20) == [[10 - 1, 20 + 2]]
