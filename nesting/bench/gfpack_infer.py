"""GFPack++ inference on the benchmark instance. Runs inside WSL (CPU torch + the compiled GFPack++ extensions).

    /opt/gf/.venv/bin/python bench/gfpack_infer.py request.json response.json

GFPack++ (Xue et al., ICCV 2025, github.com/TimHsue/GFPack-pp) learns a score model for 2D packing: a
reverse-diffusion sampler turns noise into poses (x, y, cos, sin) of the pieces. The released checkpoint was
trained on dental polygons only, knows no roll width, no grain rule and no gap, and its own post-processing
(`rm_spacing_all`) only slides pieces left and down while they do not overlap. So this script wraps the
model like this:

  1. each tool-frame polygon is grown by gap/2 (+0.1 mm) so touching grown polygons keep the gap, centred on
     its vertex mean (the training convention) and scaled so the usable roll width becomes the 1205 units of
     the dental strip;
  2. the sampler draws `samples` layouts (batched, CPU);
  3. every layout is snapped to the allowed rotations (--snap), made overlap-free by a deterministic push-out
     that keeps every polygon inside the strip, then compacted by GFPack++'s own `rm_spacing_all`;
  4. the shortest layouts are returned in the tool frame, rotation in degrees and translation in mm, as
     P = R(r) Q + t of the original tool polygon Q.

`--init random` replaces the sampler with uniform random poses and keeps steps 3-4: the control that shows
how much of the result is the model and how much is the legaliser.
"""
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import torch
from shapely import affinity
from shapely.geometry import Polygon

GFPACK = Path('/opt/gf/gfpack')
sys.path.insert(0, str(GFPACK))
from src.score_model import PolygonPackingTransformer  # noqa: E402
from src.sde import init_sde, pc_sampler_state  # noqa: E402
from src.evaluate import create_gnn_data  # noqa: E402  (imports the extensions, builds the graph batch)
from src import rmspacing  # noqa: E402

STRIP_UNITS = 1205.0          # height of the dental strip the checkpoint was trained on
COS_SIN_SCALE = 500.0         # the training data stores cos/sin times 500
SAFETY_MM = 0.1
PENETRATION_MM = 0.05         # deeper than this counts as an overlap; the evaluator tolerates 0.1 mm
BOUND_TOL_MM = 0.02           # the compaction nudges pieces by 0.001 units; the evaluator tolerates 0.1 mm


def grown_polygons(request):
    """Grown, simplified polygons in mm and their vertex-mean centres (tool frame, CCW)."""
    r = request['gap_mm'] / 2.0 + SAFETY_MM
    out = []
    for ring in request['polys']:
        grown = Polygon(ring).buffer(r, join_style='round', quad_segs=8).simplify(0.1, preserve_topology=True)
        ring_g = np.asarray(grown.exterior.coords)[:-1]
        if not Polygon(ring_g).exterior.is_ccw:
            ring_g = ring_g[::-1]
        out.append((ring_g, ring_g.mean(axis=0)))
    return out, r


def sample_poses(request, grown, scale, device):
    n = len(grown)
    steps = request['steps']
    torch.manual_seed(request['seed'])
    batch = request['samples']
    if request['init'] == 'random':
        strip = STRIP_UNITS
        x = torch.rand(batch, n) * (request['random_length_units'])
        y = torch.rand(batch, n) * strip
        ang = torch.rand(batch, n) * 2 * math.pi
        return torch.stack([x, y, torch.cos(ang) * COS_SIN_SCALE, torch.sin(ang) * COS_SIN_SCALE], dim=-1).numpy(), 0.0
    prior, marginal, sde_fn, _ = init_sde('ve')
    model = PolygonPackingTransformer(marginal_prob_std_func=marginal, device=device).to(device)
    weights = request.get('weights') or str(GFPACK / 'checkpoints' / 'score_model.pth')
    model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True))
    if request['eval_mode']:
        model.eval()
    centred = [((ring - c) * scale).tolist() for ring, c in grown]
    gnn = create_gnn_data(centred).to(device)
    ids = torch.arange(n, dtype=torch.int64)
    mask = torch.zeros(n, dtype=torch.float32)
    t0 = time.perf_counter()
    with torch.no_grad():
        _, final = pc_sampler_state(model, sde_fn, n, ids, gnn, mask, batch_size=batch, num_steps=steps)
    return final.cpu().numpy(), time.perf_counter() - t0


