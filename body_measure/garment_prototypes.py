"""Garment measurements that are NOT in measurement-spec.

Everything in this module is a prototype. None of it has an ISO 8559-1
definition audit, a reference comparison, or a place in the robustness
battery, and none of it appears under `measurements` in a result — the
result schema stays exactly the spec's keys. They live here so a garment
discussion can point at real numbers from a real scan, and they are kept
in a separate module, a separate result block and a separate colour so a
prototype can never be read as a validated measurement.

Promoting one means: audit its definition against the standard, give it a
reference to be compared against, add it to the spec, and put it through
the battery. Until then it is a sketch.

The girth prototypes reuse the core's own tier rule — a torso loop chosen
by nearest-centroid fallback is not a measurement — because a prototype
that is sloppier than the pipeline it sits beside teaches nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from .canonicalize import body_axis_point
from .landmarks import estimated as E
from .landmarks.base import Landmark
from .measure.circumference import measure_circumference
from .measure.slicing import project_axis_to_plane, select_torso_loop, slice_mesh

_UP = np.array([0.0, 1.0, 0.0])

#: A short sleeve ends part-way down the upper arm. Where exactly is a
#: garment design choice, so this is a parameter, not a definition.
SLEEVE_END_FRACTION = 0.30


@dataclass
class PrototypeValue:
    key: str
    label: str
    value: float | None
    unit: str = "mm"
    flags: list[str] = field(default_factory=list)
    note: str = ""
    #: height of the horizontal slice, when the prototype is a girth
    level_mm: float | None = None

    @property
    def available(self) -> bool:
        return self.value is not None

    def to_dict(self) -> dict:
        return {
            "value": self.value, "unit": self.unit, "flags": self.flags,
            "note": self.note, "level_mm": self.level_mm,
            "status": "prototype_not_in_spec",
        }


def torso_girth_at(mesh: trimesh.Trimesh, level_mm: float):
    """(girth_mm, selection) at a height, or (None, None)."""
    axis = body_axis_point(mesh)
    origin = np.array([0.0, float(level_mm), 0.0])
    selection = select_torso_loop(
        slice_mesh(mesh, origin, _UP), project_axis_to_plane(axis, origin, _UP))
    if selection is None or selection.method != "axis_containment":
        return None, None
    circ = measure_circumference(selection.loop, close_gap=not selection.loop.closed)
    return circ.selected_value_mm, selection


def hem_girth(mesh, waist: Landmark | None, crotch: float | None) -> PrototypeValue:
    """Torso girth where a hem falls, taken as the widest level between the
    crotch and the waist. The hem's real height is a garment length
    decision; this is the body underneath wherever it is put."""
    if waist is None:
        return PrototypeValue("hem_girth", "Hem girth (hip level)", None,
                              note="no waist landmark to search below")
    lo = (crotch + 20.0) if crotch is not None else 0.45 * float(mesh.bounds[1][1])
    hi = float(waist.position_mm[1]) - 20.0
    best_value, best_level = None, None
    for level in np.arange(lo, hi, 10.0):
        girth, _ = torso_girth_at(mesh, level)
        if girth is not None and (best_value is None or girth > best_value):
            best_value, best_level = girth, float(level)
    if best_value is None:
        return PrototypeValue("hem_girth", "Hem girth (hip level)", None,
                              note="no trustworthy torso loop between crotch and waist")
    return PrototypeValue("hem_girth", "Hem girth (hip level)", best_value,
                          note="widest torso level below the waist",
                          level_mm=best_level)


def sleeve_opening_girth(mesh, armpit: Landmark | None,
                         wrist: Landmark | None) -> PrototypeValue:
    if armpit is None:
        return PrototypeValue("sleeve_opening_girth", "Sleeve opening girth", None,
                              note="no armpit landmark")
    armpit_y = float(armpit.position_mm[1])
    if wrist is not None:
        level = armpit_y - SLEEVE_END_FRACTION * (armpit_y - float(wrist.position_mm[1]))
    else:
        level = armpit_y - 0.08 * float(mesh.bounds[1][1])
    loops, flags = E.arm_loops_at(mesh, level, armpit)
    values = []
    for loop in loops.values():
        circ = measure_circumference(loop, close_gap=not loop.closed)
        if circ.selected_value_mm is not None:
            values.append(circ.selected_value_mm)
    if not values:
        return PrototypeValue("sleeve_opening_girth", "Sleeve opening girth", None,
                              flags=list(flags), level_mm=level,
                              note="no arm loop at the sleeve-end height")
    return PrototypeValue(
        "sleeve_opening_girth", "Sleeve opening girth", float(np.mean(values)),
        flags=list(flags), level_mm=level,
        note=f"arm girth {int(SLEEVE_END_FRACTION * 100)} % down armpit-to-wrist, "
             f"{len(values)} arm(s)")


def armhole_depth(shoulders, armpit: Landmark | None) -> PrototypeValue:
    if shoulders is None or armpit is None:
        return PrototypeValue("armhole_depth", "Armhole depth", None,
                              note="needs both shoulder points and the armpit level")
    tops = [float(s.position_mm[1]) for s in shoulders]
    return PrototypeValue(
        "armhole_depth", "Armhole depth",
        float(np.mean(tops)) - float(armpit.position_mm[1]),
        flags=[f for s in shoulders for f in s.quality_flags],
        note="vertical shoulder-to-armpit drop, mean of both sides")


def shoulder_slope(shoulders, back_neck: Landmark | None) -> PrototypeValue:
    """Degrees below horizontal from the neck point out to the shoulder tip —
    the measurement a tape cannot take and a scan can."""
    if shoulders is None or back_neck is None:
        return PrototypeValue("shoulder_slope", "Shoulder slope", None, unit="deg",
                              note="needs the back neck point and both shoulder points")
    neck = back_neck.position_mm
    angles = []
    for tip in shoulders:
        horizontal = float(np.linalg.norm((tip.position_mm - neck)[[0, 2]]))
        if horizontal > 1e-6:
            angles.append(np.degrees(np.arctan2(neck[1] - tip.position_mm[1], horizontal)))
    if not angles:
        return PrototypeValue("shoulder_slope", "Shoulder slope", None, unit="deg")
    return PrototypeValue("shoulder_slope", "Shoulder slope", float(np.mean(angles)),
                          unit="deg", note="mean of both sides")


def front_back_width(mesh, chest_level: float | None, armpit: Landmark | None,
                     facing, chest_flags) -> PrototypeValue:
    """The chest loop split at its lateral extremes: how much girth is in
    front of the body and how much behind.

    Which half is the front comes from the measured facing direction, never
    from the sign of an arbitrary perpendicular — that is a coin flip, and
    it read the back as the front the first time it ran."""
    if chest_level is None or armpit is None:
        return PrototypeValue("front_back_width", "Front / back width", None,
                              note="needs the chest level and the armpit")
    if facing is None or "orientation_unknown" in facing.flags:
        return PrototypeValue("front_back_width", "Front / back width", None,
                              note="front and back are not distinguishable on this scan")
    if "arm_clipped_at_merged_level" in chest_flags:
        return PrototypeValue(
            "front_back_width", "Front / back width", None,
            flags=["arms_merged_at_chest_level"], level_mm=chest_level,
            note="arms are merged into the chest loop, so its lateral extremes are "
                 "sleeve edges rather than body sides")
    _, selection = torso_girth_at(mesh, chest_level)
    if selection is None:
        return PrototypeValue("front_back_width", "Front / back width", None,
                              level_mm=chest_level,
                              note="no trustworthy torso loop at chest level")
    lateral, _ = E.body_lateral_axis(mesh, float(armpit.position_mm[1]))
    pts = selection.loop.points
    t = pts[:, [0, 2]] @ lateral
    forward = pts[:, [0, 2]] @ facing.direction
    a, b = sorted((int(np.argmin(t)), int(np.argmax(t))))
    seg1, seg2 = pts[a:b + 1], np.vstack([pts[b:], pts[:a + 1]])
    fwd2 = np.concatenate([forward[b:], forward[:a + 1]])

    def arc(points):
        return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))

    front, back = ((arc(seg1), arc(seg2)) if forward[a:b + 1].mean() > fwd2.mean()
                   else (arc(seg2), arc(seg1)))
    return PrototypeValue(
        "front_back_width", "Front / back width", front - back,
        flags=list(facing.flags), level_mm=chest_level,
        note=f"front arc {front:.0f} - back arc {back:.0f} mm; positive means "
             "the front is the wider half")


#: order the CLI and the figures present them in
POLO_SET = ("hem_girth", "sleeve_opening_girth", "armhole_depth",
            "shoulder_slope", "front_back_width")


def run_prototypes(mesh, measurements, landmarks) -> dict[str, PrototypeValue]:
    """All garment prototypes, keyed as POLO_SET. `measurements` and
    `landmarks` are what run_estimated_measurements returned."""
    armpit = landmarks.get("armpit_level")
    waist = landmarks.get("waist_level")
    chest = landmarks.get("chest_level")
    back_neck = landmarks.get("back_neck_point")
    shoulders = None
    if "shoulder_point_left" in landmarks and "shoulder_point_right" in landmarks:
        shoulders = (landmarks["shoulder_point_left"], landmarks["shoulder_point_right"])
    wrist = landmarks.get("wrist_point_right") or landmarks.get("wrist_point_left")
    chest_flags = list(measurements["chest_circumference"].quality)

    values = [
        hem_girth(mesh, waist, E.estimate_crotch_level(mesh)),
        sleeve_opening_girth(mesh, armpit, wrist),
        armhole_depth(shoulders, armpit),
        shoulder_slope(shoulders, back_neck),
        front_back_width(mesh, None if chest is None else float(chest.position_mm[1]),
                         armpit, landmarks.get("facing"), chest_flags),
    ]
    return {v.key: v for v in values}
