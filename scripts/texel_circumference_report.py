"""Slice 2 report: estimated waist/chest/neck vs Texel portal_mx GT.

Category: dataset_agreement (agreement with the dataset's automatic
measurements — NOT a measurement-accuracy or ISO-conformity claim).

For chest and neck the horizontal-v1 slice may match a different girth
variant than the spec's nominal target; every candidate is reported so
the definition mapping is decided by evidence (docs/decisions.md #8).

Run:  .venv\\Scripts\\python scripts\\texel_circumference_report.py
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.adapters.texel import TexelAdapter  # noqa: E402
from body_measure.canonicalize import canonicalize  # noqa: E402
from body_measure.measure.measurements import run_estimated_circumferences  # noqa: E402

ROOT = PROJECT_ROOT / "data" / "external" / "texel"


def main() -> int:
    adapter = TexelAdapter()
    persons = adapter.persons(ROOT)
    if not persons:
        print(f"no dataset at {ROOT}", file=sys.stderr)
        return 1

    per_target: dict[str, list[float]] = {}
    lines = []
    for person in persons:
        mesh = canonicalize(adapter.load(person))
        gt = adapter.checked_dataset_reference(person)
        aux = adapter.aux_reference(person)
        measurements, landmarks = run_estimated_circumferences(mesh)

        candidates = {
            "waist_circumference": {"gt:m102": gt.get("waist_circumference"),
                                    "aux:m16": aux.get("waist_girth_iso_5_3_10")},
            "chest_circumference": {"gt:m5": gt.get("chest_circumference"),
                                    "aux:m44": aux.get("bust_girth_contoured"),
                                    "aux:m45": aux.get("chest_girth_at_axilla"),
                                    "aux:m46": aux.get("upper_chest_girth")},
            "neck_circumference": {"gt:m11": gt.get("neck_circumference"),
                                   "aux:m87": aux.get("neck_girth_middle")},
        }
        for name, refs in candidates.items():
            value = measurements.get(name)
            ours = value.selected_value_mm if value else None
            for ref_name, ref in refs.items():
                if ours is not None and ref is not None:
                    per_target.setdefault(f"{name} vs {ref_name}", []).append(ours - ref)
            refs_txt = " ".join(
                f"{k}={ref:.0f}" if ref is not None else f"{k}=—" for k, ref in refs.items()
            )
            quality = ",".join(value.quality) if value else "missing"
            ours_txt = f"{ours:.1f}" if ours is not None else "—"
            lines.append(f"| {person.name} | {name} | {ours_txt} | {refs_txt} | {quality} |")

    print("# Texel Part 1 circumferences — category: dataset_agreement (portal_mx)\n")
    print("| person | measurement | ours hull (mm) | dataset girths (mm) | quality |")
    print("|---|---|---|---|---|")
    for line in lines:
        print(line)

    print("\n## Deltas by candidate mapping (mean / max|d| / n)")
    for target, deltas in sorted(per_target.items()):
        mean = statistics.mean(deltas)
        mabs = max(abs(d) for d in deltas)
        print(f"- {target}: {mean:+.1f} / {mabs:.1f} / {len(deltas)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
