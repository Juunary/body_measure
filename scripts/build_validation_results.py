"""Build reports/validation-results.json — the single structured source
from which BOTH formal reports (ko/en) are rendered. Never hand-edit the
reports; regenerate them from this file.

Run:  .venv\\Scripts\\python scripts\\build_validation_results.py
"""
from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import trimesh  # noqa: E402

from body_measure.adapters.mesh_file import MeshFileAdapter  # noqa: E402
from body_measure.adapters.nomo import NomoAdapter  # noqa: E402
from body_measure.adapters.texel import TexelAdapter  # noqa: E402
from body_measure.canonicalize import canonicalize  # noqa: E402
from body_measure.measure.measurements import run_estimated_measurements  # noqa: E402
from body_measure.measure.surface_path import EdgeGraph, surface_path_length_mm  # noqa: E402
from body_measure.spec import load_spec  # noqa: E402
from body_measure.validate.stats import (  # noqa: E402
    NOMO_MAPPING,
    TEXEL_MAPPING,
    quality_bucket,
    summarize,
)

TEXEL_ROOT = PROJECT_ROOT / "data" / "external" / "texel"
NOMO_ROOT = (PROJECT_ROOT / "data" / "external" / "nomo"
             / "NOMO-3d-400-scans_and_tc2_measurements" / "extracted")
SMPL_OBJ = PROJECT_ROOT / "data" / "generated" / "smpl_neutral0_apose.obj"
OUT = PROJECT_ROOT / "reports" / "validation-results.json"


def provenance() -> dict:
    def git(*args):
        return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True,
                              text=True).stdout.strip()

    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "python": platform.python_version(),
        "packages": {p: pkg_version(p) for p in ("numpy", "trimesh", "shapely", "scipy")},
        "spec_version": load_spec().version,
        "spec_sha256": sha256(PROJECT_ROOT / "measurement-spec.v1.yaml"),
        "thresholds_sha256": sha256(
            PROJECT_ROOT / "body_measure" / "validate" / "thresholds.py"),
        "texel_part1_persons": len(TexelAdapter().persons(TEXEL_ROOT)),
    }


def texel_agreement() -> dict:
    adapter = TexelAdapter()
    spec = load_spec()
    per_measurement: dict[str, list[dict]] = {name: [] for name in spec.names}
    sleeve_audit_rows = []
    for person in adapter.persons(TEXEL_ROOT):
        mesh = canonicalize(adapter.load(person))
        refs = adapter.checked_dataset_reference(person)
        aux = adapter.aux_reference(person)
        measurements, landmarks = run_estimated_measurements(mesh)
        for name in spec.names:
            value = measurements[name]
            ref = refs.get(name)
            delta = (value.selected_value_mm - ref
                     if value.selected_value_mm is not None and ref is not None else None)
            per_measurement[name].append({
                "person": person.name, "delta": delta,
                "bucket": quality_bucket(value), "flags": value.quality,
            })
        # sleeve segment audit (definition verdicts from measurement-audit.md)
        back_neck = landmarks.get("back_neck_point")
        shoulder = landmarks.get("shoulder_point_right") or landmarks.get("shoulder_point_left")
        wrist = landmarks.get("wrist_point_right") or landmarks.get("wrist_point_left")
        if back_neck is not None and shoulder is not None and wrist is not None:
            graph = EdgeGraph(mesh)
            seg_bs, _ = surface_path_length_mm(graph, [back_neck.position_mm, shoulder.position_mm])
            seg_sw, _ = surface_path_length_mm(graph, [shoulder.position_mm, wrist.position_mm])
            sleeve_audit_rows.append({
                "person": person.name,
                "back_neck_to_shoulder_mm": seg_bs,
                "shoulder_to_wrist_mm": seg_sw,
                "shoulder_to_wrist_minus_m2": (
                    seg_sw - aux["outer_arm_length"]
                    if seg_sw is not None and "outer_arm_length" in aux else None),
                "combined_minus_m55": (
                    seg_bs + seg_sw - aux["back_neck_to_wrist"]
                    if seg_bs is not None and seg_sw is not None
                    and "back_neck_to_wrist" in aux else None),
            })
    return {
        "dataset": "texel_part1_portal_mx",
        "reference_kind": "dataset_reference (BodyFit automatic values, vendor pipeline)",
        "label": "pilot baseline (N=10, portal_mx)",
        "measurements": {
            name: {"mapping": TEXEL_MAPPING[name], "entries": entries,
                   "summary": summarize(entries)}
            for name, entries in per_measurement.items()
        },
        "sleeve_segment_audit": {
            "verdicts": {
                "back_neck_to_shoulder_vs_m36": "mismatch (m36 origin is the side neck point) — no delta",
                "shoulder_to_wrist_vs_m2": "approximate (posture differs: hanging vs bent elbow)",
                "combined_vs_m55": "approximate (elbow waypoint omitted; posture differs)",
            },
            "rows": sleeve_audit_rows,
        },
    }


