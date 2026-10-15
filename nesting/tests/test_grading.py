"""Piece scaling used by the size study."""
from pathlib import Path

import pytest

from nesting.grading import grade, scale_piece
from nesting.pieces import load_pieces

FIXTURE = Path(__file__).parents[1] / 'examples' / 'hemd-pieces.json'


@pytest.fixture(scope='module')
def pieces():
    return load_pieces(FIXTURE)[1]


def test_identity_keeps_every_piece(pieces):
    assert [p.to_dict() for p in grade(pieces, {})] == [p.to_dict() for p in pieces]


def test_scaling_changes_area_and_box_but_not_structure(pieces):
    back = next(p for p in pieces if p.id == 'RUECKEN')
    g = scale_piece(back, 1.1, 0.9)
    assert g.area_mm2 == pytest.approx(back.area_mm2 * 0.99)
    assert g.width_mm == pytest.approx(back.width_mm * 1.1)
    assert g.height_mm == pytest.approx(back.height_mm * 0.9)
    assert g.bounds[0] == pytest.approx(0, abs=1e-6) and g.bounds[1] == pytest.approx(0, abs=1e-6)
    assert g.grain_line[0][0] == pytest.approx(g.grain_line[1][0])
    assert len(g.marks) == len(back.marks) and g.quantity == back.quantity


def test_unknown_piece_or_bad_factor_is_rejected(pieces):
    with pytest.raises(ValueError):
        grade(pieces, {'NOPE': (1, 1)})
    with pytest.raises(ValueError):
        scale_piece(pieces[0], 0, 1)
