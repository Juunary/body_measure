"""Texel BodyScan dataset adapter (CC BY-NC 4.0 — research only).

Layout: data/external/texel/PartN/<Person>/<pipeline>/{scan.ply,
measurements.csv, model_*.{json,ply}} + person.scan.xml.

Pipeline conventions (verified on Part1/Man0, recorded as adapter
metadata — this is what makes explicit units possible):
- portal_mx: scan.ply in mm, Y-up, floor at y=0, watertight.
  Its measurements.csv holds 100+ values with ISO 8559-1 clause numbers, cm.
- free_fusion: scan.ply in metres with an unverified axis convention —
  refused until verified (units/orientation are never guessed).

Dataset reference: each measurement value is compared against the CSV of the
SAME pipeline as the mesh; portal_mx and free_fusion disagree with each
other (different capture sessions/devices), so mixing them would fold
device disagreement into our error numbers.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import trimesh

from .base import Adapter, NormalizedBodySurface

# spec name -> Texel measurement ID (ISO 8559-1 clause in comments).
# Mapped by DEFINITION, not by name: our spec waist is the minimum torso
# girth, which is Texel's m102 — not m16 "Waist Girth" (5.3.10, natural
# waist level; observed ~20 mm systematically above the minimum on Part 1).
REF_IDS = {
    "chest_circumference": "m5",           # Bust/Chest Girth, 5.3.4
    "waist_circumference": "m102",         # Minimum Waist Girth (no clause) — matches spec definition
    "neck_circumference": "m11",           # Neck Base Girth, 5.3.3
    "across_back_shoulder_width": "m1",    # Across Back Shoulder Width (through the back neck point), 5.4.3
    "sleeve_length": "m55",                # Back Neck Point to Wrist (L/R), 5.4.17
    "back_length": "m3",                   # Back Neck Point to Waist, 5.4.5
}

# diagnostics, not measurements — kept out of the provides contract
AUX_IDS = {
    "stature": "m12",                      # 5.1.1
    "waist_height": "m43",                 # 5.1.10
    "waist_girth_iso_5_3_10": "m16",       # natural-waist-level girth, definition differs from spec
    "outer_arm_length": "m2",              # 5.7.8 — sleeve segment audit (approximate mapping)
    "shoulder_length": "m36",              # 5.4.1 — side-neck origin: MISMATCH with our back-neck segment
    "back_neck_to_wrist": "m55",           # 5.4.17 — duplicate of the sleeve reference for audits
    "neck_girth_middle": "m87",            # 5.3.2 — horizontal v1 slice may land here instead of m11
    "bust_girth_contoured": "m44",         # 5.3.5
    "chest_girth_at_axilla": "m45",        # 5.3.6
    "upper_chest_girth": "m46",            # 5.3.7
}

_CM_TO_MM = 10.0


class TexelAdapter(Adapter):
    name = "texel"
    source_type = "dataset_scan"
    provides = frozenset(REF_IDS)

    def persons(self, root: Path, part: str = "Part1") -> list[Path]:
        base = Path(root) / part
        if not base.is_dir():
            return []
        return sorted(p for p in base.iterdir() if p.is_dir())

    def load(self, path: Path, *, pipeline: str = "portal_mx", **kwargs) -> NormalizedBodySurface:
        """`path` is a person directory (e.g. .../Part1/Man0)."""
        if pipeline != "portal_mx":
            raise NotImplementedError(
                f"pipeline '{pipeline}': unit/axis convention not verified yet; "
                "units and orientations are never guessed"
            )
        scan = Path(path) / pipeline / "scan.ply"
        mesh = trimesh.load(scan, force="mesh", process=False)
        return NormalizedBodySurface(
            vertices_mm=np.asarray(mesh.vertices, dtype=np.float64),  # portal_mx is mm
            faces=np.asarray(mesh.faces, dtype=np.int64),
            source_type=self.source_type,
            source_id=f"texel/{Path(path).name}/{pipeline}",
            meta={"path": str(scan), "pipeline": pipeline, "dataset": "texel", "input_unit": "mm"},
        )

    def _csv_values(self, path: Path, pipeline: str) -> dict[str, float]:
        csv_path = Path(path) / pipeline / "measurements.csv"
        values: dict[str, float] = {}
        with open(csv_path, newline="", encoding="utf-8-sig") as handle:
            for row in csv.reader(handle):
                if len(row) < 4 or row[0] in ("ID", ""):
                    continue
                try:
                    values[row[0]] = float(row[3])
                except ValueError:
                    continue
        return values

    def dataset_reference(self, path: Path, *, pipeline: str = "portal_mx", **kwargs) -> dict[str, float]:
        raw = self._csv_values(path, pipeline)
        return {
            name: raw[mid] * _CM_TO_MM for name, mid in REF_IDS.items() if mid in raw
        }

    def aux_reference(self, path: Path, *, pipeline: str = "portal_mx") -> dict[str, float]:
        raw = self._csv_values(path, pipeline)
        return {
            name: raw[mid] * _CM_TO_MM for name, mid in AUX_IDS.items() if mid in raw
        }
