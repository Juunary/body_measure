"""Generic mesh-file adapter (OBJ/PLY/STL). No metadata, so the unit must
be passed explicitly — this adapter provides no ground truth."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from .base import Adapter, NormalizedBodySurface, scale_to_mm


class MeshFileAdapter(Adapter):
    name = "mesh_file"
    source_type = "mesh_file"
    provides = frozenset()

    def load(self, path: Path, *, unit: str | None = None, **kwargs) -> NormalizedBodySurface:
        scale = scale_to_mm(unit, source=str(path))
        loaded = trimesh.load(path, force="mesh", process=False)
        if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
            raise ValueError(f"'{path}' did not load as a triangle mesh")
        return NormalizedBodySurface(
            vertices_mm=np.asarray(loaded.vertices, dtype=np.float64) * scale,
            faces=np.asarray(loaded.faces, dtype=np.int64),
            source_type=self.source_type,
            source_id=path.name,
            meta={"path": str(path), "input_unit": unit},
        )
