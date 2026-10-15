"""Convex decomposition, no-fit polygons and the bottom-left placer."""
import random
from pathlib import Path

import pytest
import shapely
from shapely import affinity
from shapely.geometry import Polygon, box

from nesting.pattern_pdf import import_pdf
from nesting.pieces import Piece
from nesting.placer import Component, Item, Layout, Placer, Roll, verify
from nesting.polygons import NfpCache, Shape, convex_parts, nfp_raw, reflex_count, transform_geometry

PDF = Path(__file__).resolve().parents[1] / 'examples' / 'schnittteile-hemd.pdf'
GAP = 5.0


@pytest.fixture(scope='module')
def shapes():
    _, pieces = import_pdf(PDF)
    return [Shape(p) for p in pieces]


@pytest.fixture(scope='module')
def cache(shapes):
    return NfpCache(shapes, GAP)


def rectangle(pid, w, h, quantity=1):
    ring = [[0, 0], [w, 0], [w, h], [0, h]]
    return Piece(pid, quantity, ring, ring, [[w / 2, 0], [w / 2, h]], 90.0)


def test_rectangle_nfp_is_analytic():
    raw = nfp_raw(convex_parts(box(0, 0, 30, 20)), convex_parts(box(0, 0, 10, 5)))
    assert raw.symmetric_difference(box(-10, -5, 30, 20)).area < 1e-6


def test_convex_parts_cover_each_shape(shapes):
    for s in shapes:
        parts = [Polygon(p) for p in s.parts]
        assert shapely.union_all(parts).symmetric_difference(s.collision).area < 1e-6 * s.collision.area
        assert all(p.convex_hull.area - p.area < 1e-6 for p in parts)
        assert len(parts) <= 2 * reflex_count(s.collision) + 1


def test_exclusion_boundary_keeps_the_gap(shapes, cache):
    a, b = shapes[1], shapes[2]                       # VORDERTEIL, AERMEL
    region = cache.exclusion(a.id, False, 0, b.id, True, 90)
    moving = transform_geometry(b.true, True, 90)
    rng = random.Random(1)
    for _ in range(30):
        p = region.exterior.interpolate(rng.random(), normalized=True)
        d = affinity.translate(moving, p.x, p.y).distance(a.true)
        # never closer than the gap; at most gap + 2 x simplification tolerance (both pieces) + slack
        assert GAP - 0.05 <= d <= GAP + 1.1
    inner, outer = region.buffer(-1.0).exterior, region.buffer(1.0).exterior
    for _ in range(10):
        p = inner.interpolate(rng.random(), normalized=True)
        assert affinity.translate(moving, p.x, p.y).distance(a.true) < GAP
        q = outer.interpolate(rng.random(), normalized=True)
        assert affinity.translate(moving, q.x, q.y).distance(a.true) > GAP


def test_exclusion_equivariance(shapes, cache):
    a, b = shapes[3].id, shapes[4].id                 # PASSE, OBERKRAGEN
    base = cache.exclusion(a, False, 0, b, False, 0)
    assert transform_geometry(base, False, 90).symmetric_difference(cache.exclusion(a, False, 90, b, False, 90)).area < 1e-3
    assert transform_geometry(base, True, 0).symmetric_difference(cache.exclusion(a, True, 0, b, True, 0)).area < 1e-3
    reverse = cache.exclusion(b, False, 0, a, False, 0)
    assert shapely.transform(base, lambda c: -c).symmetric_difference(reverse).area < 1e-3
    mixed = cache.exclusion(a, False, 0, b, True, 270)
    mixed_reverse = cache.exclusion(b, True, 270, a, False, 0)
    assert shapely.transform(mixed, lambda c: -c).symmetric_difference(mixed_reverse).area < 1e-3


def test_rectangles_go_bottom_left_then_beside():
    pieces = [rectangle('A', 300, 200), rectangle('B', 100, 150)]
    roll = Roll(1000.0, GAP, 5.0, 5000.0)
    placer = Placer([Shape(p) for p in pieces], roll)
    items = [Item(p.id, (Component(p.id, 1, False, 0.0, 0.0, 0.0),), ((p.id, 1),), p.area_mm2) for p in pieces]
    layout = placer.decode([(items[0], 0.0), (items[1], 0.0)])
    a, b = layout.placed
    assert (a.x, a.y) == (5.0, 5.0)
    assert b.y == pytest.approx(5.0) and 5.0 + 300 + GAP <= b.x <= 5.0 + 300 + GAP + 0.7
    assert layout.length_mm == pytest.approx(5.0 + 200 + 5.0)
    assert verify(placer.shapes, layout)[0] == []


def test_compaction_never_lengthens_and_verify_catches_overlap(shapes):
    roll = Roll(1007.0, GAP, 5.0, 8000.0)
    placer = Placer(shapes, roll)
    items = [Item(s.id, (Component(s.id, 1, False, 0.0, 0.0, 0.0),), ((s.id, 1),), s.area_mm2) for s in shapes]
    layout = placer.decode([(items[i], r) for i, r in ((5, 0.0), (4, 90.0), (0, 0.0), (2, 180.0), (1, 270.0), (3, 0.0))])
    assert verify(placer.shapes, layout)[0] == []
    compact = placer.compact(layout, (0.0, 90.0, 180.0, 270.0))
    assert compact.length_mm <= layout.length_mm + 1e-9
    assert verify(placer.shapes, compact)[0] == []
    doubled = Layout(roll, layout.placed + [layout.placed[0]], layout.length_mm)
    issues, _ = verify(placer.shapes, doubled)
    assert any('apart' in i for i in issues) and any('duplicate' in i for i in issues)
