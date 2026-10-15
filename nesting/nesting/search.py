"""Search over placement order and orientation for a small discrete instance.

Research heuristic tuned to this study's constraints: rotations limited to the
grain rule, 1x/2x quantities, mirrored second copies, fixed roll width. Items
are single copies (pre-nested mirrored pairs on request); a beam search
shortlists children by an admissible completion bound and ranks them by greedy
roll-outs (complete markers), then an iterated local search with restarts over
the sequence and a compaction pass polish the best layout. Deterministic for a
given seed unless the time limit stops it early.
"""
from dataclasses import dataclass, field
import random
import time

import numpy as np
import shapely

from .grain import check_grain
from .placer import Component, Item, Layout, Placer, Roll, verify, world_components, world_polygons
from .polygons import Shape, transform_geometry

MIRROR_RULES = ('pairs', 'none', 'free')
# Grain rule (user decision, 2026-10-01): every grain line runs along or across the roll, never tilted.
# 90/270 cut a piece cross-grain; `--rotations 0,180` keeps every grain line along the roll.
DEFAULT_ROTATIONS = (0.0, 90.0, 180.0, 270.0)


@dataclass
class Settings:
    fabric_width_mm: float = 1007.0
    gap_mm: float = 5.0
    edge_margin_mm: float = 5.0
    rotations: tuple = DEFAULT_ROTATIONS
    mirror: str = 'pairs'
    beam: int = 16
    window: int = 4
    iterations: int = 1500
    seed: int = 0
    time_limit_s: float = 120.0
    # Pre-nested mirrored pairs trap the local search, which cannot split them (docs/nesting.md).
    pairs: bool = False
    placement: str = 'bottom-left'
    restart_patience: int = 2500

    def to_dict(self):
        return {'fabric_width_mm': self.fabric_width_mm, 'gap_mm': self.gap_mm,
                'edge_margin_mm': self.edge_margin_mm, 'rotations': list(self.rotations),
                'mirror': self.mirror, 'beam': self.beam, 'window': self.window,
                'iterations': self.iterations, 'seed': self.seed, 'time_limit_s': self.time_limit_s,
                'pairs': self.pairs, 'placement': self.placement, 'restart_patience': self.restart_patience}


def mirror_options(rule, copy):
    if rule not in MIRROR_RULES:
        raise ValueError(f'mirror rule must be one of {MIRROR_RULES}')
    if rule == 'pairs':
        return (copy == 2,)
    if rule == 'none':
        return (False,)
    return (False, True)


def _collision_union(placer, item, rotation):
    polys = [transform_geometry(placer.shapes[c.shape_id].collision, c.mirrored, c.rotation, c.x, c.y)
             for c in world_components(item, rotation)]
    geom = shapely.union_all(polys)
    minx, miny, _, _ = geom.bounds
    return shapely.transform(geom, lambda xy: xy - np.array([minx, miny]))


def distinct_rotations(placer, item, rotations, tolerance=0.005):
    """Drop rotations whose placed geometry repeats an earlier one (symmetric pieces)."""
    kept, geoms = [], []
    for rotation in rotations:
        g = _collision_union(placer, item, rotation)
        if any(g.symmetric_difference(h).area < tolerance * g.area for h in geoms):
            continue
        kept.append(rotation)
        geoms.append(g)
    return tuple(kept)


def best_pair(placer, shape, m1, m2, rotations):
    """Pre-nest copy 2 against copy 1: the exclusion-boundary vertex with the best bbox fill."""
    best = None
    for rotation in rotations:
        region = placer.cache.exclusion(shape.id, m1, 0.0, shape.id, m2, rotation)
        b1 = shape.true_bounds(m1, 0.0)
        b2 = shape.true_bounds(m2, rotation)
        coords = shapely.get_coordinates(region)
        w = np.maximum(b1[2], b2[2] + coords[:, 0]) - np.minimum(b1[0], b2[0] + coords[:, 0])
        h = np.maximum(b1[3], b2[3] + coords[:, 1]) - np.minimum(b1[1], b2[1] + coords[:, 1])
        fill = 2 * shape.area_mm2 / (w * h)
        i = int(np.argmax(fill))
        if best is None or fill[i] > best[0] + 1e-9:
            best = (float(fill[i]), rotation, float(coords[i, 0]), float(coords[i, 1]))
    return best


