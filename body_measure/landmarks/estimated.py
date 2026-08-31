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
        if selection is None or selection.disposition != "accepted":
            # Not just "not rejected": a manual_review slice is one the
            # gap-closure tier already judged too bridged to stand on its
            # own, and an extremum makes exactly that judgement on its
            # behalf. On NOMO male_0001 a slice with 15.5 % of its loop
            # replaced by a closing chord won the waist argmin with a
            # 675 mm girth on a 1725 mm subject; excluding it costs one
            # sample of 52 and moves the waist to 961 mm at 0.674 H,
            # where every other subject's sits. No Texel or HSRD result
            # moves at all.
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


#: Everything below this fraction of stature is foot rather than ankle.
FOOT_TOP_FRACTION = 0.04
#: The band the reference centre is taken from: the lower leg directly
#: above the foot. Named for what it is rather than for the ankle joint,
#: which on a standing body sits below this at roughly 4 % of stature.
LOWER_LEG_BAND_FRACTION = (0.06, 0.09)
#: A foot outline needs enough points for its long axis to mean anything.
MIN_FOOT_VERTICES = 30
#: The leg centre is one mean position, so it needs far fewer points than
#: the outline does. SMPL carries 6890 vertices for a whole body and puts
#: about 20 in this band; a scan puts hundreds.
MIN_LEG_VERTICES = 8
#: Toe reach over heel reach about the ankle. Below this the outline is too
#: symmetric to say which end is the toe, so the sign is not resolved.
MIN_TOE_HEEL_RATIO = 1.15
#: Cosine between the two feet's directions. Feet point roughly the same
#: way; a disagreement means at least one outline was not a foot.
MIN_FEET_AGREEMENT = 0.80
#: Above this cosine the two feet corroborate each other outright.
GOOD_FEET_AGREEMENT = 0.95


def _foot_toe_direction(foot_xz: np.ndarray, leg_xz: np.ndarray):
    """Unit XZ direction from the leg centre toward the toes, and the
    toe/heel reach ratio that says how firmly the sign is decided.

    The foot's long axis is heel-to-toe; the leg meets it far nearer the
    heel than the toes, so about that point the toe end reaches further
    — on the scans here by a factor of three to six. That is
    anatomy and holds at any slice height, unlike the centroid of a single
    horizontal cut, which points forward only while the cut is low enough
    to still contain toes (about 2 % of stature) and reverses above it.
    """
    rel = foot_xz - leg_xz
    _, _, vt = np.linalg.svd(rel - rel.mean(axis=0), full_matrices=False)
    axis = vt[0] / np.linalg.norm(vt[0])
    projection = rel @ axis
    forward, backward = float(projection.max()), float(-projection.min())
    if backward > forward:
        axis, forward, backward = -axis, backward, forward
    ratio = forward / backward if backward > 1e-6 else float("inf")
    return axis, ratio


