"""C1 — what a clothed scan costs you, per measurement.

The finished report (on SIZER) answers Zhen's procurement question with a
number per measurement per garment class. This skeleton runs the same code
path on HSRD, which is CC BY 4.0 and therefore usable while the SIZER
licence review is still open.

HSRD ships no same-subject body reference, so **no offset can be
computed** and none is invented: the offset fields stay null with a
reason, and the claim block reports `status: unavailable`. What HSRD can
give today is the other half of C1, which is worth having on its own:

  1. a clothed-scan failure inventory — which of the seven measurements
     the pipeline can produce at all when the subject is dressed, and
     which flags fire;
  2. LOD consistency — the same clothed body at several mesh resolutions.

Run:  .venv\\Scripts\\python scripts\\clothing_offset_report.py
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.adapters.hsrd import HsrdAdapter  # noqa: E402
from body_measure.canonicalize import canonicalize  # noqa: E402
from body_measure.measure.measurements import run_estimated_measurements  # noqa: E402
from body_measure.spec import load_spec  # noqa: E402
from body_measure.validate.claims import Comparison, claim_category_for  # noqa: E402
from body_measure.validate.stats import quality_bucket, summarize  # noqa: E402

HSRD_ROOT = PROJECT_ROOT / "data" / "external" / "hsrd"
OUT = PROJECT_ROOT / "reports" / "clothing_offset_hsrd.json"

PATHWAY = "measured_clothed"

#: These ranges used to live here as PLAUSIBLE_MM, a report-level sanity
#: check with a comment saying "the core having no such bound is a finding
#: of this run, not a design". Decision #39 acted on that finding: the
#: bounds moved into measurement-spec.v1.yaml and the core now refuses out
#: of range. What is left here is the counter below — it should read zero,
#: and a non-zero value means something reached the report that the gate
#: was supposed to stop.


def implausible(name: str, value_mm: float | None, spec) -> bool:
    entry = spec.measurements.get(name)
    if value_mm is None or entry is None or entry.plausible_mm is None:
        return False
    low, high = entry.plausible_mm
    return not (low <= value_mm <= high)


def measure_observation(adapter: HsrdAdapter, observation: Path, spec) -> dict:
    surface = adapter.load(observation)
    mesh = canonicalize(surface)
    measurements, _ = run_estimated_measurements(mesh)
    return {
        "source_id": surface.source_id,
        "lod": surface.meta["lod"],
        "n_faces": int(len(mesh.faces)),
        "garment": surface.meta["garment"],
        "recorded_stature_mm": surface.meta["recorded_stature_mm"],
        "scan_extent_mm": round(surface.meta["scan_extent_mm"], 1),
        "stature_excess_mm": surface.meta["stature_excess_mm"],
        "measurements": {
            name: {
                "value_mm": value.selected_value_mm,
                "disposition": value.disposition,
                "bucket": quality_bucket(value),
                "flags": [f for f in value.quality if f != "ok"],
                # the core produced this number; the report judges whether a
                # human could have it
                "implausible": implausible(name, value.selected_value_mm, spec),
                "plausible_range_mm": (spec.measurements[name].plausible_mm
                                       if name in spec.measurements else None),
            }
            for name, value in measurements.items()
        },
    }


def offset_block(reference_available: bool) -> dict:
    """The claim this report is allowed to make — derived, not asserted."""
    if not reference_available:
        return {
            "status": "unavailable",
            "claim_category": None,
            "pathway": PATHWAY,
            "reference_kind": None,
            "reason": (
                "HSRD ships no same-subject body reference (no minimal scan, "
                "no body registration), so a clothing offset has nothing to "
                "subtract. Offsets come from SIZER; see docs/licenses/README.md."
            ),
            "would_be_claim_with_a_minimal_scan": claim_category_for(
                PATHWAY, "minimal_scan_surface"
            ),
        }
    comparison = Comparison(
        pathway=PATHWAY,
        reference_kind="minimal_scan_surface",
        reference_method="body_measure_pipeline",
    )
    return {"status": "available", **comparison.to_dict()}


def lod_consistency(observations: list[dict], spec_names: tuple[str, ...]) -> dict:
    """Same clothed body, different mesh resolutions — a real quantitative
    result HSRD can support on its own."""
    if len(observations) < 2:
        return {"status": "unavailable", "reason": "fewer than two LODs present"}
    finest = max(observations, key=lambda o: o["n_faces"])
    rows = {}
    for name in spec_names:
        base = finest["measurements"][name]["value_mm"]
        deltas = {}
        for obs in observations:
            if obs is finest:
                continue
            value = obs["measurements"][name]["value_mm"]
            deltas[obs["lod"]] = (
                None if (base is None or value is None) else round(value - base, 2)
            )
        present = [d for d in deltas.values() if d is not None]
        rows[name] = {
            "reference_lod": finest["lod"],
            "reference_value_mm": base,
            "delta_mm": deltas,
            "max_abs_delta_mm": max((abs(d) for d in present), default=None),
        }
    return {"status": "available", "per_measurement": rows}


def coverage(observations: list[dict], spec_names: tuple[str, ...]) -> dict:
    """How often a clothed scan yields a usable number at all. The offset is
    unknown here; the refusal rate is not, and it is a C1 result."""
    out = {}
    for name in spec_names:
        entries = [
            {"delta": None, "bucket": obs["measurements"][name]["bucket"]}
            for obs in observations
        ]
        stats = summarize(entries)
        out[name] = {
            "n_observations": stats["n_total"],
            "n_accepted": stats["n_accepted"],
            "n_manual_review": stats["n_manual_review"],
            "n_rejected": stats["n_rejected"],
            # values no human body could have that the core did NOT reject.
            # Before decision #39 this was the finding; now it is the
            # regression counter, and it should read zero.
            "n_implausible_but_not_rejected": sum(
                1 for obs in observations
                if obs["measurements"][name]["implausible"]
                and obs["measurements"][name]["disposition"] != "rejected"
            ),
            "buckets": stats["buckets"],
            "flags_seen": sorted({
                flag
                for obs in observations
                for flag in obs["measurements"][name]["flags"]
            }),
        }
    return out


def main() -> int:
    if not HSRD_ROOT.is_dir():
        print(f"HSRD not found at {HSRD_ROOT} — see docs/datasets.md", file=sys.stderr)
        return 1

    spec = load_spec()
    adapter = HsrdAdapter(HSRD_ROOT)
    observations = [measure_observation(adapter, obs, spec)
                    for obs in adapter.observations()]
    if not observations:
        print(f"no LOD directories with meshes under {HSRD_ROOT}", file=sys.stderr)
        return 1

    report = {
        "stage": "C1",
        "dataset": "hsrd",
        "licence": "CC BY 4.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "purpose": (
            "Skeleton of the clothing-offset report, exercised on the one "
            "dataset available before the SIZER licence review completes. "
            "Structure is final; the offset columns are filled by SIZER."
        ),
        "offset": offset_block(reference_available=bool(adapter.fit_references)),
        "coverage": coverage(observations, spec.names),
        "lod_consistency": lod_consistency(observations, spec.names),
        "observations": observations,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    garment = observations[0]["garment"]
    print(f"HSRD — {len(observations)} LOD(s), "
          f"{garment['upper']} / {garment['lower']} / {garment['footwear']}")
    print(f"scan is {observations[0]['stature_excess_mm']:+.0f} mm taller than the "
          "recorded stature (footwear and headwear)\n")

    print(f"{'measurement':28s} {'value(finest)':>14s}  {'bucket':14s} flags")
    finest = max(observations, key=lambda o: o["n_faces"])
    for name in spec.names:
        entry = finest["measurements"][name]
        value = f"{entry['value_mm']:.0f} mm" if entry["value_mm"] else "null"
        mark = " !" if entry["implausible"] else "  "
        flags = ",".join(entry["flags"])[:42] or "-"
        print(f"{name:28s} {value:>14s}{mark}{entry['bucket']:14s} {flags}")

    lod = report["lod_consistency"]
    if lod["status"] == "available":
        print(f"\nLOD consistency vs {finest['lod']} (clothed scan):")
        for name, row in lod["per_measurement"].items():
            if row["max_abs_delta_mm"] is not None:
                print(f"  {name:28s} max |Δ| {row['max_abs_delta_mm']:7.2f} mm")

    bad = {
        name: row["n_implausible_but_not_rejected"]
        for name, row in report["coverage"].items()
        if row["n_implausible_but_not_rejected"]
    }
    if bad:
        print("\nimplausible values the pipeline did NOT reject "
              "(no human-range bound exists in the core):")
        for name, count in bad.items():
            for obs in observations:
                entry = obs["measurements"][name]
                if entry["implausible"] and entry["disposition"] != "rejected":
                    low, high = entry["plausible_range_mm"]
                    print(f"  {obs['lod']:6s} {name:28s} {entry['value_mm']:8.1f} mm "
                          f"(plausible {low}-{high}, disposition "
                          f"{entry['disposition']})")

    print(f"\noffset: {report['offset']['status']} — {report['offset'].get('reason', '')}")
    print(f"wrote {OUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
