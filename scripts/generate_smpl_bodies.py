"""Generate SMPL bodies for the two validation tracks (the ONLY torch code).

Outputs to data/generated/: per body an OBJ in metres plus a sidecar JSON
recording seed/betas/pose/gender/model version (reproducibility contract,
docs/decisions.md #7 — Date/random state never implicit).

Tracks:
  T-pose  — for cross-implementation comparison with a reference library
  A-pose  — arms abducted so slice loops separate; robustness battery input

Run (venv with requirements-smpl.txt):
  .venv\\Scripts\\python scripts\\generate_smpl_bodies.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "models" / "smpl"
OUT_DIR = PROJECT_ROOT / "data" / "generated"

SEED = 20260817
N_RANDOM = 8
ABDUCTION_DEG = 50.0  # arm-down rotation from T-pose; ~40 deg off vertical

# SMPL body_pose joint indices (pelvis excluded): L_shoulder=15, R_shoulder=16
L_SHOULDER, R_SHOULDER = 15, 16


def main() -> int:
    import torch
    import smplx

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model = smplx.create(str(MODEL_DIR.parent), model_type="smpl", gender="neutral")
    faces = model.faces.astype(np.int64)

    rng = np.random.default_rng(SEED)
    beta_sets = [("neutral0", np.zeros(10))]
    for i in range(N_RANDOM):
        beta_sets.append((f"rand{i}", rng.normal(0.0, 1.2, size=10)))

    angle = np.deg2rad(ABDUCTION_DEG)
    for name, betas in beta_sets:
        for pose_name in ("t", "a"):
            body_pose = torch.zeros(1, 69)
            if pose_name == "a":
                # rotate shoulders about the forward (z) axis to lower the arms
                body_pose[0, L_SHOULDER * 3 + 2] = -angle
                body_pose[0, R_SHOULDER * 3 + 2] = angle
            output = model(
                betas=torch.tensor(betas, dtype=torch.float32).unsqueeze(0),
                body_pose=body_pose,
                global_orient=torch.zeros(1, 3),
            )
            vertices = output.vertices.detach().numpy()[0]  # metres
            stem = f"smpl_{name}_{pose_name}pose"
            obj = OUT_DIR / f"{stem}.obj"
            with open(obj, "w", encoding="ascii") as handle:
                for v in vertices:
                    handle.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
                for f in faces + 1:
                    handle.write(f"f {f[0]} {f[1]} {f[2]}\n")
            sidecar = {
                "model": "SMPL v1.1.0 neutral (300-PC release, first 10 betas used)",
                "model_file": "SMPL_NEUTRAL.pkl",
                "gender": "neutral",
                "seed": SEED,
                "beta_set": name,
                "betas": [float(b) for b in betas],
                "pose": pose_name,
                "abduction_deg": ABDUCTION_DEG if pose_name == "a" else 0.0,
                "units": "m",
                "up_axis": "Y",
            }
            (OUT_DIR / f"{stem}.json").write_text(
                json.dumps(sidecar, indent=2), encoding="utf-8"
            )
            print("wrote", obj.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
