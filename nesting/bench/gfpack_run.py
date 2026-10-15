"""Run GFPack++ on the benchmark instance and write run records next to the other nesters' records.

    python -m bench.gfpack_run [--spec roll1007] [--mode 4rot] [--samples 512] [--steps 128] [--runs 3]
                               [--init model|random] [--snap grid|none] [--tag zeroshot]

The model runs in WSL (bench/gfpack_infer.py, CPU torch); this side builds the request from the same
`Instance` every other nester gets and checks the returned layouts with the one shared evaluator
(bench.evaluate). Records go to out/bench/gfpack/runs/. sparrow is not run here: the comparison reads
the sparrow records that already exist.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

from .evaluate import evaluate
from .instance import MODES, ROOT, SPECS, build_spec, write_json

OUT = ROOT / 'out' / 'bench' / 'gfpack'
WSL_ROOT = '/mnt/c/' + ROOT.as_posix()[3:]
WSL_PYTHON = '/opt/gf/.venv/bin/python'
GFPACK_COMMIT = 'ff75815'
CHECKPOINT = 'dental.pth (Google Drive archive linked in the GFPack-pp README)'


def run_once(inst, mode, *, samples, steps, seed, init, snap, eval_mode, top_k, tag, run, weights=None):
    work = OUT / 'work'
    work.mkdir(parents=True, exist_ok=True)
    rid = f'gfpack-{tag}_{mode}_s{samples}x{steps}_r{run}'
    request = {
        'polys': [[[float(x), float(y)] for x, y in c.tool] for c in inst.copies],
        'keys': [c.key for c in inst.copies],
        'fabric_width_mm': inst.fabric_width_mm, 'gap_mm': inst.gap_mm, 'margin_mm': inst.margin_mm,
        'allowed_rotations': list(MODES[mode]), 'samples': samples, 'steps': steps, 'seed': seed,
        'init': init, 'snap': snap, 'eval_mode': eval_mode, 'top_k': top_k, 'weights': weights,
    }
    req_path, res_path = work / f'{rid}.request.json', work / f'{rid}.response.json'
    write_json(req_path, request)
    wsl_work = f'{WSL_ROOT}/out/bench/gfpack/work'
    cmd = ['wsl', '-d', 'Ubuntu', '-u', 'root', '--', 'env', 'PYTHONWARNINGS=ignore', WSL_PYTHON,
           f'{WSL_ROOT}/bench/gfpack_infer.py', f'{wsl_work}/{rid}.request.json', f'{wsl_work}/{rid}.response.json']
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    wall = time.perf_counter() - t0
    if proc.returncode != 0 or not res_path.exists():
        raise RuntimeError(f'GFPack++ failed:\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}')
    response = json.loads(res_path.read_text(encoding='utf-8'))
    candidates, best = [], None
    for cand in response['top']:
        placements = {k: tuple(v) for k, v in cand['placements'].items()}
        ev = evaluate(inst, placements, mode) if snap != 'none' else None
        candidates.append({'estimate_mm': cand['length_mm_estimate'],
                           'valid': ev['valid'] if ev else None, 'length_mm': ev['length_mm'] if ev else None})
        if ev and ev['valid'] and (best is None or ev['length_mm'] < best[1]['length_mm']):
            best = (placements, ev)
    record = {
        'tool': 'gfpack', 'variant': tag, 'id': rid, 'mode': mode, 'run': run, 'wall_s': round(wall, 2),
        'version': f'GFPack++ {GFPACK_COMMIT} ({CHECKPOINT})',
        'settings': {k: request[k] for k in ('samples', 'steps', 'seed', 'init', 'snap', 'eval_mode', 'weights')},
        'model': {k: v for k, v in response.items() if k != 'top'},
        'candidates': candidates,
        'evaluation': best[1] if best else None,
        'final_placements': {k: list(v) for k, v in best[0].items()} if best else None,
        'valid_candidates': sum(1 for c in candidates if c['valid']),
    }
    write_json(OUT / 'runs' / f'{rid}.json', record)
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--spec', default='roll1007', choices=sorted(SPECS))
    ap.add_argument('--mode', default='4rot', choices=sorted(MODES))
    ap.add_argument('--samples', type=int, default=512)
    ap.add_argument('--steps', type=int, default=128)
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--init', default='model', choices=['model', 'random'])
    ap.add_argument('--snap', default='grid', choices=['grid', 'none'])
    ap.add_argument('--no-eval-mode', action='store_true', help='leave dropout on, as GFPack++ evaluate.py does')
    ap.add_argument('--top-k', type=int, default=40)
    ap.add_argument('--weights', default=None, help='merged LoRA state dict, path relative to the nesting folder (default: the released checkpoint)')
    ap.add_argument('--tag', default=None)
    args = ap.parse_args()
    inst = build_spec(args.spec)
    tag = args.tag or ('zeroshot' if args.init == 'model' else 'random')
    for run in range(args.runs):
        rec = run_once(inst, args.mode, samples=args.samples, steps=args.steps, seed=run, init=args.init,
                       snap=args.snap, eval_mode=not args.no_eval_mode, top_k=args.top_k, tag=tag, run=run, weights=f'{WSL_ROOT}/{args.weights}' if args.weights else None)
        ev = rec['evaluation']
        m = rec['model']
        print(f"{rec['id']}: feasible {m['feasible']}/{m['samples']}, valid after shared evaluator "
              f"{rec['valid_candidates']}/{len(rec['candidates'])}, best "
              f"{ev['length_mm'] if ev else '-'} mm, sampler {m['sampler_s']:.0f} s, wall {rec['wall_s']:.0f} s")


if __name__ == '__main__':
    main()
