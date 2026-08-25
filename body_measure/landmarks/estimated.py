"""Topology-agnostic landmark estimation on a canonical (Y-up, floor y=0)
standing body. These are replaceable heuristics (docs/decisions.md #4);
each landmark reports its method and confidence so downstream numbers can
be traced back to how the landmark was placed.

Implemented levels (all girth-profile based):
  waist_level  — minimum torso circumference between hip and chest;
  armpit_level — lowest height where the slice separates into >= 3 closed
                 loops (torso + two arms); absent if arms touch the torso;
  chest_level  — maximum torso circumference between waist and armpit;
  neck_base_level — minimum torso circumference between shoulder top and
                 head (v1: horizontal; the ISO neck-base plane is inclined,
                 so the evidence decides which dataset girth this matches).
A minimum/maximum sitting on its search-window boundary is flagged and
gets low confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from ..canonicalize import body_axis_point
from ..measure.circumference import measure_circumference
from ..measure.slicing import (
    SliceLoop,
    project_axis_to_plane,
    select_torso_loop,
    slice_mesh,
)
from .base import Landmark

_UP = np.array([0.0, 1.0, 0.0])

# stature-relative search window for the natural waist; hips peak ~52 %,
# chest peaks ~72 %, so the interior minimum lives between them.
WAIST_WINDOW = (0.45, 0.75)


def torso_girth_profile(
    mesh: trimesh.Trimesh,
    lo_mm: float,
    hi_mm: float,
    step_mm: float = 10.0,
) -> list[tuple[float, float]]:
    """(height, torso hull circumference) samples; heights with no
    trustworthy closed torso loop are skipped."""
    axis_xz = body_axis_point(mesh)
    profile: list[tuple[float, float]] = []
    for height in np.arange(lo_mm, hi_mm + 1e-9, step_mm):
        origin = np.array([0.0, height, 0.0])
        loops = slice_mesh(mesh, origin, _UP)
        selection = select_torso_loop(loops, project_axis_to_plane(axis_xz, origin, _UP))
        if selection is None or selection.disposition == "rejected":
            continue
        if selection.method != "axis_containment":
            # A nearest-centroid fallback is a guess about which loop is
            # the torso; a girth extremum taken over guesses is how a
            # 141 mm jacket-fold "waist" beat 25 trustworthy slices on a
            # clothed scan. One untrusted slice in the profile poisons
            # the argmin, so fallback slices are skipped, not down-ranked.
            continue
        circ = measure_circumference(selection.loop, close_gap=not selection.loop.closed)
        if circ.selected_value_mm is None:
            continue
        profile.append((float(height), float(circ.selected_value_mm)))
    return profile


ARMPIT_WINDOW = (0.55, 0.85)
NECK_WINDOW_TOP = 0.95


def _extremum_level(
    mesh: trimesh.Trimesh,
    name: str,
    lo_mm: float,
    hi_mm: float,
    *,
    minimum: bool,
    method: str,
    step_mm: float = 10.0,
) -> Landmark | None:
    profile = torso_girth_profile(mesh, lo_mm, hi_mm, step_mm)
    if len(profile) < 3:
        return None
    heights = np.array([p[0] for p in profile])
    girths = np.array([p[1] for p in profile])
    idx = int(np.argmin(girths) if minimum else np.argmax(girths))
    axis_xz = body_axis_point(mesh)

    flags: list[str] = []
    confidence = 0.8
    if idx in (0, len(profile) - 1):
        flags.append(("minimum" if minimum else "maximum") + "_at_search_boundary")
        confidence = 0.4

    return Landmark(
        name=name,
        position_mm=np.array([axis_xz[0], heights[idx], axis_xz[1]]),
        confidence=confidence,
        method=method,
        quality_flags=flags,
    )


CROTCH_WINDOW = (0.35, 0.60)


def estimate_crotch_level(mesh: trimesh.Trimesh, step_mm: float = 10.0) -> float | None:
    """Lowest height whose slice has a closed loop AROUND the body axis
    (legs merged). Below the crotch the legs are separate loops and the
    axis falls between them — bodies with a thigh gap (e.g. the SMPL
    template) would otherwise let a single-thigh girth win the waist
    minimum."""
    height = float(mesh.bounds[1][1])
    axis_xz = body_axis_point(mesh)
    for level in np.arange(CROTCH_WINDOW[0] * height, CROTCH_WINDOW[1] * height, step_mm):
        origin = np.array([0.0, float(level), 0.0])
        loops = slice_mesh(mesh, origin, _UP)
        selection = select_torso_loop(loops, project_axis_to_plane(axis_xz, origin, _UP))
        if selection is not None and selection.method == "axis_containment":
            return float(level)
    return None


#: The natural waist is never more than about this far below the armpit.
#: Used as a FLOOR on the search, not as the window itself: the garment
#: being built is an upper garment, and the lower body of a clothed scan
#: is whatever the subject happened to wear — a skirt has no crotch to
#: anchor on and baggy trousers have no reliable hip. Anchoring the floor
#: to the armpit keeps the search inside the torso the shirt has to fit.
ARMPIT_TO_WAIST_MAX_FRACTION = 0.28


def estimate_waist_level(
    mesh: trimesh.Trimesh,
    armpit: Landmark | None = None,
    step_mm: float = 10.0,
) -> Landmark | None:
    """Minimum torso girth, searched between a floor and WAIST_WINDOW's top.

    The floor is the strictest of three: the stature window's bottom, the
    crotch (when a crotch exists), and a fixed reach below the armpit.
    Each guards something different and none subsumes the others — the
    crotch stops a thigh loop winning on a body with legs, the armpit
    keeps the search out of the hips on a body whose proportions put its
    narrowest point there, and the stature bound is the fallback when
    neither landmark is available.

    Only the floor is anchored. Lowering the ceiling was tried and
    rejected: on NOMO male_0007 an armpit-relative ceiling cut off the
    true minimum at 0.657 H and returned a girth 28.6 mm larger, which by
    the spec's own definition is the wrong answer."""
    height = float(mesh.bounds[1][1])
    lo = WAIST_WINDOW[0] * height
    flags: list[str] = []

    if armpit is not None:
        lo = max(lo, float(armpit.position_mm[1]) - ARMPIT_TO_WAIST_MAX_FRACTION * height)
    else:
        flags.append("armpit_not_available_waist_floor_is_stature_relative")

    crotch = estimate_crotch_level(mesh, step_mm)
    if crotch is not None:
        lo = max(lo, crotch + 20.0)
    else:
        flags.append("crotch_not_detected")

    waist = _extremum_level(
        mesh,
        "waist_level",
        lo,
        WAIST_WINDOW[1] * height,
        minimum=True,
        method="minimum_torso_circumference",
        step_mm=step_mm,
    )
    if waist is not None:
        waist.quality_flags += flags
    return waist


