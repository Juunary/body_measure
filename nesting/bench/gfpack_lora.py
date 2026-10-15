"""LoRA fine-tuning of the GFPack++ score model on shirt markers. Runs inside WSL (CPU torch).

    /opt/gf/.venv/bin/python bench/gfpack_lora.py teacher.json out.pth [--steps 2000] [--rank 16] ...

The released checkpoint knows dental polygons only. This adapts it to the study's rules by learning from
teacher markers (bench/gfpack_teacher.py: the study's own nester on graded shirt variants, which already obey
the roll width, the 5 mm gap and rotations 0/90/180/270). The base weights stay frozen; low-rank deltas are
trained on every attention and feed-forward weight of the transformer and on the output layer with the
original denoising score-matching loss (`src.sde.lossFun`), then merged back so the result is a plain
state dict that `gfpack_infer.py --weights` loads. Augmentation: point reflection of a whole marker through
its centre (all pieces turn by 180 deg, still obeying the grain rule).
"""
import argparse
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch
from torch import nn
from torch.nn.utils import parametrize
from torch_geometric.data import Batch, Data
from shapely import affinity
from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gfpack_infer as gi  # noqa: E402  (also puts /opt/gf/gfpack on sys.path)
from src.evaluate import compute_global_features, compute_node_features  # noqa: E402
from src.score_model import PolygonPackingTransformer  # noqa: E402
from src.sde import init_sde  # noqa: E402


class LoRADelta(nn.Module):
    """W -> W + (alpha / rank) * B A, registered as a parametrization so the base module is untouched."""

    def __init__(self, shape, rank, alpha):
        super().__init__()
        out_f, in_f = shape
        self.A = nn.Parameter(torch.randn(rank, in_f) / math.sqrt(in_f))
        self.B = nn.Parameter(torch.zeros(out_f, rank))
        self.scale = alpha / rank

    def forward(self, W):
        return W + (self.B @ self.A) * self.scale


def add_lora(model, rank, alpha):
    for p in model.parameters():
        p.requires_grad_(False)
    targets = []
    for name, module in model.transformer_model.named_modules():
        if isinstance(module, nn.MultiheadAttention):
            targets += [(module, 'in_proj_weight'), (module, 'out_proj.weight')]
        elif isinstance(module, nn.Linear) and name.endswith(('linear1', 'linear2')):
            targets.append((module, 'weight'))
    targets.append((model.output_layer, 'weight'))
    for module, attr in targets:
        owner = module
        if '.' in attr:
            head, attr = attr.split('.')
            owner = getattr(module, head)
        shape = getattr(owner, attr).shape
        parametrize.register_parametrization(owner, attr, LoRADelta(shape, rank, alpha))
    return targets


def merge_lora(model, targets):
    for module, attr in targets:
        owner = module
        if '.' in attr:
            head, attr = attr.split('.')
            owner = getattr(module, head)
        parametrize.remove_parametrizations(owner, attr, leave_parametrized=True)


def sample_from_teacher(entry, cfg, flip):
    """Model-frame tensors (units; cos/sin x500) and centred scaled polygons for one teacher marker."""
    request = {'polys': entry['polys'], 'gap_mm': cfg['gap_mm']}
    grown, r = gi.grown_polygons(request)
    strip_mm = cfg['fabric_width_mm'] - 2 * (cfg['margin_mm'] - r)
    scale = gi.STRIP_UNITS / strip_mm
    pose, rotated = [], []
    for (ring, c), key in zip(grown, entry['keys']):
        rot, tx, ty = entry['placements'][key]
        a = math.radians(rot)
        T = np.array([c[0] * math.cos(a) - c[1] * math.sin(a) + tx, c[0] * math.sin(a) + c[1] * math.cos(a) + ty])
        T[1] -= cfg['margin_mm'] - r
        pose.append([T[0], T[1], rot])
        rotated.append(affinity.rotate(Polygon(ring - c), rot, origin=(0, 0)))
    pose = np.array(pose)
    bounds = np.array([affinity.translate(p, *pose[i, :2]).bounds for i, p in enumerate(rotated)])
    pose[:, 0] -= bounds[:, 0].min()
    if flip:
        cx = (bounds[:, 2].max() - bounds[:, 0].min()) / 2.0
        pose[:, 0] = 2 * cx - pose[:, 0]
        pose[:, 1] = strip_mm - pose[:, 1]
        pose[:, 2] += 180.0
    th = np.radians(pose[:, 2])
    actions = np.stack([pose[:, 0] * scale, pose[:, 1] * scale,
                        np.cos(th) * gi.COS_SIN_SCALE, np.sin(th) * gi.COS_SIN_SCALE], axis=1)
    centred = [((ring - c) * scale) for ring, c in grown]
    return actions.astype(np.float32), centred


def polygon_data(poly):
    ring = poly.tolist()
    n = len(ring)
    edges = [(i, (i + 1) % n) for i in range(n)] + [((i + 1) % n, i) for i in range(n)]
    area, perm = compute_global_features(ring)
    return Data(x=torch.tensor(compute_node_features(ring), dtype=torch.float),
                edge_index=torch.tensor(edges, dtype=torch.long).t().contiguous(),
                area=torch.tensor(area, dtype=torch.float), perm=torch.tensor(perm, dtype=torch.float))


