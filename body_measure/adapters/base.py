"""Adapter contract: every input (dataset, generic file, scanner) is
normalized to a NormalizedBodySurface before the measurement core sees it.

Rules enforced here:
- Units are never guessed. An adapter must know its unit (metadata) or be
  told one explicitly; otherwise loading fails with UnitError.
- Reference values an adapter returns must stay inside its declared
  `provides` frozenset (AdapterContractError otherwise) — same philosophy as
  dpp-prototype's Source.provides contract.

Reference-value tiers used across the project (see docs/measurement-audit.md):
  analytic_expected  — closed-form values of synthetic shapes (true ground truth)
  synthetic_reference — another implementation on identical synthetic bodies
  dataset_reference  — automatic values shipped with a dataset (vendor pipeline)
  manual_reference   — trained-measurer manual values (post-scanner phase only)
Adapters serve dataset_reference: agreement with them is NOT accuracy.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CANONICAL_COORDINATE_SYSTEM = "Y_UP_RIGHT_HANDED"

UNIT_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0}


class UnitError(ValueError):
    """Raised when a mesh's unit is unknown and no explicit unit was given."""


class AdapterContractError(RuntimeError):
    """Raised when an adapter emits reference values outside its `provides` set."""


@dataclass
class NormalizedBodySurface:
    vertices_mm: np.ndarray          # (n, 3) float64, millimetres
    faces: np.ndarray                # (m, 3) int
    source_type: str                 # "synthetic_smpl" | "dataset_scan" | "vitronic_scan" | "mesh_file"
    source_id: str
    coordinate_system: str = CANONICAL_COORDINATE_SYSTEM
    normals: np.ndarray | None = None
    transform_to_canonical: np.ndarray | None = None  # 4x4, applied by canonicalize
    meta: dict = field(default_factory=dict)


class Adapter(ABC):
    """A named input source with a declared reference-value capability set."""

    name: str
    source_type: str
    #: measurement names (from measurement-spec) this adapter can supply
    #: dataset reference values for. Empty for sources without references.
    provides: frozenset[str] = frozenset()

    @abstractmethod
    def load(self, path: Path, **kwargs) -> NormalizedBodySurface: ...

    def dataset_reference(self, path: Path, **kwargs) -> dict[str, float]:
        """Dataset-provided reference values in mm, keyed by spec names.
        These come from the dataset's own (automatic) pipeline — agreement
        with them is dataset_agreement, never measurement accuracy."""
        return {}

    def checked_dataset_reference(self, path: Path, **kwargs) -> dict[str, float]:
        values = self.dataset_reference(path, **kwargs)
        extra = set(values) - self.provides
        if extra:
            raise AdapterContractError(
                f"adapter '{self.name}' emitted reference values outside its "
                f"declared provides set: {sorted(extra)}"
            )
        return values


def scale_to_mm(unit: str | None, *, source: str) -> float:
    if unit is None:
        raise UnitError(
            f"unit for '{source}' is unknown; pass an explicit unit "
            f"({', '.join(UNIT_TO_MM)}). Units are never guessed."
        )
    try:
        return UNIT_TO_MM[unit]
    except KeyError:
        raise UnitError(f"unsupported unit '{unit}' (expected one of {', '.join(UNIT_TO_MM)})") from None
