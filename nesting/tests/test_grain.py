"""The grain check: along, across and tilted grain lines, allowed rotations and left/right copies."""
from nesting.grain import check_grain, grain_state


def placement(piece, copy, rotation, mirrored, line):
    return {'piece_id': piece, 'copy': copy, 'rotation_deg': rotation, 'mirrored': mirrored, 'grain_line': line}


def test_grain_state_tells_along_across_and_tilted():
    assert grain_state([[10, 0], [10, 300]])[0] == 'along'
    assert grain_state([[10, 300], [10, 0]])[0] == 'along'          # a grain line has no direction
    assert grain_state([[0, 5], [300, 5]])[0] == 'across'
    state, deviation = grain_state([[0, 0], [100, 100]])
    assert state == 'off' and abs(deviation - 45.0) < 1e-9
    assert grain_state([[0, 0], [1, 300]])[0] == 'along'            # 0.19 deg is inside the tolerance


def test_check_grain_reports_tilts_rotations_and_unmirrored_pairs():
    good = [placement('A', 1, 0.0, False, [[0, 0], [0, 100]]), placement('A', 2, 90.0, True, [[0, 0], [100, 0]])]
    result = check_grain(good, (0.0, 90.0, 180.0, 270.0))
    assert (result['along'], result['across'], result['off'], result['problems']) == (1, 1, 0, [])
    bad = [placement('A', 1, 45.0, False, [[0, 0], [70, 70]]), placement('A', 2, 0.0, False, [[0, 0], [0, 100]])]
    problems = check_grain(bad, (0.0, 180.0))['problems']
    assert any('deg away' in p for p in problems)
    assert any('not in the allowed set' in p for p in problems)
    assert any('plain and one mirrored' in p for p in problems)
