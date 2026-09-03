"""Does recovering the body get harder as the garment gets thicker?

`c2_synthetic_battery.py --cape` fits one shell per (subject, outfit).
This reads that output and asks the question the individual rows cannot:
across ten real garments on two subjects, does the fit degrade with how
much cloth is between the shell and the body, and does it degrade the same
way for every measurement?

It is a self-consistency study, not an accuracy one. Each case's gap band
is derived from its own displacement, and the truth is the subject's own
betas, so a good result means the fitter recovers a body it was given
enough information to recover. Nothing here is evidence about a real
clothed scan (decisions #40, #41).

Run (PowerShell):
  $env:PYTHONUTF8=1; .venv\\Scripts\\python scripts\\cape_garment_report.py

Aggregate statistics from CAPE may be quoted internally with the dataset
named; no mesh, rendering or per-frame row leaves the project
(docs/licenses/public-material.md).
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BATTERY = PROJECT_ROOT / "reports" / "c2_synthetic_battery.json"
OUT = PROJECT_ROOT / "reports" / "cape_garment_report.json"

#: Sleeve length is a property of the garment, not of its name — measured
#: on the displacement itself (decision #34), not taken from the token.
SHORT_SLEEVED = ("poloshort", "shortlong", "shortshort")


def torso_gap(case: dict) -> tuple[float, float]:
    lo, hi = case["gap_band_mm"]["torso"]
    return float(lo), float(hi)


def main() -> int:
    if not BATTERY.is_file():
        print(f"no battery report at {BATTERY} — run "
              "scripts/c2_synthetic_battery.py --cape first", file=sys.stderr)
        return 1
    report = json.loads(BATTERY.read_text(encoding="utf-8"))
    cases = report.get("cape_cases") or []
    if not cases:
        print("the battery report has no cape_cases — it was run without "
              "--cape", file=sys.stderr)
        return 1

    rows = []
    for case in cases:
        source = case["meta"].get("shell_source", case["meta"])
        outfit = source.get("outfit", "?")
        lo, hi = torso_gap(case)
        score = case["fit"]["fit_quality_score"]
        rows.append({
            "case": case["case"],
            "subject": source.get("subject", "?"),
            "outfit": outfit,
            "sleeve": "short" if outfit in SHORT_SLEEVED else "long",
            "torso_band_mm": [lo, hi],
            "torso_hi_mm": hi,
            "arm_band_mm": list(case["gap_band_mm"].get("arm", (0.0, 0.0))),
            "tangential_rms_mm": case["meta"].get("tangential_rms_mm"),
            "beta_l2_error": case["beta_l2_error"],
            "coverage_fraction": round(score["coverage_fraction"], 3),
            "outside_fraction": round(score["outside_fraction"], 4),
            "collapse_fraction": round(score["collapse_fraction"], 4),
            "median_gap_mm": round(score["median_gap_mm"], 2),
            "deltas_mm": {k: v["delta_mm"] for k, v in case["measurements"].items()},
            "flags": case["fit"]["flags"],
        })
    rows.sort(key=lambda r: (r["subject"], -r["torso_hi_mm"]))

    print(f"{len(rows)} garments, {len({r['subject'] for r in rows})} subjects "
          f"— CAPE, research licence, aggregates only\n")
    print(f"{'case':30s} {'slv':4s} {'torso band':>13s} {'tang':>6s} "
          f"{'|B-B*|':>7s} {'cov':>5s} {'col%':>5s}  chest  waist   neck  arm")
    for row in rows:
        d = row["deltas_mm"]
        fmt = lambda n: "  null" if d.get(n) is None else f"{d[n]:+6.0f}"
        lo, hi = row["torso_band_mm"]
        print(f"{row['case']:30s} {row['sleeve']:4s} "
              f"{lo:6.1f}..{hi:5.1f} {row['tangential_rms_mm']:6.1f} "
              f"{row['beta_l2_error']:7.2f} {row['coverage_fraction']:5.2f} "
              f"{100 * row['collapse_fraction']:5.1f} "
              f"{fmt('chest_circumference')} {fmt('waist_circumference')} "
              f"{fmt('neck_circumference')} {fmt('upper_arm_girth')}")

    # --- does thicker cloth cost accuracy? ------------------------------
    thin = [r for r in rows if r["torso_hi_mm"] < statistics.median(
        [x["torso_hi_mm"] for x in rows])]
    thick = [r for r in rows if r not in thin]
    print(f"\nsplit at the median torso band "
          f"({statistics.median([r['torso_hi_mm'] for r in rows]):.1f} mm):")
    for label, group in (("thinner", thin), ("thicker", thick)):
        if not group:
            continue
        print(f"  {label:8s} n={len(group)}  "
              f"beta error {statistics.mean(r['beta_l2_error'] for r in group):5.2f}  "
              f"chest |delta| "
              f"{statistics.mean(abs(r['deltas_mm']['chest_circumference']) for r in group if r['deltas_mm'].get('chest_circumference') is not None):6.1f} mm")

    # --- and does a sleeve reach the arm? -------------------------------
    print("\nby sleeve length (measured from the displacement, not the name):")
    for sleeve in ("short", "long"):
        group = [r for r in rows if r["sleeve"] == sleeve]
        if not group:
            continue
        arm_hi = statistics.mean(r["arm_band_mm"][1] for r in group)
        arm_delta = [abs(r["deltas_mm"]["upper_arm_girth"]) for r in group
                     if r["deltas_mm"].get("upper_arm_girth") is not None]
        print(f"  {sleeve:5s} n={len(group)}  arm band top {arm_hi:5.1f} mm  "
              f"upper-arm |delta| "
              f"{statistics.mean(arm_delta) if arm_delta else float('nan'):6.1f} mm")

    collapsed = [r for r in rows if r["collapse_fraction"] > 0.05]
    print(f"\ncollapses (>5 %): {len(collapsed)}"
          + ("" if not collapsed else " — " + ", ".join(r["case"] for r in collapsed)))
    flagged = [r for r in rows if r["flags"]]
    if flagged:
        print("flagged fits:")
        for row in flagged:
            print(f"  {row['case']:30s} {','.join(row['flags'])}")

    OUT.write_text(json.dumps({
        "source": str(BATTERY.relative_to(PROJECT_ROOT)),
        "generated_from_battery_utc": report.get("generated_utc"),
        "claim": report.get("claim"),
        "note": ("Self-consistency: each case's gap band comes from its own "
                 "displacement and the truth is the subject's own betas. Not "
                 "evidence about a real clothed scan (decisions #40, #41)."),
        "garments": rows,
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