def make_batch(items):
    """items: list of (actions (n,4), geometry features (n,64), weight) -> state batch and stacked features."""
    n = items[0][0].shape[0]
    state = Batch.from_data_list([Data(x=torch.from_numpy(a), z=torch.zeros(n), w=torch.tensor([w], dtype=torch.float32))
                                  for a, _, w in items])
    state.y = torch.arange(len(items) * n, dtype=torch.int64)
    return state, torch.cat([f for _, f, _ in items], dim=0)


def score_loss(model, state, feats, marginal):
    """src.sde.lossFun with the (frozen) geometry features passed in instead of recomputed every step."""
    batch = int(state.batch.max().item() + 1)
    t = torch.rand(batch) * (1 - 0.01) + 0.01
    noise = torch.randn_like(state.x)
    _, std = marginal(state.x, t)
    std = std[state.batch].view(-1, 1) + 1e-5
    out = model(state.x + noise * std, state.y, state.z, state.batch, t, None, feats)
    delta = out * std + noise
    per = (delta ** 2).reshape(batch, -1).sum(dim=1) / state.x.shape[1]
    weight = state.w.reshape(-1)
    return (per * weight).sum() / weight.sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('teacher')
    ap.add_argument('out')
    ap.add_argument('--steps', type=int, default=2000)
    ap.add_argument('--batch', type=int, default=48)
    ap.add_argument('--rank', type=int, default=16)
    ap.add_argument('--alpha', type=float, default=16.0)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--val', type=int, default=20)
    ap.add_argument('--seed', type=int, default=0)
    args = ap.parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    cfg = {'gap_mm': 5.0, 'margin_mm': 5.0, 'fabric_width_mm': 1007.0}
    entries = json.loads(Path(args.teacher).read_text())
    effs = np.array([e['efficiency_pct'] for e in entries])
    weights = 1.0 / (1.0 + np.exp(-(effs - effs.mean()) / max(np.ptp(effs), 1e-6) * 10.0))   # as GFPack++'s train.py
    _, marginal, _, _ = init_sde('ve')
    model = PolygonPackingTransformer(marginal_prob_std_func=marginal, device=torch.device('cpu'))
    model.load_state_dict(torch.load(gi.GFPACK / 'checkpoints' / 'score_model.pth', map_location='cpu', weights_only=True))
    model.eval()
    data = []
    t_feat = time.perf_counter()
    for e, w in zip(entries, weights):
        pair = []
        for flip in (False, True):
            actions, centred = sample_from_teacher(e, cfg, flip)
            if not flip:
                with torch.no_grad():     # the geometry encoder stays frozen: encode each marker's polygons once
                    feats = model.geo_feature(Batch.from_data_list([polygon_data(p) for p in centred]))
            pair.append((actions, feats, float(w)))
        data.append(pair)
    print(f'geometry features cached in {time.perf_counter() - t_feat:.0f} s', flush=True)
    random.shuffle(data)
    val, train = data[:args.val], data[args.val:]
    print(f'{len(train)} train / {len(val)} validation markers, x2 with point reflection', flush=True)
    targets = add_lora(model, args.rank, args.alpha)
    params = [p for p in model.parameters() if p.requires_grad]
    print(f'{sum(p.numel() for p in params)} trainable LoRA parameters (rank {args.rank})', flush=True)
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=1e-4)

    def val_loss():
        model.eval()
        state, feats = make_batch([p[i % 2] for i, p in enumerate(val)])
        g = torch.Generator().manual_seed(1)
        total = 0.0
        with torch.no_grad():
            for _ in range(4):
                torch.manual_seed(int(torch.randint(0, 10 ** 6, (1,), generator=g)))
                total += score_loss(model, state.clone(), feats, marginal).item()
        model.train()
        return total / 4

    print(f'step 0: validation loss {val_loss():.4f}', flush=True)
    model.train()
    t0 = time.perf_counter()
    for step in range(1, args.steps + 1):
        lr = args.lr * min(1.0, step / 50) * (0.5 * (1 + math.cos(math.pi * step / args.steps)))
        for g in opt.param_groups:
            g['lr'] = lr
        picks = [random.choice(random.choice(train)) for _ in range(args.batch)]
        state, feats = make_batch(picks)
        loss = score_loss(model, state, feats, marginal)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        if step % 50 == 0:
            print(f'step {step}: train {loss.item():.4f}  {time.perf_counter() - t0:.0f} s', flush=True)
        if step % 250 == 0 or step == args.steps:
            print(f'step {step}: validation loss {val_loss():.4f}', flush=True)
    merge_lora(model, targets)
    torch.save(model.state_dict(), args.out)
    Path(args.out).with_suffix('.json').write_text(json.dumps({
        'teacher': args.teacher, 'markers': len(entries), 'steps': args.steps, 'rank': args.rank, 'alpha': args.alpha,
        'lr': args.lr, 'batch': args.batch, 'seed': args.seed, 'validation_markers': len(val)}))
    print('saved', args.out)


if __name__ == '__main__':
    main()