def build_items(placer, pieces, settings):
    """Single-copy items plus one pre-nested pair item per 2x shape."""
    items = []
    for piece in pieces:
        shape = placer.shapes[piece.id]
        for copy in range(1, piece.quantity + 1):
            for m in mirror_options(settings.mirror, copy):
                suffix = 'm' if (m and settings.mirror == 'free') else ''
                items.append(Item(f'{piece.id}#{copy}{suffix}',
                                  (Component(piece.id, copy, m, 0.0, 0.0, 0.0),),
                                  ((piece.id, copy),), shape.area_mm2))
        if settings.pairs and piece.quantity == 2:
            for m1 in mirror_options(settings.mirror, 1):
                for m2 in mirror_options(settings.mirror, 2):
                    fill, rotation, dx, dy = best_pair(placer, shape, m1, m2, settings.rotations)
                    suffix = ('m' if m1 else '') + ('m' if m2 else '')
                    items.append(Item(f'{piece.id}#pair{suffix}',
                                      (Component(piece.id, 1, m1, 0.0, 0.0, 0.0),
                                       Component(piece.id, 2, m2, rotation, dx, dy)),
                                      ((piece.id, 1), (piece.id, 2)), 2 * shape.area_mm2))
    return items


@dataclass
class State:
    layout: Layout
    remaining: frozenset
    sequence: tuple = ()


def _candidates(items, remaining):
    out = []
    for item in items:
        copies = set(item.copies)
        if not copies <= remaining:
            continue
        if any(copy == 2 and (shape, 1) in remaining and (shape, 1) not in copies for shape, copy in copies):
            continue          # copy 2 only after copy 1 (symmetry breaking)
        out.append(item)
    return out


def _bound(state, roll, area_by_copy):
    """Admissible completion bound: current length plus the remaining area spread over the usable width."""
    remaining_area = sum(area_by_copy[c] for c in state.remaining)
    bound = state.layout.length_mm + remaining_area / (roll.fabric_width_mm - 2 * roll.margin_mm)
    return (round(bound, 6), round(-state.layout.fill, 6), round(state.layout.top_sum, 3))


def rollout(placer, state, items, rotations_by_item):
    """Greedy completion: largest remaining item first, best rotation by the placement key."""
    layout, remaining, sequence = state.layout, state.remaining, state.sequence
    while remaining:
        cands = sorted(_candidates(items, remaining), key=lambda it: (-it.area_mm2, it.id))
        if not cands:
            return None
        item, best = cands[0], None
        for rotation in rotations_by_item[item.id]:
            trial = placer.place(layout, item, rotation)
            if trial is None:
                continue
            new = trial.placed[-1]
            key = (trial.length_mm, new.bounds[3], new.x)
            if best is None or key < best[0]:
                best = (key, trial, rotation)
        if best is None:
            return None
        layout, remaining = best[1], remaining - set(item.copies)
        sequence = sequence + ((item, best[2]),)
    return State(layout, remaining, sequence)


def _final_key(state):
    return (round(state.layout.length_mm, 6), round(-state.layout.fill, 6))


class Progress:
    """Reports each new best complete marker as (seconds since start, length) to an optional callback."""

    def __init__(self, started, callback=None):
        self.started, self.callback, self.best = started, callback, float('inf')

    def offer(self, length_mm):
        if length_mm < self.best - 1e-9:
            self.best = length_mm
            if self.callback is not None:
                self.callback(time.time() - self.started, length_mm)


