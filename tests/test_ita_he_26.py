"""The ITA_HE_26 shirt chart, read from body to size.

Pinned: every row maps back to itself; chest and neck choose the size
and nothing else does; a body off the chart is refused; without a neck
the paired sizes are flagged as unresolved; and the chest bias is
reported, never applied."""
import pytest

from body_measure.charts import ita_he_26 as c


@pytest.mark.parametrize("size", c.SIZES)
def test_every_row_maps_back_to_itself(size):
    assert c.nearest_size(c.body_targets(size)).size == size


def test_lengths_and_widths_never_move_the_size():
    base = c.body_targets(50)
    far = {**base, "back_length": base["back_length"] - 200,
           "across_back_shoulder_width": base["across_back_shoulder_width"] - 200}
    out = c.nearest_size(far)
    assert out.size == 50
    assert out.residual_steps["back_length"] < -10


def test_a_body_off_the_chart_is_refused():
    out = c.nearest_size({"chest_circumference": 700.0, "neck_circumference": 280.0})
    assert out.size is None and "off_chart" in out.flags


def test_no_chest_no_size():
    out = c.nearest_size({"neck_circumference": 380.0})
    assert out.size is None


def test_without_a_neck_the_pairs_are_flagged():
    out = c.nearest_size({"chest_circumference": c.body_targets(44)["chest_circumference"]})
    assert out.size in (44, 46)
    assert "neck_unusable_paired_sizes_unresolved" in out.flags


def test_the_chest_bias_is_reported_not_applied():
    t = c.body_targets(52)
    out = c.nearest_size({**t, "chest_circumference": t["chest_circumference"] + c.CHEST_BIAS_MM})
    assert out.size_if_chest_bias_holds == 52
    assert out.size in (52, 54)


def test_an_unusable_key_is_ignored():
    t = c.body_targets(48)
    out = c.nearest_size({**t, "neck_circumference": 999.0},
                         {"neck_circumference": False})
    assert "neck_circumference" not in out.keys_used