def estimate_armpit_level(mesh: trimesh.Trimesh, step_mm: float = 10.0) -> Landmark | None:
    """Armpit = the HIGHEST height whose slice still has >= 3 closed loops
    (torso + both arms), i.e. just below where the arms merge into the
    shoulders. Searching upward from below would stop at the wrists —
    hanging hands already separate from the torso near hip height (this
    exact failure showed up on Texel Part 1). Returns None when the arms
    never separate from the torso."""
    height = float(mesh.bounds[1][1])
    axis_xz = body_axis_point(mesh)

    def landmark(level: float, confidence: float, flags: list[str]) -> Landmark:
        return Landmark(
            name="armpit_level",
            position_mm=np.array([axis_xz[0], level, axis_xz[1]]),
            confidence=confidence,
            method="highest_height_with_three_closed_loops",
            quality_flags=flags,
        )

    # position: always the HIGHEST separating level (the armpit is where
    # the arms merge into the shoulders — a lower, thicker separation zone
    # must not outrank it; Texel Woman4's true gap is one slice thick).
    # persistence of the level below only sets confidence: a single-slice
    # separation is honest but fragile under noise (known limitation).
    for level in np.arange(ARMPIT_WINDOW[1] * height, ARMPIT_WINDOW[0] * height, -step_mm):
        loops = slice_mesh(mesh, np.array([0.0, float(level), 0.0]), _UP)
        if sum(1 for lp in loops if lp.closed) >= 3:
            below = slice_mesh(mesh, np.array([0.0, float(level) - step_mm, 0.0]), _UP)
            persistent = sum(1 for lp in below if lp.closed) >= 3
            if persistent:
                return landmark(float(level), 0.7, [])
            return landmark(float(level), 0.4, ["single_slice_arm_separation"])
    return None


def estimate_chest_level(
    mesh: trimesh.Trimesh,
    waist: Landmark,
    armpit: Landmark | None,
    step_mm: float = 10.0,
) -> Landmark | None:
    """Maximum torso girth between the waist and the armpit."""
    height = float(mesh.bounds[1][1])
    hi = float(armpit.position_mm[1]) if armpit is not None else 0.78 * height
    chest = _extremum_level(
        mesh,
        "chest_level",
        float(waist.position_mm[1]) + step_mm,
        hi,
        minimum=False,
        method="maximum_torso_circumference_below_armpit",
        step_mm=step_mm,
    )
    if chest is not None and armpit is None:
        chest.quality_flags.append("armpit_not_detected_window_is_stature_relative")
        chest.confidence = min(chest.confidence, 0.5)
    return chest


