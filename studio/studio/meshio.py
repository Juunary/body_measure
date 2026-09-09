"""Load a catalogue entry through the adapter that owns it, and pack a
mesh for the browser.

The adapters are body-measure's; nothing here reads a mesh file itself.
`MeshFileAdapter` needs a unit and `canonicalize` needs an up axis, and
both are the caller's to state — this module refuses without them.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import trimesh

from . import paths  # noqa: F401  (sys.path bootstrap)
from body_measure.adapters.base import UnitError
from body_measure.adapters.hsrd import HsrdAdapter
from body_measure.adapters.mesh_file import MeshFileAdapter
from body_measure.adapters.nomo import NomoAdapter
from body_measure.adapters.texel import TexelAdapter
from body_measure.canonicalize import canonicalize

UNITS = ("m", "cm", "mm")
UP_AXES = ("Y", "Z")
MAGIC = b"STUM"
#: above this the browser gets a coarser copy; measurements always run on
#: the full mesh (body-measure viewer.py does the same for its figures)
DISPLAY_FACE_LIMIT = 1_500_000
DISPLAY_VOXEL_MM = 5.0


class LoadError(ValueError):
    pass


def load_surface(entry: dict, unit: str | None, up_axis: str | None):
    """(NormalizedBodySurface, canonical trimesh, info dict)."""
    kind = entry["kind"]
    path = Path(entry["path"])
    info = {"kind": kind, "unit": None, "up_axis": None}

    if kind == "hsrd_lod":
        surface = HsrdAdapter(path.parent).load(path)
        info["unit"] = surface.meta.get("verified_unit")
        info["up_axis"] = "Z (adapter transform)"
        mesh = canonicalize(surface)               # transform_to_canonical applies
    elif kind == "texel_person":
        surface = TexelAdapter().load(path, pipeline="portal_mx")
        info["unit"], info["up_axis"] = "mm", "Y"
        mesh = canonicalize(surface, up_axis="Y")
    elif kind == "nomo":
        subject = entry["id"].split(":", 1)[1]
        surface = NomoAdapter(path).load(subject)
        info["unit"] = f"verified (scale {surface.meta.get('verified_unit_scale')})"
        info["up_axis"] = "Y"
        mesh = canonicalize(surface, up_axis="Y")
    elif kind == "mesh_file":
        if unit not in UNITS:
            raise LoadError(f"unit must be one of {UNITS} for a mesh file — units are never guessed")
        if up_axis not in UP_AXES:
            raise LoadError(f"up_axis must be one of {UP_AXES} for a mesh file")
        try:
            surface = MeshFileAdapter().load(path, unit=unit)
        except (UnitError, ValueError, FileNotFoundError) as exc:
            raise LoadError(str(exc)) from exc
        info["unit"], info["up_axis"] = unit, up_axis
        mesh = canonicalize(surface, up_axis=up_axis)
    else:
        raise LoadError(f"unknown entry kind {kind!r}")

    info.update({
        "source_type": surface.source_type,
        "source_id": surface.source_id,
        "n_vertices": int(len(mesh.vertices)),
        "n_faces": int(len(mesh.faces)),
        "bounds_mm": [[round(float(v), 1) for v in row] for row in mesh.bounds],
        "weld": mesh.metadata.get("weld"),
        "adapter_meta": {k: v for k, v in surface.meta.items()
                         if isinstance(v, (str, int, float, bool)) or v is None},
    })
    return surface, mesh, info


def _coarse(mesh: trimesh.Trimesh, voxel_mm: float) -> trimesh.Trimesh:
    quantised = np.round(mesh.vertices / voxel_mm) * voxel_mm
    coarse = trimesh.Trimesh(vertices=quantised, faces=mesh.faces.copy(), process=False)
    coarse.merge_vertices()
    coarse.update_faces(coarse.nondegenerate_faces())
    coarse.remove_unreferenced_vertices()
    return coarse


def pack_binary(mesh: trimesh.Trimesh) -> tuple[bytes, bool]:
    """Header (magic, n_vertices, n_faces, flags) + float32 xyz mm + uint32
    triangles. `flags` bit 0 says the geometry was coarsened for display."""
    decimated = len(mesh.faces) > DISPLAY_FACE_LIMIT
    shown = _coarse(mesh, DISPLAY_VOXEL_MM) if decimated else mesh
    vertices = np.ascontiguousarray(shown.vertices, dtype=np.float32)
    faces = np.ascontiguousarray(shown.faces, dtype=np.uint32)
    header = MAGIC + struct.pack("<III", len(vertices), len(faces), 1 if decimated else 0)
    return header + vertices.tobytes() + faces.tobytes(), decimated
