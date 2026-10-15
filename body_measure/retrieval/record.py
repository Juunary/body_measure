"""One scan as a row the index can hold: who it is (as far as a licence
lets us say), what the pipeline measured on it, how much each value is
trusted, which size each chart gave it, and which pipeline produced all
of that. A record never holds the mesh. A licensed scan stays where its
licence put it, and a synthetic body is regenerable from `gen`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .features import FEATURE_KEYS, PROTOTYPE_KEYS, SPEC_KEYS, STATURE_KEY

RECORD_SCHEMA_VERSION = 1


class LicenceClass(str, Enum):
    """Where a record may go. Decided per source, never per request."""
    #: HSRD-100 (CC BY 4.0): the only class cleared for public material
    PUBLIC = "public_hsrd"
    #: generated from SMPL under the project's own licence; may be moved
    #: to the user's own compute
    SYNTHETIC = "synthetic_smpl"
    #: Texel (CC BY-NC), NOMO (no redistribution), CAPE (single user) and
    #: anything derived from them; stays on this workstation
    LOCAL_ONLY = "local_only_licensed"


#: the classes `RecordStore.export` will write anywhere other than here
EXPORTABLE = frozenset({LicenceClass.PUBLIC, LicenceClass.SYNTHETIC})

SPLITS = ("train", "test", "holdout", "unsplit")

#: quality buckets whose value the pipeline itself would not accept, the
#: same two `sizing.assign` refuses on; a feature built on them would feed
#: the index our own failures as body variation
UNTRUSTED_BUCKETS = frozenset({"rejected", "manual_review"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ScanRecord:
    record_id: str
    source_type: str                  # synthetic_smpl | dataset_scan | mesh_file | ...
    source_id: str
    licence_class: LicenceClass
    population: str | None            # men | women | None (a mesh does not say)
    pose: str
    clothed: bool
    split: str
    #: FEATURE_KEYS minus stature, in the key's unit (mm; deg for
    #: shoulder_slope), None when the pipeline gave nothing
    values: dict[str, float | None]
    #: quality bucket per key: validate.stats.quality_bucket for spec
    #: keys, clean / flagged / rejected for prototypes
    quality: dict[str, str]
    stature_mm: float | None
    #: chart key -> label the chart gave this body, None when it refused
    size_labels: dict[str, str | None]
    spec_version: int
    pipeline_hash: str
    betas: tuple[float, ...] | None = None
    smpl_model_id: str | None = None
    #: how to regenerate a synthetic body: seed, index, gender, abduction
    gen: dict | None = None
    embedding_version: str | None = None
    created_utc: str = field(default_factory=_now)
    record_schema_version: int = RECORD_SCHEMA_VERSION

    def __post_init__(self):
        if not isinstance(self.licence_class, LicenceClass):
            object.__setattr__(self, "licence_class", LicenceClass(self.licence_class))
        if self.split not in SPLITS:
            raise ValueError(f"split {self.split!r} is not one of {SPLITS}")
        if self.betas is not None:
            object.__setattr__(self, "betas", tuple(float(b) for b in self.betas))
        unknown = set(self.values) - set(FEATURE_KEYS)
        if unknown:
            raise ValueError(f"values carry keys outside FEATURE_KEYS: {sorted(unknown)}")

    # ------------------------------------------------------------ features --
    def usable(self, key: str) -> bool:
        if key == STATURE_KEY:
            return self.stature_mm is not None
        return (self.values.get(key) is not None
                and self.quality.get(key, "clean") not in UNTRUSTED_BUCKETS)

    def feature_values(self) -> dict[str, float | None]:
        out = dict(self.values)
        out[STATURE_KEY] = self.stature_mm
        return out

    def feature_usable(self) -> dict[str, bool]:
        return {key: self.usable(key) for key in FEATURE_KEYS}

    @property
    def exportable(self) -> bool:
        return self.licence_class in EXPORTABLE

    # ---------------------------------------------------------------- i/o --
    def to_dict(self) -> dict:
        data = asdict(self)
        data["licence_class"] = self.licence_class.value
        data["betas"] = None if self.betas is None else list(self.betas)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict) -> "ScanRecord":
        data = dict(data)
        version = int(data.get("record_schema_version", 0))
        if version != RECORD_SCHEMA_VERSION:
            raise ValueError(
                f"record schema {version} is not the current {RECORD_SCHEMA_VERSION}; "
                "rebuild the store rather than reading it with the wrong reader")
        betas = data.get("betas")
        data["betas"] = None if betas is None else tuple(betas)
        return cls(**data)

    @classmethod
    def from_json(cls, line: str) -> "ScanRecord":
        return cls.from_dict(json.loads(line))


def prototype_bucket(value) -> str:
    """A PrototypeValue has flags, not a disposition: no value is
    rejected, any flag is flagged, the rest is clean."""
    if value is None or value.value is None:
        return "rejected"
    return "flagged" if value.flags else "clean"


def stature_of(mesh) -> float:
    """Height of a canonical mesh (Y-up, floor at 0) in mm."""
    return float(mesh.bounds[1][1] - mesh.bounds[0][1])


def build_record(*, record_id: str, source_type: str, source_id: str,
                 licence_class: LicenceClass, measurements: dict, prototypes: dict | None,
                 stature_mm: float | None, population: str | None, size_labels: dict,
                 spec_version: int, pipeline_hash: str, pose: str = "standing_a_pose",
                 clothed: bool = False, split: str = "unsplit",
                 betas=None, smpl_model_id: str | None = None, gen: dict | None = None,
                 ) -> ScanRecord:
    """A record from what `run_estimated_measurements` and `run_prototypes`
    returned. Buckets come from validate.stats so the record trusts
    exactly what the rest of the project trusts."""
    from ..validate.stats import quality_bucket

    values: dict[str, float | None] = {}
    quality: dict[str, str] = {}
    for key in SPEC_KEYS:
        mv = measurements.get(key)
        if mv is None:
            values[key], quality[key] = None, "rejected"
            continue
        values[key] = None if mv.selected_value_mm is None else float(mv.selected_value_mm)
        quality[key] = quality_bucket(mv)
    for key in PROTOTYPE_KEYS:
        pv = (prototypes or {}).get(key)
        values[key] = None if pv is None or pv.value is None else float(pv.value)
        quality[key] = prototype_bucket(pv)
    return ScanRecord(
        record_id=record_id, source_type=source_type, source_id=source_id,
        licence_class=licence_class, population=population, pose=pose, clothed=clothed,
        split=split, values=values, quality=quality,
        stature_mm=None if stature_mm is None else float(stature_mm),
        size_labels=dict(size_labels), spec_version=spec_version, pipeline_hash=pipeline_hash,
        betas=betas, smpl_model_id=smpl_model_id, gen=gen,
    )