def nomo_agreement(limit: int = 10) -> dict:
    adapter = NomoAdapter(NOMO_ROOT)
    per_measurement: dict[str, list[dict]] = {name: [] for name in NOMO_MAPPING}
    for subject in adapter.subjects("male")[:limit]:
        try:
            mesh = canonicalize(adapter.load(subject))
        except (ValueError, FileNotFoundError):
            for name in per_measurement:
                per_measurement[name].append(
                    {"person": subject, "delta": None, "bucket": "rejected",
                     "flags": ["load_failed"]})
            continue
        refs = adapter.checked_dataset_reference(subject)
        measurements, _ = run_estimated_measurements(mesh)
        for name in per_measurement:
            value = measurements[name]
            ref = refs.get(name)
            delta = (value.selected_value_mm - ref
                     if value.selected_value_mm is not None and ref is not None else None)
            per_measurement[name].append({
                "person": subject, "delta": delta,
                "bucket": quality_bucket(value), "flags": value.quality,
            })
    return {
        "dataset": "nomo_3d_400_male_subset",
        "reference_kind": "dataset_reference (TC2 automatic values)",
        "label": f"pilot baseline (N={limit}, male)",
        "measurements": {
            name: {"mapping": NOMO_MAPPING[name], "entries": entries,
                   "summary": summarize(entries)}
            for name, entries in per_measurement.items()
        },
    }


def yaw_sweep() -> dict:
    """Multi-angle yaw invariance on the SMPL A-pose body — replaces the
    former prose claim with measured maxima."""
    mesh = canonicalize(MeshFileAdapter().load(SMPL_OBJ, unit="m"))
    base, _ = run_estimated_measurements(mesh)
    names = ("waist_circumference", "chest_circumference", "neck_circumference")
    angles = (45, 90, 180, 270)
    max_delta = {name: 0.0 for name in names}
    for angle in angles:
        turned = mesh.copy()
        turned.apply_transform(
            trimesh.transformations.rotation_matrix(np.deg2rad(angle), [0, 1, 0]))
        got, _ = run_estimated_measurements(turned)
        for name in names:
            if base[name].selected_value_mm and got[name].selected_value_mm:
                max_delta[name] = max(
                    max_delta[name],
                    abs(got[name].selected_value_mm - base[name].selected_value_mm))
    return {"body": "smpl_neutral0_apose", "angles_deg": list(angles),
            "max_abs_delta_mm": max_delta}


def tpose_agreement() -> dict:
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "tpose_reference_report.py")],
        capture_output=True, text=True, encoding="utf-8")
    parsed = {}
    for line in proc.stdout.splitlines():
        m = re.match(r"- (\w+): ([+-]?[\d.]+) / ([\d.]+) / (\d+)", line.strip())
        if m:
            parsed[m.group(1)] = {"bias": float(m.group(2)),
                                  "max_ae": float(m.group(3)), "n": int(m.group(4))}
    return {
        "reference": "SMPL-Anthropometry (MIT) on identical vertices at identical landmark heights",
        "available": proc.returncode == 0 and bool(parsed),
        "summaries": parsed,
    }


def main() -> int:
    results = {
        "provenance": provenance(),
        "scope_statement": {
            "ko": "6종 측정 파이프라인과 4종 선행 검증 체계 구현 완료. 실물 제작 적용을 위한 계측 정확도 검증은 미완료.",
            "en": "Six-measurement pipeline and four pre-arrival validation categories implemented. Metrological accuracy validation for production use is NOT yet performed.",
        },
        "categories": {
            "dataset_agreement": {
                "texel": texel_agreement() if (TEXEL_ROOT / "Part1").is_dir() else None,
                "nomo": nomo_agreement() if NOMO_ROOT.is_dir() else None,
            },
            "numerical_robustness": {
                "yaw_sweep": yaw_sweep() if SMPL_OBJ.exists() else None,
            },
            "synthetic_agreement": tpose_agreement(),
        },
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