def beam_search(placer, items, rotations_by_item, area_by_copy, settings, deadline, progress=None):
    """Beam over placement order x rotation. Children are pre-ranked by the completion bound,
    then the best 2 x beam are ranked by a greedy rollout; every rollout is a candidate result."""
    roll = placer.roll
    frontier = [State(Layout(roll), frozenset(area_by_copy))]
    completed, hit_limit = [], False
    while frontier and not hit_limit:
        children = {}
        for state in frontier:
            cands = sorted(_candidates(items, state.remaining), key=lambda it: (-it.area_mm2, it.id))
            for item in cands[:settings.window]:
                for rotation in rotations_by_item[item.id]:
                    layout = placer.place(state.layout, item, rotation)
                    if layout is None:
                        continue
                    child = State(layout, state.remaining - set(item.copies), state.sequence + ((item, rotation),))
                    key = (child.remaining, round(layout.length_mm, 2))
                    score = _bound(child, roll, area_by_copy)
                    if key not in children or score < children[key][0]:
                        children[key] = (score, child)
        shortlist = [child for _, child in sorted(children.values(), key=lambda sc: sc[0])[:2 * settings.beam]]
        ranked = []
        for child in shortlist:
            if time.time() > deadline:
                hit_limit = True
                break
            if not child.remaining:
                completed.append(child)
                if progress is not None:
                    progress.offer(child.layout.length_mm)
                ranked.append((_final_key(child), child))
                continue
            finished = rollout(placer, child, items, rotations_by_item)
            if finished is None:
                continue
            completed.append(finished)
            if progress is not None:
                progress.offer(finished.layout.length_mm)
            ranked.append((_final_key(finished), child))
        ranked.sort(key=lambda rc: rc[0])
        frontier = [child for _, child in ranked[:settings.beam] if child.remaining]
    if not completed:
        raise RuntimeError('time limit reached before any complete layout')
    completed.sort(key=_final_key)
    return completed[0], hit_limit


def _neighbours(sequence, rotations_by_item):
    """Every swap, rotation change and re-insertion of the sequence, as new lists."""
    n = len(sequence)
    for i in range(n):
        for j in range(i + 1, n):
            seq = list(sequence)
            seq[i], seq[j] = seq[j], seq[i]
            yield seq
        item, rotation = sequence[i]
        for alt in rotations_by_item[item.id]:
            if alt != rotation:
                seq = list(sequence)
                seq[i] = (item, alt)
                yield seq
        for j in range(n):
            if j != i:
                seq = list(sequence)
                entry = seq.pop(i)
                seq.insert(j, entry)
                yield seq


def _random_move(sequence, rotations_by_item, rng):
    seq = list(sequence)
    i = rng.randrange(len(seq))
    move = rng.choice(('swap', 'rotate', 'insert'))
    if move == 'swap' and len(seq) > 1:
        j = rng.randrange(len(seq) - 1)
        j = j + 1 if j >= i else j
        seq[i], seq[j] = seq[j], seq[i]
    elif move == 'rotate':
        item, _ = seq[i]
        options = rotations_by_item[item.id]
        seq[i] = (item, options[rng.randrange(len(options))])
    elif len(seq) > 1:
        entry = seq.pop(i)
        seq.insert(rng.randrange(len(seq) + 1), entry)
    return seq


class PrefixDecoder:
    """placer.decode with every placed prefix cached. Sequences that share a start reuse its layout,
    so a neighbourhood scan pays only for the changed tail; the layouts are the ones placer.decode
    returns. The cache is dropped whenever it holds `limit` prefixes, which bounds its memory."""

    def __init__(self, placer, limit=100_000):
        self.placer, self.limit, self.cache = placer, limit, {}

    def __call__(self, sequence):
        keys = tuple((item.id, rotation) for item, rotation in sequence)
        k, layout = len(keys), None
        while k > 0 and layout is None:
            layout = self.cache.get(keys[:k])
            if layout is None:
                k -= 1
        if layout is None:
            layout = Layout(self.placer.roll)
        for i in range(k, len(keys)):
            item, rotation = sequence[i]
            layout = self.placer.place(layout, item, rotation)
            if layout is None:
                return None
            if len(self.cache) >= self.limit:
                self.cache.clear()
            self.cache[keys[:i + 1]] = layout
        return layout


