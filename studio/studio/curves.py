"""The geometry behind each number, for drawing.

body-measure keeps only the scalar and, since decision #46, the station
and axis an arm girth was cut at; its `viewer.gather_curves` re-slices
the mesh to draw the rings and rebuilds each length along the route its
number was measured on — the sagittal section for the back length
(decision #48), the edge graph for the two that cross it. That function
is used verbatim here and its curves are keyed to table rows by their
label.
"""
from __future__ import annotations

import numpy as np

from . import paths  # noqa: F401
from body_measure.viewer import gather_curves

#: viewer label prefix -> the measurement or prototype key it draws, so a
#: report filed from the 3D view lands on the right table row
LABEL_KEYS = {
    "Neck girth": "neck_circumference",
    "Chest girth": "chest_circumference",
    "Waist girth": "waist_circumference",
    "Upper arm girth": "upper_arm_girth",
    "Hip girth": "hip_girth",
    "Sleeve opening girth": "sleeve_opening_girth",
    "Back length": "back_length",
    "Across-back width": "across_back_shoulder_width",
    "Sleeve length": "sleeve_length",
}


def key_for_label(label: str | None) -> str | None:
    if not label:
        return None
    for prefix, key in LABEL_KEYS.items():
        if label.startswith(prefix):
            return key
    return None


def gather(mesh, measurements, landmarks, prototypes=None) -> tuple[list[dict], list[str]]:
    """Curves as JSON-ready dicts, canonical millimetres, Y-up."""
    out = []
    for label, colour, points, kind in gather_curves(mesh, measurements, landmarks, prototypes):
        out.append({"label": label, "key": key_for_label(label), "colour": colour, "kind": kind,
                    "points": _points(points)})
    notes = []
    if not any(c["key"] == "upper_arm_girth" for c in out):
        notes.append("upper-arm ring: not drawable — no station landmark for the measured value")
    return out, notes


def landmarks_json(landmarks: dict) -> tuple[dict, dict | None]:
    """Position landmarks as dicts; the facing (a direction, not a point)
    separately. Arm axes (a line, decision #46) are neither and are left
    out of the point set — the ring drawn from them is in the curves."""
    points, facing = {}, None
    for name, value in landmarks.items():
        if hasattr(value, "position_mm"):
            points[name] = value.to_dict()
        elif hasattr(value, "origin_mm"):
            continue
        elif hasattr(value, "direction"):
            facing = value.to_dict()
    return points, facing


def _points(points) -> list:
    arr = np.asarray(points, dtype=float)
    return [[round(float(x), 1), round(float(y), 1), round(float(z), 1)] for x, y, z in arr]
