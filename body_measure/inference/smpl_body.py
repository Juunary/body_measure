"""SMPL as a body generator, wrapped so the rest of the package never
touches smplx directly.

Two frames matter and they are kept apart on purpose:

  fit frame      metres, Y-up, whatever pose the optimiser needs to match
                 a scan — `forward()`
  measure frame  millimetres, Y-up, floor at y=0, the canonical A-pose —
                 `canonical_mesh()`

Only the measure frame ever reaches the measurement core. Measuring the
fitted pose would make every number depend on how well the arms happened
to be matched; measuring the canonical pose makes two bodies comparable
whatever scan they came from (docs/decisions.md, C2 design).

The canonical pose is the generator's A-pose (shoulders lowered by
ABDUCTION_DEG about the forward axis) so that validated A-pose bodies and
recovered bodies are measured identically.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import trimesh

from ..adapters.base import NormalizedBodySurface
from ..canonicalize import canonicalize

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = PROJECT_ROOT / "models" / "smpl"

NUM_BETAS = 10
#: matches scripts/generate_smpl_bodies.py — the A-pose the unclothed
#: validation used, so recovered and generated bodies measure alike
ABDUCTION_DEG = 50.0
L_SHOULDER, R_SHOULDER = 15, 16  # body_pose joint indices (pelvis excluded)

#: SMPL joint index -> coarse body part, from argmax skinning weight.
#: Used by the synthetic shells to put different offsets on different
#: parts, and by the fit to weight parts differently.
PART_OF_JOINT = {
    0: "torso", 3: "torso", 6: "torso", 9: "torso", 12: "torso", 13: "torso", 14: "torso",
    15: "head",
    16: "arm", 17: "arm", 18: "arm", 19: "arm", 20: "arm", 21: "arm", 22: "arm", 23: "arm",
    1: "leg", 2: "leg", 4: "leg", 5: "leg", 7: "leg", 8: "leg", 10: "leg", 11: "leg",
}


def canonical_body_pose() -> torch.Tensor:
    pose = torch.zeros(1, 69)
    angle = float(np.deg2rad(ABDUCTION_DEG))
    pose[0, L_SHOULDER * 3 + 2] = -angle
    pose[0, R_SHOULDER * 3 + 2] = angle
    return pose


@dataclass
class BodyParams:
    betas: torch.Tensor         # (1, 10)
    body_pose: torch.Tensor     # (1, 69) axis-angle
    global_orient: torch.Tensor # (1, 3)
    transl: torch.Tensor        # (1, 3) metres

    def detach_numpy(self) -> dict:
        return {
            "betas": self.betas.detach().cpu().numpy()[0].tolist(),
            "body_pose": self.body_pose.detach().cpu().numpy()[0].tolist(),
            "global_orient": self.global_orient.detach().cpu().numpy()[0].tolist(),
            "transl_m": self.transl.detach().cpu().numpy()[0].tolist(),
        }


class SmplBody:
    """Neutral SMPL, first 10 betas, CPU."""

    def __init__(self, model_dir: Path = MODEL_DIR, gender: str = "neutral"):
        import smplx

        if not (model_dir / f"SMPL_{gender.upper()}.pkl").exists():
            raise FileNotFoundError(
                f"SMPL {gender} model not found under {model_dir} — see docs/datasets.md"
            )
        self.model = smplx.create(
            str(model_dir.parent), model_type="smpl", gender=gender, num_betas=NUM_BETAS
        )
        self.model.requires_grad_(False)
        self.faces = self.model.faces.astype(np.int64)
        self.n_vertices = int(self.model.v_template.shape[0])
        self.gender = gender
        self.model_id = f"SMPL v1.1.0 {gender} (first {NUM_BETAS} betas)"
        # per-vertex coarse part from the skinning weights
        joint_of_vertex = self.model.lbs_weights.argmax(dim=1).cpu().numpy()
        self.part_of_vertex = np.array([PART_OF_JOINT[int(j)] for j in joint_of_vertex])

    # ------------------------------------------------------------- frames ---
    def forward(self, params: BodyParams) -> torch.Tensor:
        """Vertices in the fit frame (metres), differentiable."""
        out = self.model(
            betas=params.betas,
            body_pose=params.body_pose,
            global_orient=params.global_orient,
            transl=params.transl,
        )
        return out.vertices[0]

    def canonical_vertices_m(self, betas: torch.Tensor) -> np.ndarray:
        with torch.no_grad():
            out = self.model(
                betas=betas.reshape(1, NUM_BETAS),
                body_pose=canonical_body_pose(),
                global_orient=torch.zeros(1, 3),
            )
        return out.vertices[0].cpu().numpy().astype(np.float64)

    def canonical_mesh(self, betas: torch.Tensor | np.ndarray, *, source_id: str) -> trimesh.Trimesh:
        """The one mesh the measurement core is allowed to see for this body:
        millimetres, Y-up, floor at 0, canonical pose, welded."""
        betas_t = torch.as_tensor(np.asarray(betas, dtype=np.float32))
        vertices_m = self.canonical_vertices_m(betas_t)
        surface = NormalizedBodySurface(
            vertices_mm=vertices_m * 1000.0,
            faces=self.faces.copy(),
            source_type="synthetic_smpl",
            source_id=source_id,
            meta={"model": self.model_id, "pose": "canonical_a_pose",
                  "abduction_deg": ABDUCTION_DEG},
        )
        return canonicalize(surface)

    def initial_params(self, betas: np.ndarray | None = None) -> BodyParams:
        b = torch.zeros(1, NUM_BETAS) if betas is None else torch.as_tensor(
            np.asarray(betas, dtype=np.float32)).reshape(1, NUM_BETAS)
        return BodyParams(
            betas=b.clone(),
            body_pose=canonical_body_pose(),
            global_orient=torch.zeros(1, 3),
            transl=torch.zeros(1, 3),
        )
