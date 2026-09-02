"""CLI: measure | validate.

`measure` loads a mesh (explicit unit required), canonicalizes it, and
reports the spec's measurements. It prints a table by default and JSON
with --format json; --out always writes JSON, because that is the result
schema other tools read.

--view renders the scan in 3-D with each measurement drawn where it was
actually taken. --garment polo adds the garment prototypes, which are NOT
in the spec and are labelled as such everywhere they appear.
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
    measure.add_argument("--format", choices=["table", "json"], default="table",
                         help="stdout format; --out always writes JSON")
    measure.add_argument("--garment", choices=["none", "polo"], default="none",
                         help="add garment prototypes — NOT in the spec, unvalidated")
    measure.add_argument("--size-chart",
                         choices=["none", "en13402", "en13402-women", "lacoste"],
                         default="none",
                         help="assign a ready-to-wear size from the measured body")
    measure.add_argument("--clothed", action="store_true",
                         help="the subject is dressed; records the measured_clothed "
                              "pathway, so the numbers read as the garment's")
    measure.add_argument("--pattern", choices=["none", "polo"], default="none",
                         help="check the body against what a pattern draft "
                              "consumes, and report what is missing")
    measure.add_argument("--population", choices=["men", "women"], default=None,
                         help="who the subject is; a mesh does not say, and the "
                              "size charts are men's")
    measure.add_argument("--view", nargs="?", const="", default=None, metavar="PNG",
                         help="render a 3-D view; optional path, else next to the mesh")
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


def _print_table(spec, result, prototypes, mesh_path) -> None:
    """Terminal report. Values are millimetres unless the row says otherwise."""
    from .validate.stats import quality_bucket

    width = max(len(name) for name in spec.names)
    print(f"\n{mesh_path}")
    print(f"{'measurement':{width}s} {'value':>12s}  {'quality':14s} flags")
    print("-" * (width + 46))
    for name in spec.names:
        value = result.measurements[name]
        shown = "—" if value.selected_value_mm is None else f"{value.selected_value_mm:9.1f} mm"
        flags = ",".join(f for f in value.quality if f != "ok")
        priority = spec.measurements[name].priority
        marker = " " if priority == "core" else "."
        print(f"{name:{width}s} {shown:>12s}  {quality_bucket(value):14s} {flags[:46]}{marker}")

    if prototypes:
        print(f"\n{'garment prototype':{width}s} {'value':>12s}   NOT in the spec — no definition")
        print("-" * (width + 46) + "   audit, no reference, no battery")
        for value in prototypes.values():
            if value.value is None:
                shown = "—"
            elif value.unit == "deg":
                shown = f"{value.value:9.1f} °"
            else:
                shown = f"{value.value:9.1f} mm"
            note = value.note or ",".join(value.flags[:2])
            print(f"{value.key:{width}s} {shown:>12s}  {note[:52]}")
    print("\n. = deferred priority (outside the current garment)")


def _print_size(sizing) -> None:
    chart = sizing.chart
    print()
    if sizing.assigned:
        line = f"  size {sizing.label}"
        if sizing.alternative:
            line += f"  (or {sizing.alternative})"
        print(line)
    else:
        print("  size —")
    print(f"    chart      {chart.name}")
    print(f"    basis      {chart.primary_measurement}, {chart.dimension_kind} measurement, "
          f"{chart.population}")
    print(f"    reason     {sizing.reason}")
    if sizing.flags:
        print(f"    flags      {','.join(sizing.flags)}")
    print(f"    source     {chart.source}")
    print(f"    checked    {chart.checked}")


def _print_readiness(readiness) -> None:
    print()
    print(f"  pattern readiness — {readiness.garment}: "
          f"{readiness.verdict.replace('_', ' ')}")
    print(f"    {len(readiness.draftable)} of {len(readiness.statuses)} "
          "dimensions can carry a drafted line\n")
    width = max(len(s.requirement.key) for s in readiness.statuses)
    for status in readiness.statuses:
        mark = "+" if status.draftable else "-"
        shown = ("—" if status.value is None
                 else f"{status.value:9.1f} {status.unit}")
        print(f"    {mark} {status.requirement.key:{width}s} {shown:>14s}  "
              f"{status.bucket:14s} {status.note[:44]}")
    print()
    for note in readiness.notes:
        for line in _wrap(note, 92):
            print(f"    {line}")
        print()


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _measure(args: argparse.Namespace) -> int:
    spec = load_spec()
    try:
        surface = MeshFileAdapter().load(args.mesh, unit=args.input_unit)
    except (UnitError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    mesh = canonicalize(surface, up_axis=args.up_axis)
    # a mesh file does not say whether its subject was dressed, so the
    # caller does; every girth on a clothed scan is the garment's
    result = empty_result(
        spec, source_type=surface.source_type, source_id=surface.source_id,
        pathway="measured_clothed" if args.clothed else "estimated",
    )
    result.meta["input"] = {"path": str(args.mesh), "unit": args.input_unit, "up_axis": args.up_axis}

    measurements, landmarks = {}, {}
    if args.estimate:
        from .measure.measurements import run_estimated_measurements

        measurements, landmarks = run_estimated_measurements(mesh)
        result.measurements.update(measurements)
        result.landmarks.update({name: lm.to_dict() for name, lm in landmarks.items()})
    elif args.waist_height is not None:
        from .measure.measurements import circumference_at_height
        from .measure.range_gate import gate_human_range

        axis2d = body_axis_point(mesh)
        # A hand-given height bypasses the estimated pathway and therefore
        # its gate; a typo in --waist-height must not become a measurement.
        result.measurements.update(gate_human_range({
            "waist_circumference": circumference_at_height(mesh, args.waist_height)
        }))
        result.landmarks["waist_level"] = {
            "position_mm": [float(axis2d[0]), args.waist_height, float(axis2d[1])],
            "confidence": 1.0,
            "method": "manual_height",
            "quality_flags": [],
        }

    prototypes = None
    if args.garment == "polo":
        if not args.estimate:
            print("error: --garment needs --estimate; the prototypes are built on "
                  "the estimated landmarks", file=sys.stderr)
            return EXIT_ERROR
        from .garment_prototypes import run_prototypes

        prototypes = run_prototypes(mesh, measurements, landmarks)
        # kept out of `measurements`: the result schema is exactly the spec
        result.meta["garment_prototypes"] = {
            key: value.to_dict() for key, value in prototypes.items()
        }

    if args.out:
        args.out.write_text(result.to_json(), encoding="utf-8")
    elif args.format == "json":
        print(result.to_json())
    else:
        _print_table(spec, result, prototypes, args.mesh)

    if args.size_chart != "none":
        if not args.estimate:
            print("error: --size-chart needs --estimate; a size is assigned from "
                  "measured girths", file=sys.stderr)
            return EXIT_ERROR
        from .sizing import CHARTS, assign

        sizing = assign(result.measurements, chart=CHARTS[args.size_chart],
                        pathway=result.pathway, population=args.population)
        result.meta["size"] = sizing.to_dict()
        if args.out:
            args.out.write_text(result.to_json(), encoding="utf-8")
        elif args.format != "json":
            _print_size(sizing)

    if args.pattern != "none":
        if not args.estimate:
            print("error: --pattern needs --estimate; readiness is judged on "
                  "measured dimensions", file=sys.stderr)
            return EXIT_ERROR
        from .pattern_readiness import assess

        readiness = assess(result.measurements, prototypes, garment=args.pattern)
        result.meta["pattern_readiness"] = readiness.to_dict()
        if args.out:
            args.out.write_text(result.to_json(), encoding="utf-8")
        elif args.format != "json":
            _print_readiness(readiness)

    if args.view is not None:
        if not args.estimate:
            print("error: --view needs --estimate; there is nothing to draw without "
                  "landmarks", file=sys.stderr)
            return EXIT_ERROR
        from .viewer import render

        png = Path(args.view) if args.view else args.mesh.with_suffix(".measured.png")
        n = render(mesh, result.measurements, landmarks, png,
                   prototypes=prototypes, subtitle=str(args.mesh))
        print(f"\n{n} measured curves drawn -> {png}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "measure":
        return _measure(args)
    if args.command == "validate":
        return _validate(args)
    return EXIT_ERROR
