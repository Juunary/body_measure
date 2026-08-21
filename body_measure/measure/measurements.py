"""Compose slicing/circumference primitives into spec measurements."""
from __future__ import annotations

import numpy as np
import trimesh

from ..canonicalize import body_axis_point
from ..landmarks.base import Landmark
from ..result import MeasurementValue
from .circumference import clipped_circumference_xz, measure_circumference
from .slicing import project_axis_to_plane, select_torso_loop, slice_mesh

_UP = np.array([0.0, 1.0, 0.0])

# chest search reaches this far above the arm-merge level (stature-relative)
_CHEST_ABOVE_MERGE = 0.10


def circumference_at_height(mesh: trimesh.Trimesh, height_mm: float) -> MeasurementValue:
    """Horizontal torso circumference at a canonical height."""
    axis_xz = body_axis_point(mesh)
    origin = np.array([0.0, height_mm, 0.0])
    loops = slice_mesh(mesh, origin, _UP)
    selection = select_torso_loop(loops, project_axis_to_plane(axis_xz, origin, _UP))
    if selection is None:
        return MeasurementValue(method="plane_slice", quality=["no_torso_candidate_at_height"])
    gap = (
        {"chord_mm": selection.gap_chord_mm, "ratio": selection.gap_ratio}
        if not selection.loop.closed
        else None
    )
    if selection.disposition == "rejected":
        # identified torso candidate failed the gap tiers: null, never a
        # different loop (docs/decisions.md — no re-shopping after reject)
        return MeasurementValue(
            method="plane_slice",
            quality=selection.quality_flags or ["gap_rejected"],
            disposition="rejected",
            gap=gap,
        )
    circ = measure_circumference(selection.loop, close_gap=not selection.loop.closed)
    if circ.selected_value_mm is None:
        return MeasurementValue(
            method="plane_slice",
            quality=(circ.quality_flags + selection.quality_flags) or ["measurement_failed"],
            disposition="rejected",
            gap=gap,
        )
    return MeasurementValue(
        raw_contour_mm=circ.raw_contour_mm,
        taut_tape_hull_mm=circ.taut_tape_hull_mm,
        selected_value_mm=circ.selected_value_mm,
        selection_method=circ.selection_method,
        method="plane_slice",
        quality=(circ.quality_flags + selection.quality_flags) or ["ok"],
        disposition=selection.disposition,
        gap=gap,
    )


def measure_circumference_at_landmark(mesh: trimesh.Trimesh, landmark: Landmark) -> MeasurementValue:
    value = circumference_at_height(mesh, float(landmark.position_mm[1]))
    if landmark.quality_flags:
        value.quality = [f for f in value.quality if f != "ok"] + landmark.quality_flags
    return value


# Slice-1 name kept for callers/tests
measure_waist_circumference = measure_circumference_at_landmark


