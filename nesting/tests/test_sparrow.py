"""The sparrow engine: its frame matches the study's, and a short real run keeps every rule."""
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from nesting import sparrow
from nesting.pattern_pdf import import_pdf
from nesting.polygons import rotate_coords
from nesting.search import Settings

PDF = Path(__file__).resolve().parents[1] / 'examples' / 'schnittteile-hemd.pdf'
FOUR = (0.0, 90.0, 180.0, 270.0)


def built():
    try:
        sparrow.find_binary()
        return True
    except FileNotFoundError:
        return False


@pytest.fixture(scope='module')
def pieces():
    return import_pdf(PDF)[1]


def test_instance_carries_the_grain_rule_and_mirrored_copies(pieces):
    settings = Settings(rotations=FOUR)
    instance, copies = sparrow.build_instance(pieces, settings)
    assert len(instance['items']) == len(copies) == 9
    assert instance['strip_height'] == settings.fabric_width_mm
    assert all(item['allowed_orientations'] == list(FOUR) for item in instance['items'])
    assert sorted(piece.id for piece, _, mirrored in copies if mirrored) == ['AERMEL', 'PASSE', 'VORDERTEIL']


def test_a_sparrow_placement_maps_onto_the_true_cut_line(pieces):
    """Place every packed polygon by hand in sparrow's frame: the study's record must lie inside it."""
    settings = Settings(rotations=FOUR)
    instance, copies = sparrow.build_instance(pieces, settings)
    placed, packed = [], []
    for i, item in enumerate(instance['items']):
        rotation, t = FOUR[i % 4], (2000.0 * i + 1000.0, 500.0)
        placed.append({'item_id': i, 'transformation': {'rotation': rotation, 'translation': list(t)}})
        packed.append(rotate_coords(item['shape']['data'], rotation) + t)
    records = sparrow.to_placements({'solution': {'layout': {'placed_items': placed}}}, copies, settings)
    width = settings.fabric_width_mm
    for i, (piece, copy, mirrored) in enumerate(copies):
        record = next(r for r in records if r['piece_id'] == piece.id and r['copy'] == copy)
        shift = record['y_mm'] - placed[i]['transformation']['translation'][0]      # the push to the roll start
        outline = Polygon([(width - y, x + shift) for x, y in packed[i]])           # sparrow frame -> study frame
        true = Polygon(record['contour'])
        assert outline.buffer(1e-6).covers(true) and outline.area < 1.02 * true.area
        assert record['rotation_deg'] == FOUR[i % 4] and record['mirrored'] == mirrored


@pytest.mark.skipif(not built(), reason='sparrow is not built (python -m bench.fetch_tools)')
def test_a_short_sparrow_run_keeps_grain_gap_and_copies(pieces, tmp_path):
    settings = Settings(rotations=(0.0, 180.0), time_limit_s=4.0, seed=0)
    result = sparrow.nest_with_sparrow(pieces, settings, tmp_path / 'sparrow')
    totals, grain = result['totals'], result['grain']
    assert totals['placements'] == 9 and totals['min_distance_mm'] >= settings.gap_mm - 0.05
    assert (grain['across'], grain['off'], grain['problems']) == (0, 0, [])
    assert totals['length_mm'] >= totals['lower_bound_length_mm']
