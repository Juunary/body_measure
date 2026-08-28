r"""Thin wrapper: draw a dataset's scan in 3-D.

The rendering and the prototype measurements both live in the package now
(body_measure/viewer.py and body_measure/garment_prototypes.py), reachable
straight from the CLI:

  python -m body_measure measure <mesh> --input-unit m --estimate --view

This script exists only to point that machinery at the project's datasets
by name rather than by file path, since a dataset adapter knows its own
unit and axis and a raw path does not.

  $env:PYTHONUTF8=1; .venv\Scripts\python scripts\polo_measurement_3d.py --dataset hsrd

Public-material note: HSRD-100 is CC BY 4.0 and may leave the project;
Texel and NOMO may not. The output filename records which.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.garment_prototypes import run_prototypes  # noqa: E402
from body_measure.measure.measurements import run_estimated_measurements  # noqa: E402
from body_measure.viewer import render  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "polo_map", PROJECT_ROOT / "scripts" / "polo_measurement_map.py")
polo = importlib.util.module_from_spec(_spec)
sys.modules["polo_map"] = polo          # @dataclass resolves through sys.modules
_spec.loader.exec_module(polo)

OUT_DIR = PROJECT_ROOT / "reports" / "polo_map"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="hsrd", choices=["hsrd", "texel"])
    ap.add_argument("--subject", default="Man0")
    args = ap.parse_args()

    mesh, label, shareable = polo.load(args.dataset, args.subject)
    measurements, landmarks = run_estimated_measurements(mesh)
    prototypes = run_prototypes(mesh, measurements, landmarks)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = args.dataset if args.dataset == "hsrd" else f"{args.dataset}_{args.subject}"
    suffix = "" if shareable else "_INTERNAL_ONLY"
    png = OUT_DIR / f"polo_3d_{tag}{suffix}.png"

    n = render(mesh, measurements, landmarks, png, prototypes=prototypes,
               title="Polo measurements on the scan", subtitle=label)
    print(f"{n} measured curves drawn")
    print(f"wrote {png.relative_to(PROJECT_ROOT)}")
    if not shareable:
        print("  NOT cleared to leave the project (docs/licenses/public-material.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