def measure_chest_circumference(
    mesh: trimesh.Trimesh, waist: Landmark, armpit: Landmark | None
) -> tuple[MeasurementValue, Landmark | None]:
    """Maximum torso girth between waist and shoulder top.

    Real subjects often stand with arms touching the torso, so the true
    chest/bust level can sit ABOVE the height where the slice loops merge
    (seen on Texel Part 1: merge at 0.69 h, bust at 0.72 h). Above the
    merge, the arm cross-sections are clipped away at the torso x-range
    taken at the armpit level — a tape approximation, always flagged.
    """
    height = float(mesh.bounds[1][1])
    axis_xz = body_axis_point(mesh)
    waist_y = float(waist.position_mm[1])

    lateral = lo_t = hi_t = None
    lateral_flags: list[str] = []
    if armpit is not None:
        from ..landmarks.estimated import body_lateral_axis

        armpit_y = float(armpit.position_mm[1])
        lateral, lateral_flags = body_lateral_axis(mesh, armpit_y)
        origin = np.array([0.0, armpit_y, 0.0])
        selection = select_torso_loop(
            slice_mesh(mesh, origin, _UP), project_axis_to_plane(axis_xz, origin, _UP)
        )
        if selection is not None:
            t = selection.loop.points[:, [0, 2]] @ lateral
            lo_t, hi_t = float(t.min()), float(t.max())
        hi = min(armpit_y + _CHEST_ABOVE_MERGE * height, 0.92 * height)
    else:
        hi = 0.78 * height

    samples: list[tuple[float, "MeasurementValue"]] = []
    for level in np.arange(waist_y + 10.0, hi, 10.0):
        origin = np.array([0.0, float(level), 0.0])
        loops = slice_mesh(mesh, origin, _UP)
        selection = select_torso_loop(loops, project_axis_to_plane(axis_xz, origin, _UP))
        if selection is None:
            continue
        if selection.disposition == "rejected":
            continue  # rejected torso candidate: skip the height, never re-shop
        n_closed = sum(1 for lp in loops if lp.closed)
        if n_closed >= 3 or lo_t is None:
            circ = measure_circumference(selection.loop, close_gap=not selection.loop.closed)
        else:  # arms merged into the torso loop — clip them away
            circ = clipped_circumference_xz(
                selection.loop.points[:, [0, 2]], lo_t, hi_t, lateral=lateral
            )
        if circ.selected_value_mm is None:
            continue
        value = MeasurementValue(
            raw_contour_mm=circ.raw_contour_mm,
            taut_tape_hull_mm=circ.taut_tape_hull_mm,
            selected_value_mm=circ.selected_value_mm,
            selection_method=circ.selection_method,
            method="plane_slice",
            quality=(circ.quality_flags + selection.quality_flags) or ["ok"],
            disposition=selection.disposition,
            gap=(
                {"chord_mm": selection.gap_chord_mm, "ratio": selection.gap_ratio}
                if not selection.loop.closed
                else None
            ),
        )
        samples.append((float(level), value))

    if not samples:
        return MeasurementValue(method="plane_slice", quality=["chest_estimation_failed"]), None

    idx = max(range(len(samples)), key=lambda i: samples[i][1].selected_value_mm)
    level, value = samples[idx]
    flags = [f for f in value.quality if f != "ok"] + lateral_flags
    confidence = 0.7
    if idx in (0, len(samples) - 1):
        flags.append("maximum_at_search_boundary")
        confidence = 0.4
    if armpit is None:
        flags.append("armpit_not_detected_window_is_stature_relative")
        confidence = min(confidence, 0.5)
    value.quality = flags or ["ok"]

    landmark = Landmark(
        name="chest_level",
        position_mm=np.array([axis_xz[0], level, axis_xz[1]]),
        confidence=confidence,
        method="maximum_torso_circumference_arm_clipped",
        quality_flags=flags,
    )
    return value, landmark


