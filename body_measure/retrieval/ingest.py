"""Scan in, record out: the one path every store builder and every query
takes from a canonical mesh to features, so a stored body and a queried
body are measured identically."""
from __future__ import annotations

from dataclasses import dataclass

from .features import STATURE_KEY
from .labels import label_record
from .record import LicenceClass, ScanRecord, build_record, stature_of


@dataclass
class Measured:
    measurements: dict
    prototypes: dict
    landmarks: dict
    stature_mm: float
    pose_ok: bool
    pose_reasons: list[str]


def measure_mesh(mesh, *, check_pose: bool = True) -> Measured | None:
    """Pose gate, then the estimated pathway and the garment prototypes.
    None when the pose gate refuses: an unmeasurable scan is not a record."""
    from ..garment_prototypes import run_prototypes
    from ..measure.measurements import run_estimated_measurements
    from ..pose_gate import check_pose as gate

    reasons: list[str] = []
    if check_pose:
        verdict = gate(mesh)
        if not verdict.ok:
            return None
        reasons = list(verdict.reasons)
    measurements, landmarks = run_estimated_measurements(mesh)
    prototypes = run_prototypes(mesh, measurements, landmarks)
    return Measured(measurements, prototypes, landmarks, stature_of(mesh), True, reasons)


def shirt_inputs(m: Measured) -> tuple[dict, dict]:
    from .estimator import query_from_measurements

    return query_from_measurements(m.measurements, m.prototypes, m.stature_mm)


def record_from_measured(m: Measured, *, record_id: str, source_type: str, source_id: str,
                         licence_class: LicenceClass, population: str | None,
                         spec_version: int, pipeline_hash: str, split: str = "unsplit",
                         clothed: bool = False, betas=None, smpl_model_id: str | None = None,
                         gen: dict | None = None) -> ScanRecord:
    values, usable = shirt_inputs(m)
    values.pop(STATURE_KEY, None)
    labels = label_record(m.measurements, population=population,
                          pathway="measured_clothed" if clothed else "estimated",
                          shirt_values=values, shirt_usable=usable)
    return build_record(
        record_id=record_id, source_type=source_type, source_id=source_id,
        licence_class=licence_class, measurements=m.measurements, prototypes=m.prototypes,
        stature_mm=m.stature_mm, population=population, size_labels=labels,
        spec_version=spec_version, pipeline_hash=pipeline_hash, clothed=clothed,
        split=split, betas=betas, smpl_model_id=smpl_model_id, gen=gen)
