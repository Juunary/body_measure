"""Teacher markers for fine-tuning GFPack++ (LoRA): this study's own nester on graded shirt variants.

    python -m bench.gfpack_teacher [--count 240] [--budget 20] [--workers 6]

Every variant scales the pieces of the benchmark shirt by one global factor per axis (about +-15 %, with a
little per-piece jitter) through nesting.grading and nests them with the study's beam search under the same
rules as the benchmark (roll 1007 mm, gap 5 mm, rotations 0/90/180/270, mirrored pairs). Variants whose axis
factors both lie within 3 % of 1 are skipped, so the benchmark instance itself (all factors 1) is never in the
training set. sparrow results are not used anywhere. Only markers the shared evaluator accepts are kept.
"""
import argparse
import concurrent.futures as cf
import json
import math
import random
import time

from nesting.grading import grade
from nesting.pieces import load_pieces

from .evaluate import evaluate
from .instance import DEFAULT_PIECES, MODES, ROOT, SPECS, build_pieces
from .runners import run_ours

OUT = ROOT / 'out' / 'bench' / 'gfpack' / 'teacher'
EXCLUDE_NEAR_ONE = 0.03


def factors_for(index, ids):
    rng = random.Random(10_000 + index)
    while True:
        gx, gy = (math.exp(rng.uniform(-0.15, 0.15)) for _ in range(2))
        if abs(gx - 1) > EXCLUDE_NEAR_ONE or abs(gy - 1) > EXCLUDE_NEAR_ONE:
            break
    return {pid: (gx * math.exp(rng.gauss(0, 0.02)), gy * math.exp(rng.gauss(0, 0.02))) for pid in ids}, (gx, gy)


def make(job):
    index, budget, mode = job
    _, pieces = load_pieces(DEFAULT_PIECES)
    factors, glob = factors_for(index, [p.id for p in pieces])
    inst = build_pieces(grade(pieces, factors), SPECS['roll1007']['fabric_width_mm'])
    t0 = time.perf_counter()
    rec = run_ours(inst, mode, budget, run=index, seed=index)
    ev = rec['evaluation']
    if not ev['valid']:
        return None
    return {'index': index, 'global_factors': glob, 'length_mm': ev['length_mm'], 'efficiency_pct': ev['efficiency_pct'],
            'keys': [c.key for c in inst.copies],
            'polys': [[[float(x), float(y)] for x, y in c.tool] for c in inst.copies],
            'placements': rec['final_placements'], 'seconds': round(time.perf_counter() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--count', type=int, default=240)
    ap.add_argument('--budget', type=int, default=20)
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--mode', default='4rot', choices=sorted(MODES))
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f'teacher_{args.mode}_{args.budget}s.json'
    done = {e['index']: e for e in json.loads(path.read_text())} if path.exists() else {}
    todo = [(i, args.budget, args.mode) for i in range(args.count) if i not in done]
    with cf.ProcessPoolExecutor(max_workers=args.workers) as pool:
        for n, out in enumerate(pool.map(make, todo), 1):
            if out:
                done[out['index']] = out
            if n % 10 == 0 or n == len(todo):
                path.write_text(json.dumps(sorted(done.values(), key=lambda e: e['index'])))
                effs = [e['efficiency_pct'] for e in done.values()]
                print(f'{n}/{len(todo)} nested, {len(done)} valid kept, efficiency {min(effs):.1f}-{max(effs):.1f} %', flush=True)
    print('written', path)


if __name__ == '__main__':
    main()