def run_estimated_circumferences(mesh: trimesh.Trimesh) -> tuple[dict, dict]:
    """Estimated pathway for the three circumference measurements.

    Returns (measurements, landmarks): spec-named MeasurementValue entries
    for whatever could be estimated, plus the landmarks used.
    """
    from ..landmarks.estimated import (
        estimate_armpit_level,
        estimate_neck_base_level,
        estimate_waist_level,
    )

    measurements: dict[str, MeasurementValue] = {}
    landmarks: dict[str, Landmark] = {}

    waist = estimate_waist_level(mesh)
    if waist is None:
        measurements["waist_circumference"] = MeasurementValue(
            method="plane_slice", quality=["waist_estimation_failed"]
        )
        return measurements, landmarks
    landmarks["waist_level"] = waist
    measurements["waist_circumference"] = measure_circumference_at_landmark(mesh, waist)

    armpit = estimate_armpit_level(mesh)
    if armpit is not None:
        landmarks["armpit_level"] = armpit

    chest_value, chest_landmark = measure_chest_circumference(mesh, waist, armpit)
    measurements["chest_circumference"] = chest_value
    if chest_landmark is not None:
        landmarks["chest_level"] = chest_landmark

    neck = estimate_neck_base_level(mesh, armpit)
    if neck is None:
        measurements["neck_circumference"] = MeasurementValue(
            method="plane_slice", quality=["neck_estimation_failed"]
        )
    else:
        landmarks["neck_base_level"] = neck
        measurements["neck_circumference"] = measure_circumference_at_landmark(mesh, neck)

    # Upper arm girth needs no front/back orientation — it is a girth, not a
    # back-neck-dependent path — so it belongs here rather than with the lengths.
    wrist = None
    if armpit is not None:
        from ..landmarks.estimated import estimate_wrist_points

        wrist_left, wrist_right = estimate_wrist_points(mesh, armpit)
        wrist = wrist_right if wrist_right is not None else wrist_left
        if wrist is not None:
            landmarks[wrist.name] = wrist
    side = "right" if (wrist is None or wrist.name.endswith("right")) else "left"
    measurements["upper_arm_girth"] = measure_upper_arm_girth(
        mesh, armpit, wrist, side=side
    )

    return measurements, landmarks


def measure_upper_arm_girth(
    mesh: trimesh.Trimesh,
    armpit: Landmark | None,
    wrist: Landmark | None,
    side: str = "right",
    step_mm: float = 6.0,
) -> MeasurementValue:
    """Widest girth of the upper arm — the sleeve-width measurement a short
    sleeve is built around. Same plane-slice primitive as the torso girths,
    applied to the arm loop instead of the torso loop."""
    from ..landmarks.estimated import arm_loops_at, upper_arm_window

    if armpit is None:
        return MeasurementValue(
            method="plane_slice", quality=["armpit_not_detected"]
        )
    lo, hi, window_flags = upper_arm_window(mesh, armpit, wrist)
    best: tuple[float, MeasurementValue] | None = None
    axis_flags: list[str] = []
    for level in np.arange(lo, hi, step_mm):
        loops, flags = arm_loops_at(mesh, float(level), armpit)
        axis_flags = flags
        loop = loops.get(side)
        if loop is None:
            continue
        circ = measure_circumference(loop, close_gap=not loop.closed)
        if circ.selected_value_mm is None:
            continue
        value = MeasurementValue(
            raw_contour_mm=circ.raw_contour_mm,
            taut_tape_hull_mm=circ.taut_tape_hull_mm,
            selected_value_mm=circ.selected_value_mm,
            selection_method=circ.selection_method,
            method="plane_slice",
            quality=circ.quality_flags,
            disposition="accepted",
        )
        if best is None or circ.selected_value_mm > best[0]:
            best = (circ.selected_value_mm, value)

    if best is None:
        return MeasurementValue(
            method="plane_slice",
            quality=["no_arm_loop_in_upper_arm_window"] + window_flags + axis_flags,
        )
    value = best[1]
    flags = [f for f in value.quality if f != "ok"] + window_flags + axis_flags
    value.quality = flags or ["ok"]
    return value


#: Flags that mean the path was walked successfully but not between the
#: landmarks it was supposed to connect. The number is real geometry and
#: is kept, but it is not the measurement, so it never lands as accepted.
_PATH_NOT_TRUSTED = {
    "surface_path_detour",
    "waypoint_off_main_surface",
    "shoulder_vertical_asymmetry",
}


def _length_value(length: float | None, flags: list[str], method: str) -> MeasurementValue:
    if length is None:
        return MeasurementValue(method=method, quality=flags or ["path_failed"])
    return MeasurementValue(
        selected_value_mm=float(length),
        method=method,
        quality=flags or ["ok"],
        disposition=(
            "manual_review" if set(flags) & _PATH_NOT_TRUSTED else "accepted"
        ),
    )


