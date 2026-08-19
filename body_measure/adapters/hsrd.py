"""HSRD-100 adapter (CC BY 4.0 — the only dataset cleared for material
shown outside the project).

These are clothed photogrammetry scans: winter jacket, jeans, boots, hat.
That makes them useful for exactly two things and useless for a third.

Useful:
  - a clothed-scan FAILURE INVENTORY: which measurements the pipeline can
    even produce on a clothed body, and which flags fire;
  - LOD consistency (the same subject at several mesh resolutions).

Not useful, and refused here:
  - any quantitative clothing offset. HSRD ships no same-subject body
    reference, so `fit_references` is empty and there is nothing to
    subtract. The offset belongs to SIZER.

Conventions verified on HSR0015-Body-009: Z-up, metres, floor at z=0.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

from .base import Adapter, NormalizedBodySurface, scale_to_mm

#: A clothed scan is TALLER than the person: boots and headwear add height,
#: nothing removes it. Verification is therefore one-sided — the observed
#: extent may exceed the recorded stature substantially, but must not fall
#: meaningfully below it. Observed on HSR0015-Body-009: 1687 mm scan vs a
#: recorded 1630 mm stature (+3.5 %, boots and a beanie).
STATURE_TOLERANCE_LOW = 0.95
STATURE_TOLERANCE_HIGH = 1.20

#: Z-up (as shipped) into the canonical Y-up frame.
_Z_UP_TO_Y_UP = np.array([
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, -1.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
])


class HsrdAdapter(Adapter):
    name = "hsrd"
    source_type = "dataset_scan"
    provides = frozenset()        # no tape or automatic measurements ship with it
    fit_references = frozenset()  # and no body-under-clothing surface either

    def __init__(self, root: Path):
        self.root = Path(root)

    def observations(self) -> list[Path]:
        """Every LOD directory holding a mesh, lowest resolution first."""
        found = [d for d in sorted(self.root.iterdir())
                 if d.is_dir() and any(d.glob("*.obj"))]
        return sorted(found, key=lambda d: d.name, reverse=True)

    def metadata(self, observation: Path) -> dict:
        person = observation / "person_metadata.json"
        pose = observation / "pose_metadata.json"
        return {
            "person": json.loads(person.read_text(encoding="utf-8")) if person.exists() else {},
            "pose": json.loads(pose.read_text(encoding="utf-8")) if pose.exists() else {},
        }

    def garment_description(self, observation: Path) -> dict:
        # The shipped JSON uses Title Case with spaces ("Upper Body
        # Clothing"); the dataset's web API uses snake_case for the same
        # fields. Read the shipped file's spelling.
        pose = self.metadata(observation)["pose"]
        return {
            "upper": pose.get("Upper Body Clothing"),
            "lower": pose.get("Lower Body Clothing"),
            "full_body": pose.get("Full Body Clothing"),
            "footwear": pose.get("Footwear"),
            "outfit_type": pose.get("Outfit Type"),
            "accessories": {
                key.replace(" Accessories", "").lower(): pose[key]
                for key in pose
                if key.endswith("Accessories") and pose[key] not in (None, "None")
            },
        }

    def load(self, path: Path, **kwargs) -> NormalizedBodySurface:
        """`path` is an LOD directory (e.g. .../hsrd/lod2)."""
        observation = Path(path)
        obj = next(iter(sorted(observation.glob("*.obj"))), None)
        if obj is None:
            raise FileNotFoundError(f"no OBJ under {observation}")

        mesh = trimesh.load(obj, force="mesh", process=False)
        vertices = np.asarray(mesh.vertices, dtype=np.float64)

        stature_cm = self.metadata(observation)["person"].get("Height")
        if stature_cm is None:
            raise ValueError(
                f"{obj.name}: no recorded stature to verify the unit against — "
                "units are never guessed"
            )
        stature_mm = float(stature_cm) * 10.0
        # the long axis of a standing scan, whatever axis order it shipped in
        extent = float(np.max(vertices.max(axis=0) - vertices.min(axis=0)))

        scale = None
        for unit in ("m", "cm", "mm"):
            candidate = extent * scale_to_mm(unit, source=str(obj))
            if STATURE_TOLERANCE_LOW * stature_mm <= candidate <= STATURE_TOLERANCE_HIGH * stature_mm:
                scale = scale_to_mm(unit, source=str(obj))
                verified_unit = unit
                break
        if scale is None:
            raise ValueError(
                f"{obj.name}: extent {extent:.3f} matches no unit against a "
                f"recorded stature of {stature_cm} cm — refusing to guess"
            )

        return NormalizedBodySurface(
            vertices_mm=vertices * scale,
            faces=np.asarray(mesh.faces, dtype=np.int64),
            source_type=self.source_type,
            source_id=f"hsrd/{observation.name}/{obj.stem}",
            transform_to_canonical=_Z_UP_TO_Y_UP,
            meta={
                "dataset": "hsrd",
                "licence": "CC BY 4.0",
                "lod": observation.name,
                "verified_unit": verified_unit,
                "recorded_stature_mm": stature_mm,
                "scan_extent_mm": extent * scale,
                # the scan is taller than the person by whatever the boots and
                # hat add; this is a garment artefact, not a measurement
                "stature_excess_mm": round(extent * scale - stature_mm, 1),
                "clothed": True,
                "garment": self.garment_description(observation),
            },
        )