def estimate_facing(mesh: trimesh.Trimesh) -> Facing:
    """Front-back orientation from the asymmetry of each foot about the
    leg above it (toe_extent_about_leg).

    Confidence comes from corroboration — the two feet agreeing with each
    other, and each outline being lopsided enough to tell toe from heel —
    rather than from the magnitude of any single sample. The earlier
    toe_projection method read the centroid of one horizontal cut at 3 % of
    stature; toes are only ~25 mm tall, so that cut holds heel and Achilles
    instead and pointed backwards, the more strongly the higher it was cut
    (decision #31).

    Missing feet leave the 180-degree ambiguity unresolved ->
    orientation_unknown with confidence 0.
    """
    METHOD = "toe_extent_about_leg"
    # Only vertices the faces actually use: a mesh may carry orphans, and a
    # surface that has been cropped away is gone whether or not its
    # vertices were also deleted.
    referenced = mesh.referenced_vertices
    vertices = np.asarray(mesh.vertices, dtype=np.float64)[referenced]
    if not len(vertices):
        return Facing(np.array([0.0, 1.0]), 0.0, METHOD,
                      ["orientation_unknown", "no_foot_slice"])
    floor = float(vertices[:, 1].min())
    height = float(vertices[:, 1].max()) - floor
    y = vertices[:, 1] - floor
    xz = vertices[:, [0, 2]]

    foot_mask = y < FOOT_TOP_FRACTION * height
    lo, hi = LOWER_LEG_BAND_FRACTION
    leg_mask = (y > lo * height) & (y < hi * height)
    if foot_mask.sum() < MIN_FOOT_VERTICES or leg_mask.sum() < MIN_LEG_VERTICES:
        return Facing(np.array([0.0, 1.0]), 0.0, METHOD,
                      ["orientation_unknown", "no_foot_slice"])

    # Separate the two legs along the line between them rather than along
    # world x: a scanner may deliver the subject at any yaw, and splitting
    # on the wrong axis cuts each foot in half instead of parting the pair.
    legs = xz[leg_mask]
    _, _, vt = np.linalg.svd(legs - legs.mean(axis=0), full_matrices=False)
    across = vt[0] / np.linalg.norm(vt[0])
    leg_projection = legs @ across
    midline = 0.5 * (float(leg_projection.min()) + float(leg_projection.max()))
    foot_projection = xz[foot_mask] @ across
    groups = [(foot_projection < midline, leg_projection < midline),
              (foot_projection >= midline, leg_projection >= midline)]
    # Feet close together leave no real separation to split on, so one
    # combined reading is honest where two invented ones would not be.
    centres = [legs[leg].mean(axis=0) for _, leg in groups
               if leg.sum() >= MIN_LEG_VERTICES]
    if len(centres) < 2 or float(np.linalg.norm(centres[0] - centres[1])) < 40.0:
        groups = [(np.ones(foot_mask.sum(), bool), np.ones(leg_mask.sum(), bool))]

    feet, directions, ratios = xz[foot_mask], [], []
    for foot_side, leg_side in groups:
        foot, leg = feet[foot_side], legs[leg_side]
        if len(foot) < MIN_FOOT_VERTICES or len(leg) < MIN_LEG_VERTICES:
            continue
        direction, ratio = _foot_toe_direction(foot, leg.mean(axis=0))
        if ratio < MIN_TOE_HEEL_RATIO:
            continue  # too symmetric to name an end; not evidence
        directions.append(direction)
        ratios.append(ratio)

    if not directions:
        return Facing(np.array([0.0, 1.0]), 0.0, METHOD,
                      ["orientation_unknown", "foot_outline_not_lopsided"])

    if len(directions) == 1:
        # One foot is a real reading but nothing corroborates it.
        return Facing(directions[0], 0.4, METHOD,
                      ["front_back_low_confidence", "single_foot_orientation"])

    mean = np.mean(directions, axis=0)
    norm = float(np.linalg.norm(mean))
    agreement = float(min(np.dot(d, mean / norm) for d in directions)) \
        if norm > 1e-9 else -1.0
    if agreement < MIN_FEET_AGREEMENT:
        # The two feet disagree, so at least one outline was not a foot.
        return Facing(np.array([0.0, 1.0]), 0.0, METHOD,
                      ["orientation_unknown", "feet_disagree_on_orientation"])

    confidence = min(0.9, agreement * min(1.0, min(ratios) / 2.0))
    flags = [] if agreement >= GOOD_FEET_AGREEMENT \
        else ["front_back_low_confidence"]
    return Facing(mean / norm, confidence, METHOD, flags)


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


#: Half-width of the lateral slab the shoulder top is read from. Narrow on
#: purpose: the station is fixed by the armpit crease, and any width given
#: to an argmax over height is width it spends sliding medially, because
#: the shoulder ridge falls away monotonically outward (decision #32).
SHOULDER_SLAB_HALF_MM = 6.0
#: Front-back half-window about the crease, keeping the slab on the
#: shoulder rather than on the chest or the shoulder blade.
SHOULDER_DEPTH_HALF_MM = 45.0
#: How far above the armpit the shoulder top is looked for.
SHOULDER_CEILING_FRACTION = 0.15
#: A top found this close to the ceiling was cut off by the window rather
#: than found on the body.
SHOULDER_CEILING_MARGIN_MM = 5.0


def estimate_shoulder_points(
    mesh: trimesh.Trimesh, armpit: Landmark
) -> tuple[Landmark, Landmark] | None:
    """Shoulder (acromion-ish) point per side: the top of the surface
    directly above the armpit crease.

    The lateral station is taken from the crease and not searched. A
    search would be worse than useless here: the shoulder ridge declines
    monotonically from the neck out to the arm with no acromion break in
    it, so an argmax over height inside a lateral window always returns
    the window's medial edge. The earlier version used a +/-25 mm column
    and did exactly that on 19 of 20 Texel shoulders, landing within 4 mm
    of the medial edge each time and reading the width 50 mm short
    (decision #32).

    Flagged as an approximation; the ISO acromion is a palpated bony
    landmark, and "above the armpit crease" is a stand-in for it."""
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

    ceiling = armpit_y + SHOULDER_CEILING_FRACTION * height

    def side_landmark(crease: np.ndarray, name: str) -> Landmark | None:
        crease_t = crease[[0, 2]] @ lateral
        crease_o = crease[[0, 2]] @ ortho
        mask = (
            (np.abs(t_vert - crease_t) < SHOULDER_SLAB_HALF_MM)
            & (np.abs(o_vert - crease_o) < SHOULDER_DEPTH_HALF_MM)
            & (vertices[:, 1] > armpit_y)
            & (vertices[:, 1] < ceiling)
        )
        if not mask.any():
            return None
        column = vertices[mask]
        top = column[int(np.argmax(column[:, 1]))]
        flags = ["acromion_approximation"] + lateral_flags
        if ceiling - float(top[1]) < SHOULDER_CEILING_MARGIN_MM:
            # the slab ran out before the surface stopped rising, so this
            # is the window's own lid — hair and a raised arm both do it
            flags.append("shoulder_at_search_ceiling")
        return Landmark(
            name,
            np.asarray(top, dtype=np.float64),
            0.5,
            "top_of_surface_above_armpit_crease",
            flags,
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
