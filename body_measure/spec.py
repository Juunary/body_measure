"""Load and validate measurement-spec.v1.yaml.

The spec file is the contract: result JSON must contain exactly its
measurement keys, and code must not invent measurements outside it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

SPEC_FILENAME = "measurement-spec.v1.yaml"


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class MeasurementSpec:
    name: str
    definition: str
    definition_verified: bool
    method: str
    no_reference: bool
    known_deviations: tuple[str, ...]
    route: tuple[str, ...]
    landmarks: tuple[str, ...]
    implementation_status: str
    requires: tuple[str, ...] = ()
    #: how much this measurement matters to the garment currently being
    #: built. "core" must work; "deferred" may fail without blocking a
    #: slice. Scope, not difficulty — see the spec header.
    priority: str = "core"
    #: [lo, hi] in mm that a human body can have for this measurement.
    #: Outside it the core refuses — null plus `outside_plausible_range`,
    #: never a corrected number (measure/range_gate.py, decision #39).
    #: None means the spec did not say; a test pins that the shipped spec
    #: always says, so the unspecified branch is unreachable in practice.
    plausible_mm: tuple[float, float] | None = None


@dataclass(frozen=True)
class Spec:
    version: int
    standard: str
    measurements: dict[str, MeasurementSpec]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.measurements)

    @property
    def core_names(self) -> tuple[str, ...]:
        """Measurements the current garment actually needs. Reporting may
        summarise over these; nothing may silently drop the rest."""
        return tuple(n for n, m in self.measurements.items() if m.priority == "core")


def _parse_plausible_mm(name: str, raw) -> tuple[float, float] | None:
    """A malformed bound is refused rather than ignored: a gate nobody can
    trust the shape of is worse than no gate."""
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise SpecError(f"measurement '{name}': plausible_mm must be [lo, hi]")
    try:
        lo, hi = float(raw[0]), float(raw[1])
    except (TypeError, ValueError) as exc:
        raise SpecError(f"measurement '{name}': plausible_mm is not numeric") from exc
    if not 0.0 <= lo < hi:
        raise SpecError(
            f"measurement '{name}': plausible_mm must satisfy 0 <= lo < hi, got [{lo}, {hi}]")
    return (lo, hi)


def default_spec_path() -> Path:
    return Path(__file__).resolve().parents[1] / SPEC_FILENAME


def load_spec(path: Path | None = None) -> Spec:
    path = path or default_spec_path()
    if not path.is_file():
        raise SpecError(f"spec file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "measurements" not in raw:
        raise SpecError(f"spec file has no 'measurements' mapping: {path}")

    measurements: dict[str, MeasurementSpec] = {}
    for name, entry in raw["measurements"].items():
        if not isinstance(entry, dict):
            raise SpecError(f"measurement '{name}' is not a mapping")
        for required in ("definition", "definition_verified", "method"):
            if required not in entry:
                raise SpecError(f"measurement '{name}' missing '{required}'")
        measurements[name] = MeasurementSpec(
            name=name,
            definition=entry["definition"],
            definition_verified=bool(entry["definition_verified"]),
            method=entry["method"],
            no_reference=bool(entry.get("no_reference", False)),
            known_deviations=tuple(entry.get("known_deviations", ())),
            route=tuple(entry.get("route", ())),
            landmarks=tuple(entry.get("landmarks", ())),
            implementation_status=entry.get("implementation_status", "not_implemented"),
            requires=tuple(entry.get("requires", ())),
            priority=str(entry.get("priority", "core")),
            plausible_mm=_parse_plausible_mm(name, entry.get("plausible_mm")),
        )
    return Spec(
        version=int(raw.get("spec_version", 0)),
        standard=str(raw.get("standard", "")),
        measurements=measurements,
    )