class Layout:
    """Rotated, centred polygons (mm) with translations; legalised in place."""

    def __init__(self, bases, angles_deg, trans, strip_mm):
        self.base, self.strip = bases, strip_mm
        self.angle = np.asarray(angles_deg, float)
        self.t = np.asarray(trans, float).copy()
        self.rot = [affinity.rotate(b, a, origin=(0, 0)) for b, a in zip(bases, self.angle)]

    def poly(self, i, dt=(0.0, 0.0)):
        return affinity.translate(self.rot[i], self.t[i, 0] + dt[0], self.t[i, 1] + dt[1])

    def pull_inside(self):
        for i in range(len(self.rot)):
            b = self.poly(i).bounds
            self.t[i, 1] += max(0.0, -b[1]) - max(0.0, b[3] - self.strip)
            self.t[i, 0] += max(0.0, -b[0])

    def overlaps(self):
        """Pairs that penetrate each other by more than PENETRATION_MM (touching pieces are fine)."""
        polys = [self.poly(i) for i in range(len(self.rot))]
        eroded = [p.buffer(-PENETRATION_MM) for p in polys]
        out = []
        for i in range(len(polys)):
            for j in range(i + 1, len(polys)):
                if polys[i].bounds[2] < polys[j].bounds[0] or polys[j].bounds[2] < polys[i].bounds[0]:
                    continue
                if eroded[i].intersects(polys[j]):
                    out.append((eroded[i].intersection(polys[j]).area, i, j, polys[i], polys[j]))
        return out

    def legalise(self, iterations=400, rng=None):
        rng = rng or np.random.default_rng(0)
        for _ in range(iterations):
            self.pull_inside()
            pairs = self.overlaps()
            if not pairs:
                return True
            for _a, i, j, pi, pj in pairs:
                d = np.array(pj.centroid.coords[0]) - np.array(pi.centroid.coords[0])
                norm = np.hypot(*d)
                d = d / norm if norm > 1e-9 else rng.normal(size=2) / math.sqrt(2)
                # smallest separation along d by growth + bisection (concave pieces: not an MTV, but exact)
                ei = pi.buffer(-PENETRATION_MM)
                hi = 8.0
                while ei.intersects(affinity.translate(pj, *(d * hi))) and hi < 4000:
                    hi *= 2
                lo = 0.0
                for _b in range(14):
                    mid = (lo + hi) / 2
                    if ei.intersects(affinity.translate(pj, *(d * mid))):
                        lo = mid
                    else:
                        hi = mid
                move = hi * 1.002 + 0.02
                self.t[j] += d * move / 2
                self.t[i] -= d * move / 2
        self.pull_inside()
        return not self.overlaps()


def snap(theta_deg, allowed):
    if allowed is None:
        return theta_deg
    a = np.asarray(allowed, float)
    diff = np.abs((theta_deg[..., None] - a + 180.0) % 360.0 - 180.0)
    return a[np.argmin(diff, axis=-1)]


def compact(layouts, scale):
    """GFPack++'s own slide-left / slide-down compaction, in scaled model units."""
    polys = [(b.exterior.coords[:-1]) for b in layouts[0].base]
    polys_u = [[[float(x * scale), float(y * scale)] for x, y in p] for p in polys]
    ids = [list(range(len(polys))) for _ in layouts]
    thetas = [[math.radians(a) for a in L.angle] for L in layouts]
    acts = [[[float(t[0] * scale), float(t[1] * scale)] for t in L.t] for L in layouts]
    res = rmspacing.rm_spacing_all(ids, thetas, acts, polys_u, 1e9, STRIP_UNITS, 1.0)
    for L, r in zip(layouts, res):
        L.t = np.asarray(r, float) / scale
    return layouts


def _legalise_job(job):
    L, seed = job
    ok = L.legalise(rng=np.random.default_rng(seed))
    return ok, L.t


def _parallel_legalise(layouts, seed):
    import multiprocessing as mp
    with mp.get_context('fork').Pool(min(8, mp.cpu_count())) as pool:
        results = pool.map(_legalise_job, [(L, seed * 100003 + i) for i, L in enumerate(layouts)], chunksize=2)
    oks = []
    for L, (ok, t) in zip(layouts, results):
        L.t = t
        oks.append(ok)
    return oks