def body_lateral_axis(mesh: trimesh.Trimesh, level_mm: float) -> tuple[np.ndarray, list[str]]:
    """(unit (x, z) left-right axis, quality_flags). World axes are NOT
    assumed — a scanner may deliver the subject at any yaw.

    Primary signal: at a slice with separated arms, the line between the
    two arm-loop centroids gives the lateral direction (arms hang beside
    the torso by construction; stable on the poses tested so far —
    Texel Part 1 and generated SMPL bodies). Cross-section PCA is a
    flagged fallback: a torso slice can be deeper than it is wide (Texel
    Woman4), sending PCA front-back, and the fallback is unvalidated for
    asymmetric or single-arm bodies — hence the flag propagates into
    every measurement that uses the axis."""
    loops, selection = _torso_loop_at(mesh, level_mm)
    if selection is None:
        return np.array([1.0, 0.0]), ["lateral_axis_default_no_torso"]
    arms = sorted(
        (lp for lp in loops if lp.closed and lp is not selection.loop),
        key=lambda lp: len(lp.points),
        reverse=True,
    )[:2]
    if len(arms) == 2:
        delta = arms[0].points[:, [0, 2]].mean(axis=0) - arms[1].points[:, [0, 2]].mean(axis=0)
        norm = float(np.linalg.norm(delta))
        if norm > 1e-6:
            return delta / norm, []
    pts = selection.loop.points[:, [0, 2]]
    centered = pts - pts.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    lateral = vt[0]
    return lateral / np.linalg.norm(lateral), ["lateral_axis_pca_fallback"]


@dataclass
class Facing:
    """Front-back orientation estimate. `confidence` is
    front_back_confidence: 0 means the 180-degree ambiguity is unresolved
    and every orientation-dependent measurement must refuse to produce a
    number (spec `requires: [front_back_orientation]`)."""

    direction: np.ndarray          # unit (x, z)
    confidence: float
    method: str
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "direction": [float(v) for v in self.direction],
            "confidence": self.confidence,
            "method": self.method,
            "flags": list(self.flags),
        }


def provided_facing(direction_xz, *, source: str) -> Facing:
    """An orientation that is KNOWN rather than estimated — a body model
    whose frame defines its front (SMPL faces +Z), or a scanner whose
    booth fixes where the subject stands. The flag records that no
    estimate was made; the confidence is full because the 180-degree
    ambiguity does not exist for such a source."""
    d = np.asarray(direction_xz, dtype=np.float64)
    n = float(np.linalg.norm(d))
    if n < 1e-9:
        raise ValueError("provided facing direction must be non-zero")
    return Facing(d / n, 1.0, f"provided_by_{source}", ["orientation_provided"])


def estimate_facing(mesh: trimesh.Trimesh) -> Facing:
    """The toes extend forward of the body axis, so the centroid of the
    foot slice sits in the facing direction (toe_projection). Missing feet
    leave the front/back 180-degree ambiguity unresolved ->
    orientation_unknown with confidence 0."""
    height = float(mesh.bounds[1][1])
    axis_xz = body_axis_point(mesh)
    loops = slice_mesh(mesh, np.array([0.0, 0.03 * height, 0.0]), _UP)
    if not loops:
        return Facing(np.array([0.0, 1.0]), 0.0, "toe_projection",
                      ["orientation_unknown", "no_foot_slice"])
    points = np.vstack([lp.points for lp in loops])
    offset = np.array([points[:, 0].mean(), points[:, 2].mean()]) - axis_xz
    norm = float(np.linalg.norm(offset))
    if norm < 5.0:  # 180-degree ambiguity effectively unresolved
        return Facing(np.array([0.0, 1.0]), 0.0, "toe_projection",
                      ["orientation_unknown", "toe_offset_below_threshold"])
    confidence = min(0.9, norm / 60.0)
    flags = ["front_back_low_confidence"] if norm < 30.0 else []
    return Facing(offset / norm, confidence, "toe_projection", flags)


def _torso_loop_at(mesh: trimesh.Trimesh, level_mm: float):
    axis_xz = body_axis_point(mesh)
    origin = np.array([0.0, level_mm, 0.0])
    loops = slice_mesh(mesh, origin, _UP)
    selection = select_torso_loop(loops, project_axis_to_plane(axis_xz, origin, _UP))
    return loops, selection


