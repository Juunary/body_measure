"""Numerical-robustness report (category: numerical_robustness).

Bodies: SMPL neutral A-pose (synthetic) + Texel Man0/Woman0 (real scans).
Also runs the targeted waist-expansion sanity on each body.

Run:  .venv\\Scripts\\python scripts\\robustness_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.adapters.mesh_file import MeshFileAdapter  # noqa: E402
from body_measure.adapters.texel import TexelAdapter  # noqa: E402
from body_measure.canonicalize import canonicalize  # noqa: E402
from body_measure.landmarks.estimated import estimate_waist_level  # noqa: E402
from body_measure.validate.robustness import expand_waist, measure_all, run_battery  # noqa: E402

TEXEL = PROJECT_ROOT / "data" / "external" / "texel"
GENERATED = PROJECT_ROOT / "data" / "generated"


def bodies():
    smpl_obj = GENERATED / "smpl_neutral0_apose.obj"
    if smpl_obj.exists():
        yield "smpl_neutral0_apose", canonicalize(MeshFileAdapter().load(smpl_obj, unit="m"))
    adapter = TexelAdapter()
    for person in adapter.persons(TEXEL):
        if person.name in ("Man0", "Woman0"):
            yield f"texel_{person.name}", canonicalize(adapter.load(person))


def main() -> int:
    for name, mesh in bodies():
        # subdivide on 100k-face scans explodes the edge graph; SMPL only
        skip = set() if name.startswith("smpl") else {"subdivide"}
        results = run_battery(mesh, skip=skip)
        baseline = results.pop("baseline")
        print(f"\n# {name}  (baseline: " + ", ".join(
            f"{k.split('_')[0]}={v:.0f}" for k, v in baseline.items() if v is not None) + ")")
        print("| perturbation | " + " | ".join(k.replace("_circumference", "") for k in baseline) + " |")
        print("|" + "---|" * (len(baseline) + 1))
        for pname, deltas in results.items():
            cells = [f"{d:+.1f}" if d is not None else "—" for d in deltas.values()]
            print(f"| {pname} | " + " | ".join(cells) + " |")

        waist = estimate_waist_level(mesh)
        if waist is not None:
            # NOTE: the estimated waist itself may legitimately move off an
            # expanded band (minimum-girth definition), so the sanity check
            # measures at the FIXED original height instead.
            waist_y = float(waist.position_mm[1])
            expanded = expand_waist(mesh, waist_y, delta_mm=10.0)
            from body_measure.measure.measurements import circumference_at_height

            before = circumference_at_height(mesh, waist_y).selected_value_mm
            after = circumference_at_height(expanded, waist_y).selected_value_mm
            print(f"girth at fixed waist height after +10mm radial expansion: "
                  f"{after - before:+.1f} mm (expected ~ +{2 * np.pi * 10:.0f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
