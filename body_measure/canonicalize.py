"""Bring a NormalizedBodySurface into the canonical measuring frame:
Y-up right-handed, floor at y=0. No unit guessing happens here — vertices
are already millimetres by the adapter contract.

Welding also happens here. Photogrammetry OBJs split a vertex once per
texture chart, so the same 3D point arrives under several indices and the
mesh, though geometrically continuous, is topologically shattered — HSRD
ships 1348 vertex-graph components at lod2 with the largest holding under
2 % of vertices. Nothing that walks the surface can work on that, which is
what made every surface-path measurement fail on a clothed scan. Merging
by position is a pure topology repair: coordinates and bounds are
untouched, only duplicate indices collapse.

It cannot be done in the adapter, because trimesh keeps UV-split vertices
apart while texture data is attached. By the time a surface reaches here
the UVs are gone and position is the only thing left to merge on.
"""
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


def canonicalize(
    surface: NormalizedBodySurface, *, up_axis: str = "Y", weld: bool = True
) -> trimesh.Trimesh:
    """Return a trimesh in the canonical frame (Y-up, floor y=0).

    `weld` merges duplicate-position vertices so the surface is connected.
    Leave it on for anything that measures along the surface. Turn it off
    only for a caller that depends on the incoming vertex indexing — a
    fixed-topology body model, say — where collapsing indices would break
    the correspondence rather than repair it.

    What the weld did is recorded in `mesh.metadata["weld"]`; it is a
    property of the surface a reader may need, not a detail to hide.
    """
    mesh = trimesh.Trimesh(
        vertices=surface.vertices_mm.copy(), faces=surface.faces.copy(), process=False
    )
    before = len(mesh.vertices)
    if weld:
        mesh.merge_vertices()
    mesh.metadata["weld"] = {
        "applied": bool(weld),
        "vertices_before": before,
        "vertices_after": int(len(mesh.vertices)),
        "merged": before - int(len(mesh.vertices)),
    }
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