def _search_key(layout):
    """Marker length first; among equal lengths the layout whose pieces sit lower (smaller sum of
    item tops) wins, which gives the climb a direction on the long plateaus of equal length."""
    return (round(layout.length_mm, 6), round(layout.top_sum, 3))


def _hill_climb(decode, sequence, rotations_by_item, rng, budget, deadline, progress=None):
    """First-improvement descent over swaps, rotation changes and re-insertions (seeded order).
    budget is a one-element list of remaining decodes; returns (sequence, layout, key, hit_limit)."""
    best_seq = list(sequence)
    best = decode(best_seq)
    if best is None:
        return None
    best_key = _search_key(best)
    improved = True
    while improved and budget[0] > 0:
        improved = False
        neighbours = list(_neighbours(best_seq, rotations_by_item))
        rng.shuffle(neighbours)
        for seq in neighbours:
            if budget[0] <= 0:
                break
            if time.time() > deadline:
                return best_seq, best, best_key, True
            budget[0] -= 1
            layout = decode(seq)
            if layout is None:
                continue
            key = _search_key(layout)
            if key < best_key:
                best_seq, best, best_key, improved = seq, layout, key, True
                if progress is not None:
                    progress.offer(layout.length_mm)
                break
    return best_seq, best, best_key, False


def local_search(placer, sequence, rotations_by_item, settings, deadline, progress=None):
    """Iterated local search with restarts. A run climbs from the beam sequence, then repeatedly
    perturbs its best with two random moves and climbs again, accepting equal-or-better results.
    A run that finds no better layout within `restart_patience` decodes ends, and the next run
    starts from the beam sequence with its own random order, so the runs settle into different
    rotation combinations; the best of all runs is kept. `iterations` bounds the total number of
    decodes, so the outcome is deterministic for a seed. Returns (sequence, layout, hit_limit, runs)."""
    budget = [settings.iterations]
    decode = PrefixDecoder(placer)
    best, runs, hit_limit = None, 0, False
    while budget[0] > 0 and not hit_limit:
        rng = random.Random(settings.seed * 1_000_003 + runs)
        runs += 1
        climbed = _hill_climb(decode, sequence, rotations_by_item, rng, budget, deadline, progress)
        if climbed is None:
            break
        run_seq, run_layout, run_key, hit_limit = climbed
        stale = 0
        while budget[0] > 0 and not hit_limit and stale < settings.restart_patience:
            before = budget[0]
            seq = _random_move(_random_move(run_seq, rotations_by_item, rng), rotations_by_item, rng)
            climbed = _hill_climb(decode, seq, rotations_by_item, rng, budget, deadline, progress)
            stale += max(1, before - budget[0])
            if climbed is None:
                continue
            seq, layout, key, hit_limit = climbed
            if key < run_key:
                stale = 0
            if key <= run_key:
                run_seq, run_layout, run_key = seq, layout, key
        if best is None or run_key < best[2]:
            best = (run_seq, run_layout, run_key)
    if best is None:                       # no decode budget: the beam sequence as it is
        return list(sequence), decode(list(sequence)), hit_limit, runs
    return best[0], best[1], hit_limit, runs


