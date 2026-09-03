"""C2 — optimisation-based SMPL fitting to a clothed shell (CPU).

The objective is built around one idea: the body is *inside* the shell at
a *bounded* distance. "Inside" alone is not enough — a body shrunk to a
stick is perfectly inside — so the gap is pushed into a per-part band
[d_min, d_max], penalising both poking out and sinking in without cause.

    L = w_out · L_outside        body vertex outside the shell — beyond
                                 min(0, d_min), so a band that expects a
                                 few mm of registration noise outside is
                                 not contradicted by this term (#44)
      + w_band · L_gap_band      gap outside its part's [d_min, d_max]
      + w_beta · |betas|²        shape prior
      + w_pose · |pose − canon|² pose prior around the canonical A-pose

Optimisation is staged (rigid → coarse pose → shape → joint refinement)
because optimising pose and shape together from the start lets them
compensate for each other: a thin body with wide-open arms and a wide
body with arms tucked in can match the same shell.

What the result is NOT: a confidence. `fit_quality_score` is a bag of raw
residuals and violation rates. A body that is too small, or has slipped
into a hole, has a low residual too. The name `fit_confidence` is reserved
for a score calibrated against held-out error, which does not exist yet.

Units: the shell arrives in millimetres (canonical frame). Fitting runs in
metres because SMPL does; bands are converted once, at entry.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import torch
import trimesh

from .smpl_body import NUM_BETAS, BodyParams, SmplBody, canonical_body_pose

#: body_pose joint indices (pelvis excluded) the coarse-pose stage may move:
#: hips, knees, spine, shoulders, elbows. Fingers, feet and neck stay put —
#: a shell says almost nothing about them and they absorb error.
COARSE_JOINTS = (0, 1, 2, 3, 4, 5, 8, 12, 15, 16, 17, 18)

#: a body vertex whose nearest shell sample is farther than this has no
#: shell to be measured against (hole, missing limb) and gets weight 0
COVERAGE_RADIUS_M = 0.12

#: how far below the fitted body's lowest included vertex the shell still
#: counts as "covered by it" — the hip/crotch boundary is not sharp, and a
#: hard cut at the exact minimum would penalise the last centimetres of
#: torso for the trousers hanging just under them
Y_MASK_MARGIN_M = 0.05


@dataclass
class FitConfig:
    """Data terms are in mm², so a weight of 1 means "one mm² of violation
    per vertex costs 1". Priors are dimensionless; their weights are set
    so that at convergence they are small against a few mm² of residual.
    The first version had data terms in m² and a beta prior of 0.02, and
    the prior won: betas were shrunk toward zero with the torso 60 mm too
    thin while the residual looked fine."""
    n_shell_samples: int = 12000
    n_body_subsample: int = 2500
    w_outside: float = 4.0      # per mm² outside
    w_band: float = 1.0         # per mm² outside the band
    w_center: float = 0.02      # per mm² from the band centre: a flat band
                                # is a dead zone, and a body that reached the
                                # shell during the chamfer stage then stops at
                                # the band's inner edge, ~10 mm too big. The
                                # centre stands in for a gap atlas median.
                                # There is no atlas and no dated plan for
                                # one: it needs a paired clothed/body
                                # dataset, and SIZER is deferred without a
                                # reply (decision #41). Read this as the
                                # arrangement, not as a stopgap.
    w_beta: float = 0.05        # on mean(β²): ~0.1 at |β|~1.5, vs data terms of several mm²
    w_pose: float = 50.0        # on mean((θ−θ_canon)²) rad²
    #: Per-part data weight. The garment is an upper garment and the
    #: subject's lower half is whatever they happened to wear, so legs are
    #: excluded from the data term outright. This is not a tuning knob:
    #: SMPL betas are global, so every millimetre of leg the optimiser
    #: chases is spent out of the same budget the torso needs. Measured on
    #: the uniform-15 mm shell — leg weight 1.0 gives back_length +360 mm
    #: and waist -32 mm, 0.25 gives +362/-34 (no help at all), and 0.0
    #: gives +105/-11. Partial down-weighting does nothing; only exclusion
    #: works, which is what makes it a scope decision rather than a knob.
    part_weights: dict = field(default_factory=lambda: {
        "torso": 1.0, "arm": 1.0, "head": 1.0, "leg": 0.0,
    })
    iters_coarse: int = 120
    iters_pose: int = 60
    iters_shape: int = 120
    iters_refine: int = 60
    lr_betas: float = 0.05
    lr_pose: float = 0.01
    lr_transl: float = 0.003
    lr_orient: float = 0.01
    refine_scale: float = 0.2   # refinement runs every lr at this fraction
    seed: int = 0


@dataclass
class FitResult:
    params: BodyParams
    betas: np.ndarray
    stages: list[dict]
    fit_quality_score: dict
    flags: list[str]
    seconds: float
    config: FitConfig = field(repr=False)

    def to_dict(self) -> dict:
        return {
            "inference_method": "c2_staged_optimisation",
            "params": self.params.detach_numpy(),
            "stages": self.stages,
            "fit_quality_score": self.fit_quality_score,
            "flags": self.flags,
            "seconds": round(self.seconds, 2),
        }


# ---------------------------------------------------------------- shell ---
class ShellTarget:
    """Sampled shell in metres with outward-oriented normals."""

    def __init__(self, shell_mm: trimesh.Trimesh, n_samples: int, seed: int):
        # Face winding is not trusted as shipped — it is wrong on purpose in
        # one battery case and wrong by accident on real scans — but it IS
        # repairable as a mesh property: make adjacent faces agree, then
        # orient the whole shell outward. A per-point heuristic ("away from
        # the body axis") was tried first and silently flipped the inner
        # side of every arm, which is why the identity shell failed to fit
        # its own body.
        mesh = shell_mm.copy()
        before = mesh.face_normals.copy()
        trimesh.repair.fix_normals(mesh, multibody=True)
        changed = (before * mesh.face_normals).sum(axis=1) < 0
        self.fraction_reoriented = float(changed.mean())

        rng = np.random.default_rng(seed)
        points, face_idx = trimesh.sample.sample_surface(mesh, n_samples, seed=int(rng.integers(2**31)))
        normals = mesh.face_normals[face_idx]
        points = np.asarray(points, dtype=np.float64)

        self.points = torch.as_tensor(points / 1000.0, dtype=torch.float32)
        self.normals = torch.as_tensor(normals, dtype=torch.float32)
        self.floor_y = float(shell_mm.bounds[0][1]) / 1000.0
        self.centroid_xz = torch.as_tensor(points[:, [0, 2]].mean(axis=0) / 1000.0, dtype=torch.float32)

    def gap(self, body_xyz: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Signed gap per body vertex (metres, + = inside the shell) and a
        coverage mask. Nearest-sample index is not differentiated through;
        the distance along the fixed normal is.

        Point-to-plane is precise near the solution and misleading far from
        it: with the wrong correspondences every vertex is pushed along a
        normal that has nothing to do with where the shell actually is.
        Use `chamfer` to get close first."""
        with torch.no_grad():
            d = torch.cdist(body_xyz, self.points)
            nearest = d.argmin(dim=1)
            covered = d.gather(1, nearest[:, None])[:, 0] < COVERAGE_RADIUS_M
        q = self.points[nearest]
        n = self.normals[nearest]
        return ((q - body_xyz) * n).sum(dim=1), covered

    def chamfer(self, body_xyz: torch.Tensor, y_lo: torch.Tensor | None = None) -> torch.Tensor:
        """Bidirectional point-to-point distance, metres. Sign-free and
        normal-free, so it pulls a badly placed body toward the shell from
        anywhere — the coarse stages run on this.

        `y_lo` drops shell points below a height from the shell-to-body
        direction. It is required whenever the body passed in is partial:
        that direction asks "does every piece of shell have body near it?",
        and a leg-excluded body cannot answer for the shell's legs. Without
        the mask the shell's trouser points have no body to match and drag
        the torso down onto them — measured as a uniform shrink, worst on
        the identity shell where the answer should be exact (chest -16 mm
        before the mask existed, -37 mm after legs were excluded without
        it). The body-to-shell direction needs no mask: each body vertex
        finds its own nearest shell point regardless."""
        d = torch.cdist(body_xyz, self.points)
        forward = d.min(dim=1).values.mean()
        if y_lo is None:
            return forward + d.min(dim=0).values.mean()
        keep = self.points[:, 1] >= y_lo
        if not bool(keep.any()):
            return forward
        return forward + d[:, keep].min(dim=0).values.mean()


