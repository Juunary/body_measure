"""NOMO-3D-400 adapter (research-only license, NO redistribution).

Layout after extraction to data/external/nomo/NOMO-3d-400-scans_and_tc2_measurements/extracted/:
  TC2_Male_Txt/male_NNNN.txt   (`MEASURE Name=value`, header `OPTION UNITS=cm`)
  <obj dirs>/male_NNNN.obj

Definition mapping (docs/datasets.md rules — match by definition, not name):
- neck_circumference <- NeckBase_Circ (neck base girth, matches spec)
- chest_circumference <- CHEST_Circ
- waist: TC2 provides MaxWAIST_Circ / TrouserWAIST_Circ, NEITHER of which
  is the spec's minimum torso girth -> exposed as aux only, no reference claim.
Per-subject Head_Top_Height doubles as a stature cross-check for the mesh
unit (verified, not guessed).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from .base import Adapter, NormalizedBodySurface

REF_NAMES = {
    "neck_circumference": "NeckBase_Circ",
    "chest_circumference": "CHEST_Circ",
}
AUX_NAMES = {
    "max_waist_girth": "MaxWAIST_Circ",
    "trouser_waist_girth": "TrouserWAIST_Circ",
    "stature": "Head_Top_Height",
    "across_back": "Across_Back",
}
_CM_TO_MM = 10.0


def parse_tc2(path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("MEASURE ") and "=" in line:
            key, _, raw = line[len("MEASURE "):].partition("=")
            try:
                values[key.strip()] = float(raw)
            except ValueError:
                continue
    return values


class NomoAdapter(Adapter):
    name = "nomo"
    source_type = "dataset_scan"
    provides = frozenset(REF_NAMES)

    def __init__(self, root: Path):
        self.root = Path(root)  # .../extracted

    def subjects(self, gender: str = "male") -> list[str]:
        txt_dir = self.root / f"TC2_{gender.capitalize()}_Txt"
        return sorted(p.stem for p in txt_dir.glob(f"{gender}_*.txt"))

    def _obj_path(self, subject: str) -> Path:
        matches = list(self.root.rglob(f"{subject}.obj"))
        if not matches:
            raise FileNotFoundError(f"no OBJ for {subject} under {self.root}")
        return matches[0]

    def _txt_path(self, subject: str) -> Path:
        gender = subject.split("_")[0]
        return self.root / f"TC2_{gender.capitalize()}_Txt" / f"{subject}.txt"

    def load(self, path: Path, **kwargs) -> NormalizedBodySurface:
        """`path` is the subject id (e.g. 'male_0000')."""
        subject = str(path)
        mesh = trimesh.load(self._obj_path(subject), force="mesh", process=False)
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        # unit verification against the subject's own TC2 stature (cm)
        stature_cm = parse_tc2(self._txt_path(subject)).get("Head_Top_Height")
        extent = float(vertices.max(axis=0)[1] - vertices.min(axis=0)[1])
        if stature_cm is None:
            raise ValueError(f"{subject}: no stature to verify mesh unit against")
        candidates = {"mm": 1.0, "cm": 10.0, "m": 1000.0}
        scale = None
        for unit, factor in candidates.items():
            if abs(extent * factor - stature_cm * 10.0) < 0.15 * stature_cm * 10.0:
                scale = factor
                break
        if scale is None:
            raise ValueError(
                f"{subject}: mesh extent {extent:.1f} matches no unit against "
                f"stature {stature_cm} cm — refusing to guess"
            )
        return NormalizedBodySurface(
            vertices_mm=vertices * scale,
            faces=np.asarray(mesh.faces, dtype=np.int64),
            source_type=self.source_type,
            source_id=f"nomo/{subject}",
            meta={"dataset": "nomo", "verified_unit_scale": scale},
        )

    def dataset_reference(self, path: Path, **kwargs) -> dict[str, float]:
        values = parse_tc2(self._txt_path(str(path)))
        return {k: values[v] * _CM_TO_MM for k, v in REF_NAMES.items() if v in values}

    def aux_reference(self, path: Path) -> dict[str, float]:
        values = parse_tc2(self._txt_path(str(path)))
        return {k: values[v] * _CM_TO_MM for k, v in AUX_NAMES.items() if v in values}
