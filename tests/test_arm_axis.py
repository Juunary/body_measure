"""The upper arm is cut perpendicular to its own axis (decision #46).

Gated on the generated SMPL bodies: the A pose hangs its arm 43 degrees
off vertical, where a horizontal cut is an oblique ellipse; the T pose has
no usable axis and must fall back, flagged, rather than cut along the arm."""
from pathlib import Path

import numpy as np
import pytest

from body_measure.adapters.mesh_file import MeshFileAdapter
from body_measure.canonicalize import canonicalize
from body_measure.landmarks.estimated import (
    ArmAxis, arm_loop_perpendicular, arm_loops_at, estimate_arm_axes,
    estimate_armpit_level, upper_arm_window)
from body_measure.measure.circumference import measure_circumference
from body_measure.measure.measurements import run_estimated_measurements

GENERATED = Path(__file__).resolve().parents[1] / "data" / "generated"
pytestmark = pytest.mark.skipif(
    not (GENERATED / "smpl_neutral0_apose.obj").exists(), reason="generated SMPL bodies absent")


@pytest.fixture(scope="module")
def apose():
    return canonicalize(MeshFileAdapter().load(GENERATED / "smpl_neutral0_apose.obj", unit="m"))


@pytest.fixture(scope="module")
def tpose():
    return canonicalize(MeshFileAdapter().load(GENERATED / "smpl_neutral0_tpose.obj", unit="m"))


def test_the_axis_follows_the_abducted_arm(apose):
    armpit = estimate_armpit_level(apose)
    axes = estimate_arm_axes(apose, armpit, None)
    assert set(axes) == {"left", "right"}
    for axis in axes.values():
        assert axis.usable and axis.n_loops >= 10
        assert 30.0 < axis.tilt_deg < 55.0            # SMPL's 50-degree abduction, seen from the loops
        assert axis.direction[1] < 0                  # points down the arm
        assert abs(np.linalg.norm(axis.direction) - 1.0) < 1e-9
    # the two arms lean away from each other
    assert axes["left"].direction[0] < 0 < axes["right"].direction[0]


def test_the_perpendicular_cut_is_shorter_than_the_oblique_one(apose):
    """An oblique section of a near-cylinder is longer than the true girth;
    at 43 degrees by tens of millimetres. The new value must be below the
    old horizontal maximum, and by a physically plausible margin."""
    armpit = estimate_armpit_level(apose)
    lo, hi, _ = upper_arm_window(apose, armpit, None)
    horizontal = max(
        measure_circumference(loops["right"], close_gap=False).selected_value_mm
        for level in np.arange(lo, hi, 6.0)
        for loops in [arm_loops_at(apose, float(level), armpit)[0]] if "right" in loops)
    measurements, landmarks = run_estimated_measurements(apose)
    value = measurements["upper_arm_girth"]
    assert value.method == "plane_slice_perpendicular_to_arm_axis"
    assert 0.80 * horizontal < value.selected_value_mm < 0.97 * horizontal
    assert any(f.startswith("arm_axis_tilt_") for f in value.quality)
    # and the ring can be redrawn where it was measured
    station = landmarks["upper_arm_girth_station_right"]
    axis = landmarks["arm_axis_right"]
    assert isinstance(axis, ArmAxis)
    s = float((station.position_mm - axis.origin_mm) @ axis.direction)
    loop = arm_loop_perpendicular(apose, axis, s)
    assert loop is not None
    redrawn = measure_circumference(loop, close_gap=not loop.closed).selected_value_mm
    assert abs(redrawn - value.selected_value_mm) < 1.0


def test_a_t_pose_falls_back_to_the_horizontal_cut_and_says_so(tpose):
    armpit = estimate_armpit_level(tpose)
    axes = estimate_arm_axes(tpose, armpit, None)
    assert all(not axis.usable for axis in axes.values())
    measurements, landmarks = run_estimated_measurements(tpose)
    value = measurements["upper_arm_girth"]
    assert value.method == "plane_slice"
    assert "arm_axis_unresolved_horizontal_slice_fallback" in value.quality


def test_the_sleeve_opening_uses_the_same_axis(apose):
    from body_measure.garment_prototypes import run_prototypes
    measurements, landmarks = run_estimated_measurements(apose)
    proto = run_prototypes(apose, measurements, landmarks)["sleeve_opening_girth"]
    assert proto.available and proto.plane is not None
    assert "perpendicular_to_arm_axis" in proto.note
    assert proto.value < measurements["upper_arm_girth"].selected_value_mm
