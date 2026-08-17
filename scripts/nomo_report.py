"""NOMO-3D-400 comparison (category: dataset_agreement).

Definition-matched: neck (NeckBase_Circ), chest (CHEST_Circ). Waist has
no minimum-girth GT in TC2 — MaxWAIST/TrouserWAIST shown as context only.

Run:  .venv\\Scripts\\python scripts\\nomo_report.py [N]
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.adapters.nomo import NomoAdapter  # noqa: E402
from body_measure.canonicalize import canonicalize  # noqa: E402
from body_measure.measure.measurements import run_estimated_circumferences  # noqa: E402

ROOT = PROJECT_ROOT / "data" / "external" / "nomo" / "NOMO-3d-400-scans_and_tc2_measurements" / "extracted"


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    adapter = NomoAdapter(ROOT)
    subjects = adapter.subjects("male")[:limit]
    if not subjects:
        print(f"no NOMO subjects under {ROOT}", file=sys.stderr)
        return 1

    deltas: dict[str, list[float]] = {"neck_circumference": [], "chest_circumference": []}
    print("# NOMO-3D-400 (male, first %d) — category: dataset_agreement\n" % len(subjects))
    print("| subject | chest ours vs GT | neck ours vs GT | waist ours (MaxW / TrouserW ctx) | flags |")
    print("|---|---|---|---|---|")
    for subject in subjects:
        try:
            mesh = canonicalize(adapter.load(subject))
        except (ValueError, FileNotFoundError) as exc:
            print(f"| {subject} | — | — | — | {exc} |")
            continue
        gt = adapter.checked_ground_truth(subject)
        aux = adapter.aux(subject)
        measurements, _ = run_estimated_circumferences(mesh)

        def cell(name):
            ours = measurements[name].selected_value_mm
            ref = gt.get(name)
            if ours is None or ref is None:
                return "—"
            deltas[name].append(ours - ref)
            return f"{ours:.0f} vs {ref:.0f} ({ours - ref:+.0f})"

        chest = cell("chest_circumference")
        neck = cell("neck_circumference")
        waist = measurements["waist_circumference"].selected_value_mm
        waist_txt = (f"{waist:.0f}" if waist else "—") + \
            f" ({aux.get('max_waist_girth', 0):.0f} / {aux.get('trouser_waist_girth', 0):.0f})"
        flags = ",".join(
            f for name in ("chest_circumference", "neck_circumference")
            for f in measurements[name].quality if f != "ok"
        ) or "ok"
        print(f"| {subject} | {chest} | {neck} | {waist_txt} | {flags} |")

    print("\n## Deltas vs definition-matched GT (mean / max|d| / n)")
    for name, values in deltas.items():
        if values:
            print(f"- {name}: {statistics.mean(values):+.1f} / "
                  f"{max(abs(v) for v in values):.1f} / {len(values)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
