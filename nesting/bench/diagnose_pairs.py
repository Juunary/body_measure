"""Why the study's search stalls under the 0/180 grain rule.

    python -m bench.diagnose_pairs

Decodes every neighbour of the beam-search result (the moves the local search
can make) and 400 random single-copy sequences, for both grain rules. If random
single-copy sequences beat the whole neighbourhood, the local search is trapped
by the move set, not by the placement decoder.
"""
import random
import time

from nesting.placer import Placer, Roll
from nesting.polygons import Shape
from nesting.search import Settings, _neighbours, beam_search, build_items, distinct_rotations

from .instance import MODES, build


def diagnose(mode, samples=400, seed=1):
    inst = build()
    pieces = sorted(inst.pieces.values(), key=lambda p: (-p.area_mm2, p.id))
    s = Settings(rotations=MODES[mode], pairs=True, beam=16, window=4, iterations=10 ** 9, seed=0, time_limit_s=600.0)
    total = sum((p.height_mm + p.width_mm) * p.quantity for p in pieces)
    placer = Placer([Shape(p) for p in pieces], Roll(s.fabric_width_mm, s.gap_mm, s.edge_margin_mm,
                                                      total + 4 * s.edge_margin_mm + 100.0))
    items = build_items(placer, pieces, s)
    rotations = {it.id: distinct_rotations(placer, it, s.rotations) for it in items}
    area = {(p.id, c): p.area_mm2 for p in pieces for c in range(1, p.quantity + 1)}
    state, _ = beam_search(placer, items, rotations, area, s, time.time() + 600)
    beam = state.layout.length_mm
    neighbours = [placer.decode(n) for n in _neighbours(list(state.sequence), rotations)]
    lengths = [lay.length_mm for lay in neighbours if lay is not None]
    singles = [it for it in items if len(it.copies) == 1]
    rng, best_random = random.Random(seed), float('inf')
    for _ in range(samples):
        order = singles[:]
        rng.shuffle(order)
        layout = placer.decode([(it, rng.choice(rotations[it.id])) for it in order])
        if layout is not None:
            best_random = min(best_random, layout.length_mm)
    return {'mode': mode, 'beam_mm': round(beam, 1),
            'beam_sequence': [f'{it.id}@{r:g}' for it, r in state.sequence],
            'neighbours': len(neighbours), 'best_neighbour_mm': round(min(lengths), 1),
            'random_samples': samples, 'best_random_mm': round(best_random, 1)}


def main():
    for mode in MODES:
        d = diagnose(mode)
        print(f"[{d['mode']}] beam {d['beam_mm']} mm: {', '.join(d['beam_sequence'])}")
        print(f"[{d['mode']}] best of {d['neighbours']} neighbours {d['best_neighbour_mm']} mm; "
              f"best of {d['random_samples']} random single-copy sequences {d['best_random_mm']} mm")


if __name__ == '__main__':
    main()