def main(req_path, out_path):
    request = json.loads(Path(req_path).read_text(encoding='utf-8'))
    device = torch.device('cpu')
    grown, r = grown_polygons(request)
    strip_mm = request['fabric_width_mm'] - 2 * (request['margin_mm'] - r)
    scale = STRIP_UNITS / strip_mm
    n = len(grown)
    request.setdefault('random_length_units', 0.0)
    if request['init'] == 'random':
        area = sum(Polygon(g).area for g, _ in grown)
        request['random_length_units'] = 1.25 * area * scale * scale / STRIP_UNITS
    t0 = time.perf_counter()
    poses, sample_s = sample_poses(request, grown, scale, device)
    sampled_s = time.perf_counter() - t0
    allowed = None if request['snap'] == 'none' else request['allowed_rotations']
    bases = [Polygon((g - c)) for g, c in grown]
    layouts, raw_overlap = [], []
    t1 = time.perf_counter()
    rng = np.random.default_rng(request['seed'])
    for s in range(poses.shape[0]):
        p = poses[s]
        theta = np.degrees(np.arctan2(p[:, 3], p[:, 2]))
        theta = snap(theta, allowed)
        # model frame -> mm; shift the layout to the strip's lower-left like GFPack++'s evaluation does
        trans = p[:, :2] / scale
        trans = trans - np.array([0.0, 0.0])
        L = Layout(bases, theta, trans, strip_mm)
        raw_overlap.append(sum(a for a, *_ in L.overlaps()))
        layouts.append(L)
    # shift each layout so the lower-left of its bounding box is the origin (their evaluation does the same)
    for L in layouts:
        bs = np.array([L.poly(i).bounds for i in range(n)])
        L.t -= np.array([bs[:, 0].min(), bs[:, 1].min()])
    ok = _parallel_legalise(layouts, request['seed'])
    good = [L for L, o in zip(layouts, ok) if o]
    if good:
        compact(good, scale)
    legal_s = time.perf_counter() - t1
    rows = []
    for L in good:
        polys = [L.poly(i) for i in range(n)]
        bs = np.array([p.bounds for p in polys])
        inside = bs[:, 1].min() >= -BOUND_TOL_MM and bs[:, 3].max() <= strip_mm + BOUND_TOL_MM
        clear = not L.overlaps()
        length = bs[:, 2].max() - bs[:, 0].min() + 2 * (request['margin_mm'] - r)
        rows.append({'length_mm': float(length), 'inside': bool(inside), 'clear': bool(clear), 'L': L})
    fail_inside = sum(1 for x in rows if not x['inside'])
    fail_clear = sum(1 for x in rows if not x['clear'])
    rows = [x for x in rows if x['inside'] and x['clear']]
    rows.sort(key=lambda x: x['length_mm'])
    top = []
    for x in rows[:request['top_k']]:
        L = x['L']
        placement = {}
        for i, key in enumerate(request['keys']):
            a = math.radians(L.angle[i])
            c = grown[i][1]
            rc = np.array([c[0] * math.cos(a) - c[1] * math.sin(a), c[0] * math.sin(a) + c[1] * math.cos(a)])
            tx, ty = L.t[i] - rc
            placement[key] = [float(L.angle[i]) % 360.0, float(tx), float(ty + (request['margin_mm'] - r))]
        top.append({'length_mm_estimate': x['length_mm'], 'placements': placement})
    lens = sorted(x['length_mm'] for x in rows)
    response = {
        'init': request['init'], 'snap': request['snap'], 'samples': int(poses.shape[0]), 'steps': request['steps'],
        'eval_mode': request['eval_mode'], 'scale_units_per_mm': scale, 'strip_mm': strip_mm,
        'sampler_s': sampled_s, 'legalise_s': legal_s,
        'raw_overlap_mm2_median': float(np.median(raw_overlap)) * 1.0,
        'legalised': len(good), 'feasible': len(rows), 'compaction_left_strip': fail_inside,
        'compaction_overlapped': fail_clear,
        'estimate_length_quantiles': {q: (float(np.quantile(lens, q)) if lens else None) for q in (0.0, 0.1, 0.5)},
        'top': top,
    }
    Path(out_path).write_text(json.dumps(response), encoding='utf-8')
    print(json.dumps({k: v for k, v in response.items() if k != 'top'}, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