def nest(pieces, settings, on_improve=None):
    """Nest the pieces on the roll and return a JSON-ready result with placements and totals."""
    started = time.time()
    deadline = started + settings.time_limit_s
    shapes = [Shape(p) for p in pieces]
    total_height = sum(p.height_mm * p.quantity for p in pieces) + sum(p.width_mm * p.quantity for p in pieces)
    roll = Roll(settings.fabric_width_mm, settings.gap_mm, settings.edge_margin_mm,
                total_height + 4 * settings.edge_margin_mm + 100.0)
    placer = Placer(shapes, roll, settings.placement)
    for piece in pieces:
        if min(piece.width_mm, piece.height_mm) + 2 * settings.edge_margin_mm > settings.fabric_width_mm:
            raise ValueError(f'{piece.id}: does not fit across the roll in any allowed orientation')
    items = build_items(placer, pieces, settings)
    rotations_by_item = {item.id: distinct_rotations(placer, item, settings.rotations) for item in items}
    area_by_copy = {(p.id, c): p.area_mm2 for p in pieces for c in range(1, p.quantity + 1)}
    progress = Progress(started, on_improve)
    best_state, limit_beam = beam_search(placer, items, rotations_by_item, area_by_copy, settings, deadline, progress)
    stages = {'beam_length_mm': round(best_state.layout.length_mm, 3), 'beam_s': round(time.time() - started, 2)}
    sequence, layout, limit_local, runs = local_search(placer, best_state.sequence, rotations_by_item, settings,
                                                       deadline, progress)
    stages['local_length_mm'] = round(layout.length_mm, 3)
    stages['local_runs'] = runs
    layout = placer.compact(layout, settings.rotations)
    progress.offer(layout.length_mm)
    stages['compact_length_mm'] = round(layout.length_mm, 3)
    issues, min_distance = verify(placer.shapes, layout)
    if issues:
        raise RuntimeError('nesting produced an invalid marker: ' + '; '.join(issues))
    runtime = time.time() - started
    return _result(pieces, placer, layout, sequence, settings, runtime, min_distance, limit_beam or limit_local, stages)


def _result(pieces, placer, layout, sequence, settings, runtime, min_distance, hit_limit, stages):
    from .pieces import transform_marks, transform_points
    by_id = {p.id: p for p in pieces}
    placements = []
    for placed in layout.placed:
        for c in placed.components:
            piece = by_id[c.shape_id]
            placements.append({
                'piece_id': c.shape_id, 'copy': c.copy, 'rotation_deg': c.rotation, 'mirrored': c.mirrored,
                'x_mm': round(c.x, 4), 'y_mm': round(c.y, 4), 'item': placed.item.id,
                'contour': _round(transform_points(piece.contour, c.mirrored, c.rotation, c.x, c.y)),
                'seam_line': _round(transform_points(piece.seam_line, c.mirrored, c.rotation, c.x, c.y)),
                'grain_line': _round(transform_points(piece.grain_line, c.mirrored, c.rotation, c.x, c.y)),
                'marks': [{'kind': m['kind'], 'points': _round(m['points'])}
                          for m in transform_marks(piece.marks, c.mirrored, c.rotation, c.x, c.y)],
            })
    placements.sort(key=lambda p: (p['piece_id'], p['copy']))
    piece_area = sum(p.area_mm2 * p.quantity for p in pieces)
    width, margin = settings.fabric_width_mm, settings.edge_margin_mm
    length = layout.length_mm
    naive = sum(p.height_mm * p.quantity for p in pieces) + settings.gap_mm * (sum(p.quantity for p in pieces) - 1) + 2 * margin
    return {
        'version': 'nesting-study/1',
        'settings': settings.to_dict(),
        'sequence': [f'{item.id}@{rotation:g}' for item, rotation in sequence],
        'placements': placements,
        'totals': {
            'fabric_width_mm': width,
            'length_mm': round(length, 3),
            'piece_area_mm2': round(piece_area, 1),
            'efficiency_pct': round(100.0 * piece_area / (width * length), 2),
            'lower_bound_length_mm': round(piece_area / (width - 2 * margin) + 2 * margin, 1),
            'naive_stack_length_mm': round(naive, 1),
            'min_distance_mm': round(min_distance, 3) if min_distance is not None else None,
            'placements': len(placements),
            'runtime_s': round(runtime, 2),
            'nfp_count': placer.cache.computed,
            'time_limit_hit': bool(hit_limit),
        },
        'stages': stages,
        'grain': check_grain(placements, settings.rotations, settings.mirror),
    }


def _round(points, digits=3):
    return [[round(float(x), digits), round(float(y), digits)] for x, y in points]
