"""Gap-closure tiers: AND-bounded accept, manual_review cap, reject-means-
null (never fall back to a closed arm loop)."""
import numpy as np
import pytest

from body_measure.measure.circumference import measure_circumference
from body_measure.measure.slicing import (
    SliceLoop,
    gap_disposition,
    select_torso_loop,
)


def arc_loop(radius_mm: float, gap_deg: float, center=(0.0, 0.0), n=180) -> SliceLoop:
    """Open circular arc in the z=0 plane with a missing sector."""
    angles = np.linspace(
        np.deg2rad(gap_deg / 2), 2 * np.pi - np.deg2rad(gap_deg / 2), n
    )
    pts2d = np.column_stack(
        [center[0] + radius_mm * np.cos(angles), center[1] + radius_mm * np.sin(angles)]
    )
    points = np.column_stack([pts2d[:, 0], np.zeros(n), pts2d[:, 1]])
    return SliceLoop(points=points, points2d=pts2d, closed=False)


def circle_loop(radius_mm: float, center=(0.0, 0.0), n=180) -> SliceLoop:
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts2d = np.column_stack(
        [center[0] + radius_mm * np.cos(angles), center[1] + radius_mm * np.sin(angles)]
    )
    points = np.column_stack([pts2d[:, 0], np.zeros(n), pts2d[:, 1]])
    return SliceLoop(points=points, points2d=pts2d, closed=True)


def test_a_small_hole_on_a_large_torso_is_accepted_as_degraded():
    # r=160 -> path ~1005 mm; 5 deg gap -> chord ~14 mm, ratio ~0.014
    loop = arc_loop(160.0, 5.0)
    disposition, chord, ratio = gap_disposition(loop)
    assert disposition == "accepted"
    assert chord <= 30.0 and ratio <= 0.05


def test_the_and_condition_blocks_a_30mm_chord_on_a_small_neck_path():
    # r=55 -> path ~345 mm; 30 deg gap -> chord ~28 mm (<=30) but ratio ~0.083
    loop = arc_loop(55.0, 30.0)
    disposition, chord, ratio = gap_disposition(loop)
    assert chord <= 30.0
    assert ratio > 0.05
    assert disposition == "manual_review"  # an OR-rule would have accepted it


def test_a_large_absolute_chord_needs_manual_review_even_at_low_ratio():
    # r=700 -> path ~4.3 m; 11 deg gap -> chord ~134 mm, ratio ~0.031:
    # low ratio alone must not make a 13 cm hole acceptable
    loop = arc_loop(700.0, 11.0)
    disposition, chord, ratio = gap_disposition(loop)
    assert ratio <= 0.05
    assert chord > 120.0
    assert disposition == "rejected"


def test_a_wide_open_arc_is_rejected():
    loop = arc_loop(160.0, 120.0)  # chord ~277 mm, ratio ~0.25
    assert gap_disposition(loop)[0] == "rejected"


def test_rejected_torso_candidate_never_falls_back_to_a_closed_arm_loop():
    torso = arc_loop(150.0, 120.0)          # axis-containing but badly holed
    arm = circle_loop(40.0, center=(400.0, 0.0))
    selection = select_torso_loop([torso, arm], axis2d=np.zeros(2))
    assert selection is not None
    assert selection.loop is torso          # identified first...
    assert selection.disposition == "rejected"  # ...then judged, not swapped
    assert "gap_rejected" in selection.quality_flags


def test_manual_review_selection_carries_low_confidence_and_gap_info():
    loop = arc_loop(160.0, 25.0)  # chord ~69 mm, ratio ~0.066 -> manual_review
    selection = select_torso_loop([loop], axis2d=np.zeros(2))
    assert selection.disposition == "manual_review"
    assert selection.confidence <= 0.3
    assert "gap_closed_manual_review" in selection.quality_flags
    assert selection.gap_chord_mm > 0 and 0 < selection.gap_ratio < 0.2


def test_close_gap_measurement_refuses_a_rejected_loop():
    loop = arc_loop(160.0, 120.0)
    circ = measure_circumference(loop, close_gap=True)
    assert circ.selected_value_mm is None


def test_accepted_gap_closure_approximates_the_full_circle():
    loop = arc_loop(160.0, 5.0)
    circ = measure_circumference(loop, close_gap=True)
    assert circ.selected_value_mm == pytest.approx(2 * np.pi * 160.0, rel=5e-3)
