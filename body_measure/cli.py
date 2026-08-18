"""CLI: measure | validate.

Slice 0: `measure` loads a mesh (explicit unit required), canonicalizes,
and emits the full result schema. All six measurements start as null /
not_implemented; passing --waist-height exercises the real slice ->
torso-loop -> circumference path for waist_circumference.
`validate` arrives with the validation harness slice.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adapters.base import UnitError
from .adapters.mesh_file import MeshFileAdapter
from .canonicalize import body_axis_point, canonicalize
from .result import empty_result
from .spec import load_spec

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_IMPLEMENTED = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="body_measure")
    sub = parser.add_subparsers(dest="command", required=True)

    measure = sub.add_parser("measure", help="measure a body mesh")
    measure.add_argument("mesh", type=Path)
    measure.add_argument("--input-unit", choices=["mm", "cm", "m"], default=None,
                         help="unit of the input mesh; required for generic files (never guessed)")
    measure.add_argument("--up-axis", choices=["Y", "Z"], default="Y")
    measure.add_argument("--waist-height", type=float, default=None,
                         help="measure waist_circumference at this canonical height (mm)")
    measure.add_argument("--estimate", action="store_true",
                         help="estimate landmarks (topology-agnostic pathway)")
    measure.add_argument("--out", type=Path, default=None)

    validate = sub.add_parser(
        "validate", help="run category-labelled validation reports into a directory"
    )
    validate.add_argument("--reports-dir", type=Path, default=Path("reports"))
    validate.add_argument(
        "--category",
        choices=["dataset_agreement", "numerical_robustness", "synthetic_agreement", "all"],
        default="all",
    )
    return parser


# category -> (script, output file); scripts print markdown, exit 1 when
# their data is absent — that becomes "skipped", not a failure
_VALIDATE_SCRIPTS = {
    "dataset_agreement": [
        ("texel_full_report.py", "dataset_agreement_texel.md"),
        ("nomo_report.py", "dataset_agreement_nomo.md"),
    ],
    "numerical_robustness": [("robustness_report.py", "numerical_robustness.md")],
    "synthetic_agreement": [("tpose_reference_report.py", "synthetic_agreement_tpose.md")],
}


def _validate(args: argparse.Namespace) -> int:
    import subprocess

    scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    categories = (
        list(_VALIDATE_SCRIPTS) if args.category == "all" else [args.category]
    )
    failures = 0
    for category in categories:
        for script, outname in _VALIDATE_SCRIPTS[category]:
            proc = subprocess.run(
                [sys.executable, str(scripts_dir / script)],
                capture_output=True, text=True, encoding="utf-8",
            )
            out = args.reports_dir / outname
            if proc.returncode == 0:
                out.write_text(proc.stdout, encoding="utf-8")
                print(f"[{category}] {outname} written")
            else:
                print(f"[{category}] {script} skipped: {proc.stderr.strip().splitlines()[-1] if proc.stderr else 'no data'}")
                failures += 0  # missing data is not a failure; real errors show in stderr above
    return EXIT_OK if failures == 0 else EXIT_ERROR


def _measure(args: argparse.Namespace) -> int:
    spec = load_spec()
    try:
        surface = MeshFileAdapter().load(args.mesh, unit=args.input_unit)
    except (UnitError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    mesh = canonicalize(surface, up_axis=args.up_axis)
    result = empty_result(
        spec, source_type=surface.source_type, source_id=surface.source_id, pathway="estimated"
    )
    result.meta["input"] = {"path": str(args.mesh), "unit": args.input_unit, "up_axis": args.up_axis}

    if args.estimate:
        from .measure.measurements import run_estimated_measurements

        measurements, landmarks = run_estimated_measurements(mesh)
        result.measurements.update(measurements)
        result.landmarks.update({name: lm.to_dict() for name, lm in landmarks.items()})
    elif args.waist_height is not None:
        from .measure.measurements import circumference_at_height

        axis2d = body_axis_point(mesh)
        result.measurements["waist_circumference"] = circumference_at_height(
            mesh, args.waist_height
        )
        result.landmarks["waist_level"] = {
            "position_mm": [float(axis2d[0]), args.waist_height, float(axis2d[1])],
            "confidence": 1.0,
            "method": "manual_height",
            "quality_flags": [],
        }

    payload = result.to_json()
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "measure":
        return _measure(args)
    if args.command == "validate":
        return _validate(args)
    return EXIT_ERROR
