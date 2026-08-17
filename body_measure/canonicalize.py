"""Bring a NormalizedBodySurface into the canonical measuring frame:
Y-up right-handed, floor at y=0. No unit guessing happens here — vertices
are already millimetres by the adapter contract."""
from __future__ import annotations

import numpy as np
import trimesh

from .adapters.base import CANONICAL_COORDINATE_SYSTEM, NormalizedBodySurface

# Rotation taking a Z-up mesh into the Y-up canonical frame (-90 deg about X).
_Z_UP_TO_Y_UP = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
)


def canonicalize(surface: NormalizedBodySurface, *, up_axis: str = "Y") -> trimesh.Trimesh:
    """Return a trimesh in the canonical frame (Y-up, floor y=0)."""
    mesh = trimesh.Trimesh(
        vertices=surface.vertices_mm.copy(), faces=surface.faces.copy(), process=False
    )
    if surface.transform_to_canonical is not None:
        mesh.apply_transform(surface.transform_to_canonical)
    elif up_axis == "Z":
        mesh.apply_transform(_Z_UP_TO_Y_UP)
    elif up_axis != "Y":
        raise ValueError(f"unsupported up_axis '{up_axis}' (expected 'Y' or 'Z')")
    mesh.apply_translation([0.0, -mesh.bounds[0][1], 0.0])
    return mesh


def body_axis_point(mesh: trimesh.Trimesh) -> np.ndarray:
    """(x, z) of the estimated vertical body axis.

    Slice-0 estimate: centroid of all vertices projected to the ground
    plane. Good enough for torso-loop selection on standing bodies;
    replaced by a per-height torso axis in the estimated-landmarks slice.
    """
    centroid = mesh.vertices.mean(axis=0)
    return np.array([centroid[0], centroid[2]])
