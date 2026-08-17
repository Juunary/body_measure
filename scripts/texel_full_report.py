"""All six measurements vs Texel portal_mx GT (category: dataset_agreement).

Run:  .venv\\Scripts\\python scripts\\texel_full_report.py
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.adapters.texel import TexelAdapter  # noqa: E402
from body_measure.canonicalize import canonicalize  # noqa: E402
from body_measure.measure.measurements import run_estimated_measurements  # noqa: E402
from body_measure.spec import load_spec  # noqa: E402

ROOT = PROJECT_ROOT / "data" / "external" / "texel"


def main() -> int:
    adapter = TexelAdapter()
    persons = adapter.persons(ROOT)
    if not persons:
        print(f"no dataset at {ROOT}", file=sys.stderr)
        return 1
    spec = load_spec()

    deltas: dict[str, list[float]] = {name: [] for name in spec.names}
    print("# Texel Part 1 — all six measurements (dataset_agreement, portal_mx)\n")
    print("| person | " + " | ".join(n.replace("_circumference", "_circ") for n in spec.names) + " |")
    print("|" + "---|" * (len(spec.names) + 1))
    for person in persons:
        mesh = canonicalize(adapter.load(person))
        gt = adapter.checked_ground_truth(person)
        measurements, _ = run_estimated_measurements(mesh)
        cells = []
        for name in spec.names:
            ours = measurements[name].selected_value_mm
            ref = gt.get(name)
            if ours is None:
                cells.append("— (" + ",".join(measurements[name].quality) + ")")
            elif ref is None:
                cells.append(f"{ours:.0f} (no GT)")
            else:
                deltas[name].append(ours - ref)
                cells.append(f"{ours:.0f} vs {ref:.0f} ({ours - ref:+.0f})")
        print(f"| {person.name} | " + " | ".join(cells) + " |")

    print("\n## Deltas vs definition-matched GT (mean / max|d| / n)")
    for name in spec.names:
        values = deltas[name]
        if not values:
            print(f"- {name}: no comparisons")
            continue
        print(
            f"- {name}: {statistics.mean(values):+.1f} / "
            f"{max(abs(v) for v in values):.1f} / {len(values)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