def run_estimated_measurements(mesh: trimesh.Trimesh) -> tuple[dict, dict]:
    """Full estimated pathway: three circumferences + three surface-path
    lengths, sharing one landmark set and one edge graph."""
    from ..landmarks.estimated import (
        estimate_back_point_at,
        estimate_facing,
        estimate_shoulder_points,
        estimate_wrist_points,
    )
    from .surface_path import METHOD, EdgeGraph, surface_path_length_mm

    measurements, landmarks = run_estimated_circumferences(mesh)
    for name in ("across_back_shoulder_width", "sleeve_length", "back_length"):
        measurements[name] = MeasurementValue(method=METHOD, quality=["prerequisite_landmarks_missing"])

    waist = landmarks.get("waist_level")
    neck = landmarks.get("neck_base_level")
    armpit = landmarks.get("armpit_level")
    if waist is None or neck is None:
        return measurements, landmarks

    facing = estimate_facing(mesh)
    landmarks["facing"] = facing
    # spec `requires: [front_back_orientation]` — with the 180-degree
    # ambiguity unresolved, every back-neck-dependent measurement refuses
    # to produce a number rather than guessing a side
    if "orientation_unknown" in facing.flags:
        for name in ("across_back_shoulder_width", "sleeve_length", "back_length"):
            measurements[name] = MeasurementValue(
                method=METHOD, quality=["orientation_unknown"] + facing.flags
            )
        return measurements, landmarks
    facing_flags = list(facing.flags)
    orientation_review = "front_back_low_confidence" in facing.flags

    def orientation_gate(value: MeasurementValue) -> MeasurementValue:
        if orientation_review and value.selected_value_mm is not None:
            value.disposition = "manual_review"
        return value

    graph = EdgeGraph(mesh)

    back_neck = estimate_back_point_at(
        mesh, float(neck.position_mm[1]), facing.direction, "back_neck_point"
    )
    back_waist = estimate_back_point_at(
        mesh, float(waist.position_mm[1]), facing.direction, "back_waist_point"
    )
    if back_neck is not None:
        back_neck.quality_flags += facing_flags
        landmarks["back_neck_point"] = back_neck
    if back_waist is not None:
        landmarks["back_waist_point"] = back_waist

    if back_neck is not None and back_waist is not None:
        length, flags = surface_path_length_mm(
            graph, [back_neck.position_mm, back_waist.position_mm]
        )
        # a length anchored on a boundary-flagged waist inherits the doubt:
        # the path may be flawless while the waist level it walks to is
        # only where the search ran out of window
        measurements["back_length"] = orientation_gate(_length_value(
            length,
            flags + waist.quality_flags + neck.quality_flags + facing_flags,
            METHOD,
        ))

    shoulders = estimate_shoulder_points(mesh, armpit) if armpit is not None else None
    if shoulders is not None and back_neck is not None:
        left, right = shoulders
        landmarks["shoulder_point_left"] = left
        landmarks["shoulder_point_right"] = right
        length, flags = surface_path_length_mm(
            graph, [left.position_mm, back_neck.position_mm, right.position_mm]
        )
        measurements["across_back_shoulder_width"] = orientation_gate(_length_value(
            length,
            flags + ["acromion_approximation"] + left.quality_flags + facing_flags,
            METHOD,
        ))

        wrist_left, wrist_right = estimate_wrist_points(mesh, armpit)
        wrist = wrist_right if wrist_right is not None else wrist_left
        shoulder = right if wrist is wrist_right else left
        if wrist is not None:
            landmarks[wrist.name] = wrist
            length, flags = surface_path_length_mm(
                graph, [back_neck.position_mm, shoulder.position_mm, wrist.position_mm]
            )
            measurements["sleeve_length"] = orientation_gate(_length_value(
                length,
                flags + ["elbow_waypoint_omitted_straight_hanging_arm"]
                + shoulder.quality_flags + wrist.quality_flags + facing_flags,
                METHOD,
            ))

    return measurements, landmarks
