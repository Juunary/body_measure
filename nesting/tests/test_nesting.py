"""End-to-end nesting invariants and the command line."""
import json
from pathlib import Path
import random
import subprocess
import sys

import pytest
from shapely.geometry import Polygon, box

from nesting.pattern_pdf import import_pdf
from nesting.pieces import transform_points
from nesting.placer import Placer, Roll
from nesting.polygons import Shape
from nesting.search import PrefixDecoder, Settings, build_items, nest

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'examples' / 'schnittteile-hemd.pdf'
SMALL = dict(beam=2, window=2, iterations=5, time_limit_s=600.0)


@pytest.fixture(scope='module')
def pieces():
    return import_pdf(PDF)[1]


@pytest.fixture(scope='module')
def result(pieces):
    return nest(pieces, Settings(**SMALL))


def test_marker_invariants(pieces, result):
    t, s = result['totals'], result['settings']
    placements = result['placements']
    assert t['placements'] == len(placements) == 9
    assert sorted((p['piece_id'], p['copy']) for p in placements) == sorted(
        (p.id, c) for p in pieces for c in range(1, p.quantity + 1))
    by_id = {p.id: p for p in pieces}
    polys = []
    assert result['grain']['off'] == 0 and not result['grain']['problems']   # grain along or across, never tilted
    for p in placements:
        assert p['rotation_deg'] in s['rotations']
        assert p['mirrored'] == (by_id[p['piece_id']].quantity == 2 and p['copy'] == 2)
        local = by_id[p['piece_id']].contour
        rebuilt = transform_points(local, p['mirrored'], p['rotation_deg'], p['x_mm'], p['y_mm'])
        assert max(abs(a - b) for pa, pb in zip(rebuilt, p['contour']) for a, b in zip(pa, pb)) < 2e-3
        polys.append(Polygon(p['contour']))
    frame = box(s['edge_margin_mm'], s['edge_margin_mm'], s['fabric_width_mm'] - s['edge_margin_mm'],
                t['length_mm'] - s['edge_margin_mm']).buffer(1e-2)
    for i, a in enumerate(polys):
        assert frame.covers(a)
        for b in polys[i + 1:]:
            assert a.distance(b) >= s['gap_mm'] - 0.05
    assert t['min_distance_mm'] >= s['gap_mm'] - 0.05
    assert t['length_mm'] < t['naive_stack_length_mm']
    assert t['length_mm'] >= t['lower_bound_length_mm']
    assert t['efficiency_pct'] >= 65.0
    assert t['time_limit_hit'] is False


def test_same_seed_same_marker(pieces, result):
    again = nest(pieces, Settings(**SMALL))
    assert again['placements'] == result['placements']
    assert again['totals']['length_mm'] == result['totals']['length_mm']


def test_strict_grain_and_no_mirror(pieces):
    subset = pieces[:4]
    strict = nest(subset, Settings(rotations=(0.0, 180.0), mirror='none', pairs=False, **SMALL))
    assert {p['rotation_deg'] for p in strict['placements']} <= {0.0, 180.0}
    assert not any(p['mirrored'] for p in strict['placements'])
    assert strict['totals']['placements'] == sum(p.quantity for p in subset)


def test_command_line(tmp_path):
    env = {'PYTHONUTF8': '1'}
    pieces_json = tmp_path / 'pieces.json'
    run = subprocess.run([sys.executable, '-m', 'nesting', 'import', str(PDF), '-o', str(pieces_json)],
                         cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env={**__import__('os').environ, **env})
    assert run.returncode == 0, run.stderr
    assert pieces_json.is_file() and pieces_json.with_suffix('.svg').is_file()
    out = tmp_path / 'marker'
    run = subprocess.run([sys.executable, '-m', 'nesting', 'nest', str(pieces_json), '-o', str(out),
                          '--beam', '1', '--window', '1', '--iterations', '0', '--rotations', '0,180'],
                         cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env={**__import__('os').environ, **env})
    assert run.returncode == 0, run.stderr
    document = json.loads((out / 'marker.json').read_text(encoding='utf-8'))
    assert document['totals']['placements'] == 9
    assert (out / 'marker.svg').is_file() and (out / 'report.md').is_file()
    assert 'efficiency' in run.stdout


def test_prefix_decoder_returns_the_plain_decode(pieces):
    subset, settings = pieces[:4], Settings(**SMALL)
    placer = Placer([Shape(p) for p in subset], Roll(settings.fabric_width_mm, settings.gap_mm, settings.edge_margin_mm, 5000.0))
    items, decode, rng = build_items(placer, subset, settings), PrefixDecoder(placer), random.Random(3)
    for _ in range(12):
        order = items[:]
        rng.shuffle(order)
        sequence = [(item, rng.choice(settings.rotations)) for item in order]
        plain, cached = placer.decode(sequence), decode(sequence)
        assert [(p.item.id, p.rotation, p.x, p.y) for p in cached.placed] == [(p.item.id, p.rotation, p.x, p.y) for p in plain.placed]
        assert cached.length_mm == plain.length_mm


def test_local_search_restarts_and_keeps_the_best_run(pieces):
    result = nest(pieces[:4], Settings(beam=2, window=2, iterations=1500, restart_patience=40, time_limit_s=600.0))
    assert result['stages']['local_runs'] > 1
    assert not any('#pair' in step for step in result['sequence'])        # pairs are off by default
    assert result['totals']['length_mm'] <= result['stages']['beam_length_mm'] + 1e-6
    assert result['totals']['time_limit_hit'] is False