# ------------------------------------------------------------------ fit ---
def _band_tensors(part_of_vertex: np.ndarray, band_mm: dict[str, tuple[float, float]]):
    lo = np.array([band_mm[p][0] for p in part_of_vertex]) / 1000.0
    hi = np.array([band_mm[p][1] for p in part_of_vertex]) / 1000.0
    return torch.as_tensor(lo, dtype=torch.float32), torch.as_tensor(hi, dtype=torch.float32)


def _loss_terms(gap, covered, lo, hi, params, cfg, part_w=None) -> dict[str, torch.Tensor]:
    w = covered.float()
    if part_w is not None:
        w = w * part_w
    gap_mm, lo_mm, hi_mm = gap * 1000.0, lo * 1000.0, hi * 1000.0
    # "Outside" starts where the band says it starts, not at zero. A band
    # from a real registration has a negative lower edge on bare skin — the
    # clothed surface passes a few millimetres inside the body there, as
    # registration noise does — and a term that charged every gap below
    # zero at four times the band weight punished the true body more than
    # the fit that shrank away from it. Measured on three CAPE garments: the
    # objective at the truth was 22 against 8 at the fit, and the recovered
    # upper arm came back 17-31 mm short (decision #44). With the floor at
    # min(0, lo) a synthetic band (lo >= 0) is unchanged.
    floor_mm = torch.clamp(lo_mm, max=0.0)
    outside = (torch.relu(floor_mm - gap_mm) ** 2 * w).sum() / w.sum().clamp(min=1)
    band = ((torch.relu(lo_mm - gap_mm) ** 2 + torch.relu(gap_mm - hi_mm) ** 2) * w).sum() / w.sum().clamp(min=1)
    center = (((gap_mm - 0.5 * (lo_mm + hi_mm)) ** 2) * w).sum() / w.sum().clamp(min=1)
    beta = (params.betas ** 2).mean()
    pose = ((params.body_pose - canonical_body_pose()) ** 2).mean()
    return {
        "outside": cfg.w_outside * outside,
        "band": cfg.w_band * band,
        "center": cfg.w_center * center,
        "beta_prior": cfg.w_beta * beta,
        "pose_prior": cfg.w_pose * pose,
    }


