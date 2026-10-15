"""A point-cloud encoder: sampled surface points in, a body description out.

Why it exists. A clothed query today needs C2 (inference/fit.py), about
30 s a start and three starts, and an optimiser that can settle in a local
minimum. The encoder is trained on synthetic bodies and procedural shells
to map the scan's points straight to (a) SMPL betas, (b) the standardised
measurement vector of the store's feature space and (c) a unit-length
embedding whose distances follow measurement distances. Query-side it runs
as ONNX on CPU (retrieval/onnx_query.py), with no torch.

What it is not. Its measurement head is a prediction, never a measurement:
the recovered betas go through SmplBody.canonical_mesh and the geometry
pipeline when a number is reported (docs/plan.md section 6), and its
pathway is an inferred one.

Architecture constraint (decision #19). No in-graph neighbour search: the
probe showed a runtime kNN costs O(N^2) memory (6.4 GB at 8k points).
Points are sampled outside the graph, and the network is a shared
per-point MLP with symmetric pooling (PointNet family), which exports.
"""
from __future__ import annotations

import torch
from torch import nn

N_POINTS = 4096
EMBED_DIM = 64
NUM_BETAS = 10


class PointEncoder(nn.Module):
    def __init__(self, n_meas: int, *, width: int = 512, embed_dim: int = EMBED_DIM,
                 num_betas: int = NUM_BETAS):
        super().__init__()
        self.n_meas = n_meas
        self.point_mlp = nn.Sequential(
            nn.Conv1d(3, 64, 1), nn.BatchNorm1d(64), nn.ReLU(),
            nn.Conv1d(64, 128, 1), nn.BatchNorm1d(128), nn.ReLU(),
            nn.Conv1d(128, 256, 1), nn.BatchNorm1d(256), nn.ReLU(),
            nn.Conv1d(256, width, 1), nn.BatchNorm1d(width), nn.ReLU(),
        )
        self.trunk = nn.Sequential(
            nn.Linear(2 * width, 512), nn.BatchNorm1d(512), nn.ReLU(), nn.Dropout(0.1),
            nn.Linear(512, 256), nn.BatchNorm1d(256), nn.ReLU(),
        )
        self.head_betas = nn.Linear(256, num_betas)
        self.head_meas = nn.Linear(256, n_meas)
        self.head_embed = nn.Linear(256, embed_dim)

    def forward(self, points: torch.Tensor):
        """points: (B, N, 3), metres, canonical frame (Y up, floor 0,
        centred in x and z). Returns (embedding (B, E) unit length,
        betas (B, 10), standardised measurements (B, M))."""
        x = self.point_mlp(points.transpose(1, 2))           # (B, C, N)
        pooled = torch.cat([x.amax(dim=2), x.mean(dim=2)], dim=1)
        h = self.trunk(pooled)
        emb = nn.functional.normalize(self.head_embed(h), dim=1)
        return emb, self.head_betas(h), self.head_meas(h)


def losses(emb, betas_hat, meas_hat, betas, meas_z, meas_mask, *,
           tau: float = 0.5, temperature: float = 0.1,
           w_betas: float = 1.0, w_meas: float = 1.0, w_contrast: float = 0.2) -> dict:
    """Beta regression + masked measurement regression + a supervised
    contrastive term whose positives are the pairs within `tau` of each
    other in the store's (masked, standardised) measurement space, so the
    embedding's neighbourhoods are measurement neighbourhoods."""
    l_betas = nn.functional.mse_loss(betas_hat, betas)
    m = meas_mask.float()
    l_meas = (((meas_hat - meas_z) ** 2) * m).sum() / m.sum().clamp_min(1.0)

    shared = m @ m.T                                          # keys both have
    diff2 = ((meas_z * m)[:, None, :] - (meas_z * m)[None, :, :]) ** 2
    both = m[:, None, :] * m[None, :, :]
    dist = torch.sqrt((diff2 * both).sum(-1) / shared.clamp_min(1.0))
    eye = torch.eye(len(emb), device=emb.device, dtype=torch.bool)
    positive = (dist < tau) & ~eye
    logits = emb @ emb.T / temperature
    logits = logits.masked_fill(eye, -1e9)
    log_prob = logits - torch.logsumexp(logits, dim=1, keepdim=True)
    has_pos = positive.any(dim=1)
    if has_pos.any():
        l_con = -(log_prob * positive).sum(1)[has_pos] / positive.sum(1)[has_pos]
        l_con = l_con.mean()
    else:
        l_con = emb.sum() * 0.0
    total = w_betas * l_betas + w_meas * l_meas + w_contrast * l_con
    return {"total": total, "betas": l_betas.detach(), "meas": l_meas.detach(),
            "contrast": l_con.detach()}
