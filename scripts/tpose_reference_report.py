"""T-pose cross-implementation comparison (category: synthetic_agreement).

Runs SMPL-Anthropometry (DavidBoja, MIT) and our estimated pathway on the
SAME generated T-pose vertices. This validates implementation agreement,
NOT real-world accuracy (docs/decisions.md #1).

To compare the same definition, our girth is measured at the REFERENCE's
landmark height (nipple / belly button / Adam's apple vertex heights) —
so this isolates the measurement primitive (slice + hull) from landmark
placement. Our own landmark estimation is validated separately against
Texel (dataset_agreement) — and is NOT applicable to T-pose anyway (the
armpit/chest heuristics assume lowered arms; on T-pose they measured the
wingspan, +2000 mm, which is out-of-contract input, not a bug).

Run:  .venv\\Scripts\\python scripts\\tpose_reference_report.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = PROJECT_ROOT / "external" / "SMPL-Anthropometry"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(REFERENCE_ROOT))

import os  # noqa: E402

os.chdir(REFERENCE_ROOT)  # its model paths are cwd-relative

import torch  # noqa: E402
import trimesh  # noqa: E402
from landmark_definitions import SMPL_LANDMARK_INDICES  # noqa: E402
from measure import MeasureBody  # noqa: E402

from body_measure.adapters.mesh_file import MeshFileAdapter  # noqa: E402
from body_measure.canonicalize import canonicalize  # noqa: E402
from body_measure.measure.measurements import circumference_at_height  # noqa: E402

PAIRS = {  # spec name -> (reference name, landmark vertices giving the height)
    "chest_circumference": ("chest circumference", ["LEFT_NIPPLE", "RIGHT_NIPPLE"]),
    "waist_circumference": ("waist circumference", ["BELLY_BUTTON", "BACK_BELLY_BUTTON"]),
    "neck_circumference": ("neck circumference", ["NECK_ADAM_APPLE"]),
}


def main() -> int:
    generated = PROJECT_ROOT / "data" / "generated"
    bodies = sorted(generated.glob("smpl_*_tpose.obj"))
    if not bodies:
        print("no generated T-pose bodies", file=sys.stderr)
        return 1

    measurer = MeasureBody("smpl")
    deltas: dict[str, list[float]] = {name: [] for name in PAIRS}
    rows = []
    for obj in bodies:
        raw = trimesh.load(obj, force="mesh", process=False)
        vertices = np.asarray(raw.vertices, dtype=np.float64)
        measurer.from_verts(verts=torch.tensor(vertices.astype(np.float32)))
        measurer.measure([ref for ref, _ in PAIRS.values()])
        reference = {name: measurer.measurements[ref] * 10.0  # cm -> mm
                     for name, (ref, _) in PAIRS.items()}

        mesh = canonicalize(MeshFileAdapter().load(obj, unit="m"))
        floor_shift_mm = -float(vertices[:, 1].min()) * 1000.0
        cells = [obj.stem.replace("smpl_", "").replace("_tpose", "")]
        for name, (_, landmark_names) in PAIRS.items():
            height = float(np.mean(
                [vertices[SMPL_LANDMARK_INDICES[lm], 1] for lm in landmark_names]
            )) * 1000.0 + floor_shift_mm
            ours = circumference_at_height(mesh, height).selected_value_mm
            if ours is None:
                cells.append("—")
                continue
            delta = ours - reference[name]
            deltas[name].append(delta)
            cells.append(f"{ours:.0f} vs {reference[name]:.0f} ({delta:+.0f})")
        rows.append("| " + " | ".join(cells) + " |")

    print("# T-pose cross-implementation comparison — category: synthetic_agreement\n")
    print("reference: SMPL-Anthropometry (MIT, DavidBoja) on identical vertices\n")
    print("| body | " + " | ".join(PAIRS) + " |")
    print("|" + "---|" * (len(PAIRS) + 1))
    for row in rows:
        print(row)
    print("\n## Deltas (ours - reference) at identical landmark heights: mean / max|d| / n")
    for name, values in deltas.items():
        if values:
            print(f"- {name}: {statistics.mean(values):+.1f} / "
                  f"{max(abs(v) for v in values):.1f} / {len(values)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