def fit_shell(
    body: SmplBody,
    shell_mm: trimesh.Trimesh,
    gap_band_mm: dict[str, tuple[float, float]],
    cfg: FitConfig | None = None,
    *,
    init_betas: np.ndarray | None = None,
) -> FitResult:
    cfg = cfg or FitConfig()
    torch.manual_seed(cfg.seed)
    t0 = time.perf_counter()
    target = ShellTarget(shell_mm, cfg.n_shell_samples, cfg.seed)
    flags: list[str] = []
    if target.fraction_reoriented > 0.05:
        flags.append("shell_normals_reoriented")

    params = body.initial_params(init_betas)
    for t in (params.betas, params.body_pose, params.global_orient, params.transl):
        t.requires_grad_(True)

    # place the body on the shell's floor under its centroid before anything
    with torch.no_grad():
        v0 = body.forward(params)
        params.transl[0, 1] = target.floor_y - v0[:, 1].min()
        params.transl[0, [0, 2]] = target.centroid_xz - v0[:, [0, 2]].mean(dim=0)

    rng = np.random.default_rng(cfg.seed)
    sub = torch.as_tensor(np.sort(rng.choice(body.n_vertices, cfg.n_body_subsample, replace=False)))
    lo_all, hi_all = _band_tensors(body.part_of_vertex, gap_band_mm)
    lo, hi = lo_all[sub], hi_all[sub]
    part_w_all = torch.as_tensor(
        np.array([cfg.part_weights.get(p, 1.0) for p in body.part_of_vertex]),
        dtype=torch.float32,
    )
    part_w = part_w_all[sub]
    if float(part_w.sum()) == 0.0:
        raise ValueError("part_weights excludes every sampled vertex")
    full_body = bool((part_w_all > 0).all())

    pose_mask = torch.zeros(1, 69)
    for j in COARSE_JOINTS:
        pose_mask[0, j * 3:(j + 1) * 3] = 1.0

    stages: list[dict] = []

    def run_stage(name, groups, iters, *, mode, masked_pose=False, scale=1.0):
        opt = torch.optim.Adam([{"params": [tensor], "lr": lr * scale} for tensor, lr in groups])
        last = {}
        for _ in range(iters):
            opt.zero_grad()
            verts = body.forward(params)[sub]
            if mode == "chamfer":
                included = verts[part_w > 0]
                # the shell is only asked to be covered where the body we
                # are actually fitting reaches
                y_lo = None if full_body else included[:, 1].min().detach() - Y_MASK_MARGIN_M
                data = target.chamfer(included, y_lo) * 1000.0   # mm
                loss = data + cfg.w_beta * (params.betas ** 2).mean()                     + cfg.w_pose * ((params.body_pose - canonical_body_pose()) ** 2).mean()
                last = {"chamfer_mm": float(data.detach())}
            else:
                gap, covered = target.gap(verts)
                terms = _loss_terms(gap, covered, lo, hi, params, cfg, part_w)
                loss = sum(terms.values())
                last = {k: float(v.detach()) for k, v in terms.items()}
            loss.backward()
            if masked_pose and params.body_pose.grad is not None:
                params.body_pose.grad *= pose_mask
            opt.step()
        stages.append({"stage": name, "mode": mode, "iters": iters, "final_terms": last})

    B, P, O, T = params.betas, params.body_pose, params.global_orient, params.transl
    # 1. coarse shape + placement on a sign-free distance: escape the basin
    run_stage("coarse_shape", [(B, cfg.lr_betas), (T, cfg.lr_transl), (O, cfg.lr_orient)],
              cfg.iters_coarse, mode="chamfer")
    # 2. coarse pose, shape frozen, still sign-free
    run_stage("coarse_pose", [(P, cfg.lr_pose), (T, cfg.lr_transl)],
              cfg.iters_pose, mode="chamfer", masked_pose=True)
    # 3. shape against the gap band: this is where "inside, at a bounded
    #    distance" is actually enforced
    run_stage("shape_band", [(B, cfg.lr_betas), (T, cfg.lr_transl)],
              cfg.iters_shape, mode="band")
    # 4. everything, gently
    run_stage("refine", [(B, cfg.lr_betas), (P, cfg.lr_pose), (T, cfg.lr_transl), (O, cfg.lr_orient)],
              cfg.iters_refine, mode="band", masked_pose=True, scale=cfg.refine_scale)

    # ---- quality score on the FULL vertex set, raw residuals only --------
    with torch.no_grad():
        verts = body.forward(params)
        gap, covered = target.gap(verts)
        g = gap.numpy() * 1000.0
        included = part_w_all.numpy() > 0
        # coverage is "how much of what we are fitting has shell to fit
        # against", so it is a fraction of the INCLUDED vertices. Dividing
        # by the whole body instead silently charged the score for the
        # legs we chose not to model and tripped low_shell_coverage on a
        # perfect fit.
        c = covered.numpy() & included
        hi_mm = hi_all.numpy() * 1000.0
        score = {
            "scored_parts": sorted(p for p, w in cfg.part_weights.items() if w > 0),
            "coverage_fraction": float(c.sum() / max(included.sum(), 1)),
            "outside_fraction": float(((g < -2.0) & c).sum() / max(c.sum(), 1)),
            "mean_abs_outside_mm": float(np.abs(np.minimum(g[c], 0)).mean()) if c.any() else None,
            "collapse_fraction": float(((g > hi_mm + 20.0) & c).sum() / max(c.sum(), 1)),
            "median_gap_mm": float(np.median(g[c])) if c.any() else None,
            "final_terms": stages[-1]["final_terms"],
            "betas_norm": float(params.betas.norm()),
            "pose_deviation_rad": float((params.body_pose - canonical_body_pose()).abs().max()),
        }
    if score["collapse_fraction"] > 0.10:
        flags.append("possible_collapse")
    if score["coverage_fraction"] < 0.85:
        flags.append("low_shell_coverage")
    if score["pose_deviation_rad"] > 0.9:
        flags.append("pose_far_from_canonical")

    return FitResult(
        params=params,
        betas=params.betas.detach().numpy()[0].copy(),
        stages=stages,
        fit_quality_score=score,
        flags=flags,
        seconds=time.perf_counter() - t0,
        config=cfg,
    )


def multi_start(
    body: SmplBody,
    shell_mm: trimesh.Trimesh,
    gap_band_mm: dict[str, tuple[float, float]],
    cfg: FitConfig | None = None,
    *,
    starts: int = 3,
    spread: float = 0.7,
) -> list[FitResult]:
    """The same shell from perturbed initial betas. Disagreement between
    starts is a real signal about the shell (a residual is not)."""
    cfg = cfg or FitConfig()
    rng = np.random.default_rng(cfg.seed + 1)
    results = [fit_shell(body, shell_mm, gap_band_mm, cfg)]
    for k in range(1, starts):
        init = rng.normal(0.0, spread, size=NUM_BETAS)
        results.append(fit_shell(body, shell_mm, gap_band_mm, cfg, init_betas=init))
    return results
