"""Carry a CAPE clothing displacement onto this project's A-pose body.

CAPE gives a clothed surface and a body surface for the same subject, both
in ITS canonical **T** pose. This pipeline measures in an **A** pose, and
the difference is not cosmetic: measured as shipped, a T-posed body's
chest circumference is 3808 mm, because the horizontal loop goes round the
torso and both outstretched arms (decision #34). So neither surface can be
used where it lies.

What transfers cleanly is the displacement. `D = v_cano - body_T` is a
per-vertex offset in SMPL's fixed topology, and SMPL+D's whole premise is
that such an offset can be added to the shaped template and posed with the
body. That gives a clothed shell around *our* canonical body, which the
core can measure and the fitter can be asked to recover from.

**The approximation, stated once and recorded in every case's meta.**
Clothing deforms with pose — a raised arm creases a sleeve — and this
transfer ignores that: D is applied rigidly through the body's skinning
weights. CAPE's own canonicalisation already made that choice when it
unposed the frame, so this inherits it rather than adding to it. The
result is a synthetic shell, not an observation of anyone wearing anything
in an A pose, and the claim wording says so.

**Why not `smplx.lbs.lbs(v_template=v_template + D)`.** That regresses the
joints from the displaced template, so `J_regressor @ D` moves the
skeleton — the clothing would relocate the shoulders. The joints must come
from the body, so the primitives are called directly.
"""
from __future__ import annotations

import numpy as np
import torch
import trimesh
from smplx.lbs import (
    batch_rigid_transform,
    batch_rodrigues,
    blend_shapes,
    vertices2joints,
)

from ..adapters.base import NormalizedBodySurface
from ..canonicalize import canonicalize
from .shells import ShellCase
from .smpl_body import NUM_BETAS, SmplBody, canonical_body_pose

#: Quantiles used for a case's gap band. Q10/Q90 rather than min/max: a
#: band pinned to the extremes is set by a handful of vertices.
BAND_QUANTILES = (10.0, 90.0)


def _skin(body: SmplBody, betas: np.ndarray, extra: np.ndarray | None):
    """SMPL forward pass with an optional per-vertex offset added to the
    shaped template, posed into this project's canonical A pose.

    Returns vertices in metres, (6890, 3). With `extra=None` this must
    reproduce `SmplBody.canonical_vertices_m` exactly — a test pins that,
    because it is the only proof the re-implementation matches smplx.
    """
    model = body.model
    betas_t = torch.as_tensor(np.asarray(betas, dtype=np.float32)).reshape(1, NUM_BETAS)
    full_pose = torch.cat([torch.zeros(1, 3), canonical_body_pose()], dim=1)

    with torch.no_grad():
        v_shaped = model.v_template.unsqueeze(0) + blend_shapes(betas_t, model.shapedirs)
        # joints from the BODY, never from the displaced surface
        joints = vertices2joints(model.J_regressor, v_shaped)

        rot = batch_rodrigues(full_pose.view(-1, 3)).view(1, -1, 3, 3)
        eye = torch.eye(3, dtype=rot.dtype)
        pose_feature = (rot[:, 1:] - eye).view(1, -1)
        pose_offsets = torch.matmul(pose_feature, model.posedirs).view(1, -1, 3)

        _, transforms = batch_rigid_transform(rot, joints, model.parents)
        weights = model.lbs_weights.unsqueeze(0)
        n_joints = transforms.shape[1]
        skinning = torch.matmul(weights, transforms.view(1, n_joints, 16)).view(1, -1, 4, 4)

        vertices = v_shaped + pose_offsets
        if extra is not None:
            vertices = vertices + torch.as_tensor(
                np.asarray(extra, dtype=np.float32)).unsqueeze(0)
        homogeneous = torch.cat(
            [vertices, torch.ones(1, vertices.shape[1], 1, dtype=vertices.dtype)], dim=2)
        posed = torch.matmul(skinning, homogeneous.unsqueeze(-1))[:, :, :3, 0]
    return posed[0].cpu().numpy().astype(np.float64)


def transfer_displacement(
    body: SmplBody,
    betas: np.ndarray,
    displacement_T_m: np.ndarray,
    *,
    name: str,
    meta: dict | None = None,
) -> ShellCase:
    """A `ShellCase` whose shell is this subject's clothing on our A pose.

    `betas` and `displacement_T_m` both come from CAPE; `body` must be the
    `SmplBody` for that subject's gender, since SMPL's shape space is
    gendered.
    """
    displacement = np.asarray(displacement_T_m, dtype=np.float64)
    if displacement.shape != (body.n_vertices, 3):
        raise ValueError(f"displacement is {displacement.shape}, expected "
                         f"({body.n_vertices}, 3)")

    body_m = _skin(body, betas, None)
    shell_m = _skin(body, betas, displacement)

    surface = NormalizedBodySurface(
        vertices_mm=body_m * 1000.0,
        faces=body.faces.copy(),
        source_type="synthetic_smpl",
        source_id=f"{name}/body",
        meta={"model": body.model_id, "pose": "canonical_a_pose"},
    )
    body_mesh = canonicalize(surface, weld=False)

    # The shell inherits the BODY's floor shift. canonicalize floors each
    # mesh independently, and the clothed surface reaches ~2 mm below the
    # body at the feet — floored on its own it would sink the whole shell
    # by that much relative to the body it is supposed to wrap.
    shift = float(body_mesh.vertices[:, 1].min() - body_m[:, 1].min() * 1000.0)
    shell_mesh = trimesh.Trimesh(
        vertices=shell_m * 1000.0 + np.array([0.0, shift, 0.0]),
        faces=body.faces.copy(), process=False)

    offset_mm = (shell_m - body_m) * 1000.0
    normals = np.asarray(body_mesh.vertex_normals, dtype=np.float64)
    true_gap_mm = np.einsum("ij,ij->i", offset_mm, normals)
    tangential = offset_mm - true_gap_mm[:, None] * normals

    parts = body.part_of_vertex
    lo_q, hi_q = BAND_QUANTILES
    gap_band_mm = {
        part: (round(float(np.percentile(true_gap_mm[parts == part], lo_q)), 1),
               round(float(np.percentile(true_gap_mm[parts == part], hi_q)), 1))
        for part in sorted(set(parts.tolist()))
    }

    case_meta = {
        "transfer": "smpl_d_lbs_to_canonical_a_pose",
        "approximation": "pose_dependent_clothing_deformation_ignored",
        # the scalar gap is the normal component; this says how much of the
        # displacement it leaves out
        "tangential_rms_mm": round(float(np.sqrt((tangential ** 2).sum(axis=1).mean())), 2),
        # the band comes from the truth itself, so a fit that lands inside
        # it has agreed with its own prior — a self-consistency check, not
        # a calibration. A real prior comes from a gap atlas over many
        # subjects, which needs a paired dataset this project does not have.
        "band_source": f"self_consistency_q{int(lo_q)}_q{int(hi_q)}_of_true_gap",
    }
    case_meta.update(meta or {})

    return ShellCase(
        name=name,
        mesh=shell_mesh,
        true_gap_mm=true_gap_mm,
        breaks="a real garment's non-uniform, partly tangential displacement, "
               "on the subject's own betas",
        gap_band_mm=gap_band_mm,
        meta=case_meta,
    )
