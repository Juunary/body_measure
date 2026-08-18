"""Result schema. The measurements dict contains exactly the keys of
measurement-spec.v1.yaml — no more, no fewer. Unimplemented or failed
measurements report null values with a quality flag instead of a number."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .spec import Spec

SCHEMA_VERSION = 1


@dataclass
class MeasurementValue:
    raw_contour_mm: float | None = None
    taut_tape_hull_mm: float | None = None
    selected_value_mm: float | None = None
    selection_method: str | None = None
    method: str | None = None
    quality: list[str] = field(default_factory=lambda: ["not_implemented"])
    #: accepted | manual_review | rejected — manual_review values may be
    #: displayed but are excluded from headline (accepted) statistics
    disposition: str = "rejected"
    #: {"chord_mm": float, "ratio": float} when a scan hole was closed
    gap: dict | None = None


@dataclass
class MeasurementResult:
    source_type: str
    source_id: str
    pathway: str                      # "estimated" | "fitted_vertices"
    measurements: dict[str, MeasurementValue]
    pose: str = "standing"
    units: str = "mm"
    schema_version: int = SCHEMA_VERSION
    landmarks: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, **kwargs) -> str:
        kwargs.setdefault("indent", 2)
        return json.dumps(self.to_dict(), **kwargs)


def empty_result(spec: Spec, *, source_type: str, source_id: str, pathway: str) -> MeasurementResult:
    return MeasurementResult(
        source_type=source_type,
        source_id=source_id,
        pathway=pathway,
        measurements={name: MeasurementValue() for name in spec.names},
    )
