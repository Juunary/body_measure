"""Can this line actually run on size labels?

Assigning a size to one body proves the code works. Running a production
line on size labels needs three numbers the single case cannot give:

  1. coverage    — how often a size comes out at all
  2. refusals    — and when it does not, why
  3. boundaries  — how often the chest sits close enough to a band edge
                   that this pipeline's own error could flip the label

The third is the one that decides whether ready-to-wear is enough. A body
10 mm from an edge is a coin toss at our measurement quality, and a coin
toss is a return.

The report also asks what a size label does NOT say. Subjects sharing one
label still differ in waist, neck, arm and back length, and the spread of
those differences is the size of the fit problem ready-to-wear leaves
unsolved — measured from this project's own data rather than argued.

Run (PowerShell):
  $env:PYTHONUTF8=1; .venv\\Scripts\\python scripts\\size_report.py [--chart en13402]

Datasets are named and their licences stated: aggregate statistics from
Texel and NOMO may be quoted internally, per docs/licenses/public-material.md.
Per-subject rows stay in the JSON, which reports/ keeps out of git.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.canonicalize import canonicalize  # noqa: E402
from body_measure.measure.measurements import run_estimated_measurements  # noqa: E402
from body_measure.sizing import CHARTS, assign  # noqa: E402
from body_measure.spec import load_spec  # noqa: E402
from body_measure.validate.stats import quality_bucket  # noqa: E402

OUT = PROJECT_ROOT / "reports" / "size_report.json"

#: What a size label is supposed to fix. Everything else on the body is
#: free to vary within it, and how much it varies is the point.
SECONDARY = ("waist_circumference", "neck_circumference",
             "upper_arm_girth", "back_length", "across_back_shoulder_width")

#: Buckets a spread may be computed over. arm_clipped is included because
#: it is a documented, systematic approximation rather than a failure;
#: manual_review and rejected are not, and a range that includes them
#: reports the pipeline's variance as the population's.
TRUSTED_BUCKETS = ("clean", "arm_clipped", "fallback")


def texel_subjects():
    from body_measure.adapters.texel import TexelAdapter

    root = PROJECT_ROOT / "data" / "external" / "texel"
    if not root.is_dir():
        return
    adapter = TexelAdapter()
    for path in sorted(adapter.persons(root)):
        population = "women" if path.name.lower().startswith("woman") else "men"
        yield f"texel/{path.name}", population, canonicalize(adapter.load(path))


def nomo_subjects(limit: int):
    from body_measure.adapters.nomo import NomoAdapter

    root = (PROJECT_ROOT / "data" / "external" / "nomo"
            / "NOMO-3d-400-scans_and_tc2_measurements" / "extracted")
    if not root.is_dir():
        return
    adapter = NomoAdapter(root)
    for subject in adapter.subjects()[:limit]:
        # NOMO's male set; the adapter keys its subjects by gender prefix
        yield f"nomo/{subject}", "men", canonicalize(adapter.load(subject))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chart", default="en13402", choices=sorted(CHARTS))
    ap.add_argument("--nomo", type=int, default=30, help="how many NOMO subjects")
    args = ap.parse_args()

    chart = CHARTS[args.chart]
    spec = load_spec()
    rows = []

    for source, population, mesh in list(texel_subjects()) + list(nomo_subjects(args.nomo)):
        measurements, _ = run_estimated_measurements(mesh)
        sizing = assign(measurements, chart=chart, population=population)
        rows.append({
            "subject": source,
            "population": population,
            "size": sizing.label,
            "alternative": sizing.alternative,
            "chest_mm": sizing.chest_mm,
            "reason": sizing.reason,
            "flags": sizing.flags,
            "measurements": {
                name: {
                    "value_mm": measurements[name].selected_value_mm,
                    "bucket": quality_bucket(measurements[name]),
                }
                for name in spec.names
            },
        })

    if not rows:
        print("no unclothed datasets present — see docs/datasets.md", file=sys.stderr)
        return 1

    assigned = [r for r in rows if r["size"]]
    refused = [r for r in rows if not r["size"]]
    boundary = [r for r in assigned if r["alternative"]]

    print(f"\n{chart.name}   ·   {len(rows)} unclothed subjects "
          f"(Texel CC BY-NC, NOMO research-only)")
    print(f"source: {chart.source}\n")

    print(f"{'coverage':22s} {len(assigned):3d} / {len(rows)}  "
          f"({100 * len(assigned) / len(rows):.0f} %)")
    print(f"{'refused':22s} {len(refused):3d}")
    print(f"{'on a band boundary':22s} {len(boundary):3d}  "
          f"({100 * len(boundary) / max(len(assigned), 1):.0f} % of the assigned) "
          f"— the label could flip under this pipeline's own error")

    print("\nsize distribution")
    for band in chart.bands:
        n = sum(1 for r in assigned if r["size"] == band.label)
        bar = "#" * n
        print(f"  {band.label:8s} {band.chest_min_cm:5.0f}-{band.chest_max_cm:3.0f} cm  "
              f"{n:3d}  {bar}")

    if refused:
        print("\nrefusals")
        reasons: dict[str, int] = {}
        for r in refused:
            key = r["reason"].split(";")[0][:64]
            reasons[key] = reasons.get(key, 0) + 1
        for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"  {n:3d}  {reason}")

    # ---- what the label does not say -------------------------------------
    print("\nwhat a size label leaves open — spread of the other measurements "
          "among subjects sharing one label")
    print(f"  {'size':8s} {'n':>3s}  " + "  ".join(f"{n[:12]:>12s}" for n in SECONDARY))
    spreads: dict[str, dict] = {}
    for band in chart.bands:
        group = [r for r in assigned if r["size"] == band.label]
        if len(group) < 2:
            continue
        cells, record = [], {}
        for name in SECONDARY:
            # Only measurements the pipeline itself accepts. A spread taken
            # over manual_review values measures our own failures, not the
            # variation between people — the same mistake as letting an
            # untrusted sample into an extremum (decisions #22, #26).
            values = [r["measurements"][name]["value_mm"] for r in group
                      if r["measurements"][name]["value_mm"] is not None
                      and r["measurements"][name]["bucket"] in TRUSTED_BUCKETS]
            excluded = len(group) - len(values)
            if len(values) < 2:
                cells.append(f"{'—':>12s}")
                continue
            spread = max(values) - min(values)
            record[name] = {"n": len(values), "excluded": excluded,
                            "range_mm": round(spread, 1),
                            "sd_mm": round(statistics.stdev(values), 1)}
            mark = "*" if excluded else " "
            cells.append(f"{spread:9.0f}mm{mark}")
        spreads[band.label] = record
        print(f"  {band.label:8s} {len(group):3d}  " + "  ".join(cells))
    print("\n  Each cell is the full range within one size, over accepted "
          "measurements only;\n  * marks a cell where a subject was excluded for "
          "a bucket this report will\n  not average — before that filter the "
          "cells reported our own failures as\n  human variation (XL back length "
          "read 441 mm instead of 33 mm).\n\n  A polo cut to the label fits the "
          "middle of the range and compromises at\n  both ends. That is the gap "
          "made-to-measure closes.")

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chart": chart.key,
        "chart_name": chart.name,
        "chart_source": chart.source,
        "chart_checked": chart.checked,
        "n_subjects": len(rows),
        "n_assigned": len(assigned),
        "n_refused": len(refused),
        "n_on_boundary": len(boundary),
        "within_size_spread_mm": spreads,
        "subjects": rows,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