def estimate_back_point_at(
    mesh: trimesh.Trimesh, level_mm: float, facing_xz: np.ndarray, name: str
) -> Landmark | None:
    """Most-backward point of the torso loop at a height (e.g. the back
    neck point at the neck-base level, the back waist point)."""
    _, selection = _torso_loop_at(mesh, level_mm)
    if selection is None:
        return None
    if selection.method != "axis_containment":
        # the most-backward point of a loop that is merely *near* the
        # axis can sit anywhere — on HSRD it landed 104 degrees off the
        # back. No back point beats a wrong one.
        return None
    pts = selection.loop.points
    backwardness = -(pts[:, [0, 2]] @ facing_xz)
    point = pts[int(np.argmax(backwardness))]
    return Landmark(
        name=name,
        position_mm=np.asarray(point, dtype=np.float64),
        confidence=0.6 * selection.confidence / 0.9,
        method="most_backward_point_of_torso_loop",
        quality_flags=list(selection.quality_flags),
    )


def estimate_shoulder_points(
    mesh: trimesh.Trimesh, armpit: Landmark
) -> tuple[Landmark, Landmark] | None:
    """Shoulder (acromion-ish) point per side: the HIGHEST surface point in
    the vertical column above the armpit crease. With hanging arms the
    lateral silhouette extreme is the arm, not the shoulder — the column
    above the crease tops out on the shoulder ridge instead. Flagged as an
    approximation; the ISO acromion is a palpated bony landmark."""
    armpit_y = float(armpit.position_mm[1])
    _, selection = _torso_loop_at(mesh, armpit_y)
    if selection is None:
        return None
    pts = selection.loop.points
    height = float(mesh.bounds[1][1])
    vertices = mesh.vertices

    lateral, lateral_flags = body_lateral_axis(mesh, armpit_y)
    ortho = np.array([-lateral[1], lateral[0]])
    t_loop = pts[:, [0, 2]] @ lateral
    t_vert = vertices[:, [0, 2]] @ lateral
    o_vert = vertices[:, [0, 2]] @ ortho

    def side_landmark(crease: np.ndarray, name: str) -> Landmark | None:
        crease_t = crease[[0, 2]] @ lateral
        crease_o = crease[[0, 2]] @ ortho
        mask = (
            (np.abs(t_vert - crease_t) < 25.0)
            & (np.abs(o_vert - crease_o) < 45.0)
            & (vertices[:, 1] > armpit_y)
            & (vertices[:, 1] < armpit_y + 0.15 * height)
        )
        if not mask.any():
            return None
        column = vertices[mask]
        top = column[int(np.argmax(column[:, 1]))]
        return Landmark(
            name,
            np.asarray(top, dtype=np.float64),
            0.5,
            "highest_point_above_armpit_crease",
            ["acromion_approximation"] + lateral_flags,
        )

    left = side_landmark(pts[int(np.argmin(t_loop))], "shoulder_point_left")
    right = side_landmark(pts[int(np.argmax(t_loop))], "shoulder_point_right")
    if left is None or right is None:
        return None
    # a shoulder search is only as good as the armpit it stands on
    for lm in (left, right):
        lm.quality_flags += [f for f in armpit.quality_flags if f not in lm.quality_flags]
    # anatomical shoulders sit within a few mm of level (3 mm across ten
    # Texel subjects); a 200 mm step means at least one "shoulder" is a
    # jacket collar or a sleeve, and there is no telling which
    if abs(float(left.position_mm[1]) - float(right.position_mm[1])) > 0.05 * height:
        for lm in (left, right):
            lm.quality_flags.append("shoulder_vertical_asymmetry")
    return left, right


WRIST_WINDOW = (0.40, 0.55)


def estimate_wrist_points(
    mesh: trimesh.Trimesh, armpit: Landmark, step_mm: float = 10.0
) -> tuple[Landmark | None, Landmark | None]:
    """Wrist per hanging arm: the minimum arm-loop girth in the wrist
    window (the palm below and the forearm above are both wider)."""
    height = float(mesh.bounds[1][1])
    axis_xz = body_axis_point(mesh)
    armpit_y = float(armpit.position_mm[1])
    _, torso_sel = _torso_loop_at(mesh, armpit_y)
    if torso_sel is None:
        return None, None
    lateral, lateral_flags = body_lateral_axis(mesh, armpit_y)
    t_torso = torso_sel.loop.points[:, [0, 2]] @ lateral
    t_lo, t_hi = float(t_torso.min()), float(t_torso.max())
    t_axis = float(axis_xz @ lateral)

    best: dict[str, tuple[float, np.ndarray]] = {}
    for level in np.arange(WRIST_WINDOW[0] * height, WRIST_WINDOW[1] * height, step_mm):
        loops = slice_mesh(mesh, np.array([0.0, float(level), 0.0]), _UP)
        for lp in loops:
            if not lp.closed:
                continue
            ct = float((lp.points[:, [0, 2]] @ lateral).mean())
            if t_lo < ct < t_hi:
                continue  # torso, not an arm
            side = "left" if ct < t_axis else "right"
            girth = float(np.linalg.norm(np.diff(np.vstack([lp.points, lp.points[:1]]), axis=0), axis=1).sum())
            if side not in best or girth < best[side][0]:
                best[side] = (girth, lp.points.mean(axis=0))

    def landmark(side: str) -> Landmark | None:
        if side not in best:
            return None
        return Landmark(
            f"wrist_point_{side}",
            best[side][1].astype(np.float64),
            0.5,
            "minimum_arm_girth_in_wrist_window",
            ["hanging_arm_assumed"] + lateral_flags,
        )

    return landmark("left"), landmark("right")


#: Fraction of the armpit->wrist span that still counts as upper arm. The
#: elbow sits near the middle of that span, so staying below 0.45 keeps the
#: elbow (which widens again) out of the search.
UPPER_ARM_SPAN_FRACTION = 0.45
#: The search runs up to the armpit level itself: the deltoid is widest
#: right there, and a 20 mm safety clearance clipped the true maximum on
#: all ten Texel subjects (max girth always landed on the window's top
#: boundary; bias -12.6 -> -3.3 mm after removing it). Merged arm/torso
#: slices need no clearance to guard against — arm_loops_at only accepts
#: loops whose centroid lies outside the torso's lateral extent.
UPPER_ARM_CLEARANCE_MM = 0.0


def arm_loops_at(
    mesh: trimesh.Trimesh, level_mm: float, armpit: Landmark
) -> tuple[dict[str, SliceLoop], list[str]]:
    """Closed loops at `level_mm` that are arms, keyed 'left'/'right'.

    A loop is an arm when its centroid lies outside the torso's extent along
    the body's lateral axis — the same test estimate_wrist_points uses, so
    both stay consistent if the axis estimate changes."""
    armpit_y = float(armpit.position_mm[1])
    _, torso_sel = _torso_loop_at(mesh, armpit_y)
    if torso_sel is None:
        return {}, ["no_torso_at_armpit"]
    lateral, flags = body_lateral_axis(mesh, armpit_y)
    t_torso = torso_sel.loop.points[:, [0, 2]] @ lateral
    t_lo, t_hi = float(t_torso.min()), float(t_torso.max())
    t_axis = float(body_axis_point(mesh) @ lateral)

    found: dict[str, SliceLoop] = {}
    for lp in slice_mesh(mesh, np.array([0.0, float(level_mm), 0.0]), _UP):
        if not lp.closed:
            continue
        ct = float((lp.points[:, [0, 2]] @ lateral).mean())
        if t_lo < ct < t_hi:
            continue  # torso, not an arm
        found["left" if ct < t_axis else "right"] = lp
    return found, flags


def upper_arm_window(
    mesh: trimesh.Trimesh, armpit: Landmark, wrist: Landmark | None
) -> tuple[float, float, list[str]]:
    """(lowest, highest, flags) height range to search for the upper arm's
    widest point. Anchored on the detected wrist; without one the window is
    stature-relative and says so, the same way the chest window does."""
    armpit_y = float(armpit.position_mm[1])
    top = armpit_y - UPPER_ARM_CLEARANCE_MM
    if wrist is not None:
        span = armpit_y - float(wrist.position_mm[1])
        return armpit_y - UPPER_ARM_SPAN_FRACTION * span, top, []
    return (
        armpit_y - 0.19 * float(mesh.bounds[1][1]),
        top,
        ["wrist_not_detected_window_is_stature_relative"],
    )


def estimate_neck_base_level(
    mesh: trimesh.Trimesh,
    armpit: Landmark | None,
    step_mm: float = 5.0,
) -> Landmark | None:
    """Minimum girth between shoulder top and head (v1: horizontal plane)."""
    height = float(mesh.bounds[1][1])
    lo = (float(armpit.position_mm[1]) if armpit is not None else 0.78 * height) + 0.05 * height
    neck = _extremum_level(
        mesh,
        "neck_base_level",
        lo,
        NECK_WINDOW_TOP * height,
        minimum=True,
        method="minimum_girth_above_shoulders_horizontal_v1",
        step_mm=step_mm,
    )
    return neck
