"""Bottom-left-fill placement on a fixed-width roll using cached exclusion regions.

Research decoder: a sequence of oriented items is placed one by one at the
lexicographically lowest (marker length, item top, x) vertex of the free
region IFP minus the union of translated exclusion regions. Items may be
compound (a mirrored pair pre-nested as one unit); their exclusion regions are
unions of translated single-shape regions, which is exact.
"""
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import Polygon, box

from .polygons import NfpCache, ifp, rotate_coords, transform_geometry


@dataclass(frozen=True)
class Component:
    shape_id: str
    copy: int
    mirrored: bool
    rotation: float      # relative to the item frame
    dx: float            # offset of the shape origin inside the item frame
    dy: float


@dataclass(frozen=True)
class Item:
    id: str
    components: tuple
    copies: tuple        # (shape_id, copy) consumed by this item
    area_mm2: float


@dataclass(frozen=True)
class Roll:
    fabric_width_mm: float
    gap_mm: float
    margin_mm: float
    max_length_mm: float


@dataclass(frozen=True)
class PlacedComponent:
    shape_id: str
    copy: int
    mirrored: bool
    rotation: float      # world
    x: float             # world origin
    y: float


@dataclass(frozen=True)
class PlacedItem:
    item: Item
    rotation: float
    x: float
    y: float
    bounds: tuple        # true world bounds
    components: tuple    # PlacedComponent


def world_components(item, rotation, x=0.0, y=0.0):
    out = []
    for c in item.components:
        ox, oy = rotate_coords(np.array([[c.dx, c.dy]]), rotation)[0]
        out.append(PlacedComponent(c.shape_id, c.copy, c.mirrored, (rotation + c.rotation) % 360.0, ox + x, oy + y))
    return tuple(out)


class Layout:
    """Placed items on the roll; cheap to copy for beam search."""

    def __init__(self, roll, placed=(), length_mm=None):
        self.roll = roll
        self.placed = list(placed)
        self.length_mm = float(length_mm) if length_mm is not None else roll.margin_mm

    def copy(self):
        return Layout(self.roll, self.placed, self.length_mm)

    @property
    def area_mm2(self):
        return sum(p.item.area_mm2 for p in self.placed)

    @property
    def fill(self):
        width = self.roll.fabric_width_mm
        return self.area_mm2 / (width * self.length_mm) if self.placed else 0.0

    @property
    def top_sum(self):
        return sum(p.bounds[3] for p in self.placed)

    def item_ids(self):
        return frozenset(p.item.id for p in self.placed)


PLACEMENT_RULES = ('bottom-left', 'left-bottom', 'compact')


class Placer:
    """rule: 'bottom-left' = (length, top, x); 'left-bottom' = (length, x, top);
    'compact' = (length, bounding-box area of everything placed, x)."""

    def __init__(self, shapes, roll, rule='bottom-left'):
        if rule not in PLACEMENT_RULES:
            raise ValueError(f'placement rule must be one of {PLACEMENT_RULES}')
        self.shapes = {s.id: s for s in shapes}
        self.roll = roll
        self.rule = rule
        self.cache = NfpCache(shapes, roll.gap_mm)

    def item_bounds(self, item, rotation):
        """True bounds of an item at a rotation, relative to the item origin."""
        b = np.array([np.inf, np.inf, -np.inf, -np.inf])
        for c in world_components(item, rotation):
            sb = self.shapes[c.shape_id].true_bounds(c.mirrored, c.rotation)
            b = [min(b[0], sb[0] + c.x), min(b[1], sb[1] + c.y), max(b[2], sb[2] + c.x), max(b[3], sb[3] + c.y)]
        return tuple(float(v) for v in b)

    def free_region(self, layout, item, rotation):
        bounds = self.item_bounds(item, rotation)
        region = ifp(bounds, self.roll.fabric_width_mm, self.roll.margin_mm, self.roll.max_length_mm)
        if region is None:
            return None, bounds
        blocked = []
        for placed in layout.placed:
            for p in placed.components:
                for n in world_components(item, rotation):
                    ex = self.cache.exclusion(p.shape_id, p.mirrored, p.rotation, n.shape_id, n.mirrored, n.rotation)
                    blocked.append(shapely.transform(ex, lambda c, dx=p.x - n.x, dy=p.y - n.y: c + np.array([dx, dy])))
        if blocked:
            region = region.difference(shapely.union_all(blocked))
        return region, bounds

    def best_position(self, layout, item, rotation):
        """Lowest (marker length, top, x) vertex of the free region, or None."""
        region, bounds = self.free_region(layout, item, rotation)
        if region is None or region.is_empty:
            return None
        coords = shapely.get_coordinates(region)
        if len(coords) == 0:
            return None
        top = coords[:, 1] + bounds[3]
        length = np.maximum(layout.length_mm, top + self.roll.margin_mm)
        if self.rule == 'left-bottom':
            order = np.lexsort((top, coords[:, 0], length))
        elif self.rule == 'compact' and layout.placed:
            b = np.array([p.bounds for p in layout.placed])
            x0 = np.minimum(b[:, 0].min(), coords[:, 0] + bounds[0])
            y0 = np.minimum(b[:, 1].min(), coords[:, 1] + bounds[1])
            x1 = np.maximum(b[:, 2].max(), coords[:, 0] + bounds[2])
            y1 = np.maximum(b[:, 3].max(), top)
            order = np.lexsort((coords[:, 0], top, (x1 - x0) * (y1 - y0), length))
        else:
            order = np.lexsort((coords[:, 0], top, length))
        i = order[0]
        return float(coords[i, 0]), float(coords[i, 1]), bounds, float(length[i])

    def place(self, layout, item, rotation):
        """Return a new layout with the item placed, or None if it does not fit."""
        found = self.best_position(layout, item, rotation)
        if found is None:
            return None
        x, y, bounds, length = found
        world_bounds = (bounds[0] + x, bounds[1] + y, bounds[2] + x, bounds[3] + y)
        placed = PlacedItem(item, rotation, x, y, world_bounds, world_components(item, rotation, x, y))
        out = layout.copy()
        out.placed.append(placed)
        out.length_mm = max(layout.length_mm, length)
        return out

    def decode(self, sequence, layout=None):
        """Place (item, rotation) pairs in order; None if any item cannot be placed."""
        layout = layout.copy() if layout is not None else Layout(self.roll)
        for item, rotation in sequence:
            layout = self.place(layout, item, rotation)
            if layout is None:
                return None
        return layout

    def compact(self, layout, rotations, passes=5):
        """Re-place items from the top down when that lowers their key; never lengthens the marker."""
        current = layout
        for _ in range(passes):
            improved = False
            for placed in sorted(current.placed, key=lambda p: (-p.bounds[3], p.item.id)):
                others = Layout(self.roll, [p for p in current.placed if p is not placed])
                others.length_mm = max([self.roll.margin_mm] + [p.bounds[3] + self.roll.margin_mm for p in others.placed])
                best, best_key = None, (current.length_mm, placed.bounds[3], placed.x)
                for rotation in rotations:
                    candidate = self.place(others, placed.item, rotation)
                    if candidate is None:
                        continue
                    new = candidate.placed[-1]
                    key = (candidate.length_mm, new.bounds[3], new.x)
                    if key < best_key:
                        best, best_key = candidate, key
                if best is not None:
                    current, improved = best, True
            if not improved:
                break
        return current


def world_polygons(shapes, layout):
    """True contours in world coordinates, one per placed component."""
    out = []
    for placed in layout.placed:
        for c in placed.components:
            out.append((c, transform_geometry(shapes[c.shape_id].true, c.mirrored, c.rotation, c.x, c.y)))
    return out


def verify(shapes, layout, tolerance_mm=0.05):
    """Independent check on the true contours: pairwise gap, roll containment, no duplicate copies."""
    roll = layout.roll
    polys = world_polygons(shapes, layout)
    issues, min_distance = [], float('inf')
    for i, (ci, pi) in enumerate(polys):
        for cj, pj in polys[i + 1:]:
            d = pi.distance(pj)
            min_distance = min(min_distance, d)
            if d < roll.gap_mm - tolerance_mm:
                issues.append(f'{ci.shape_id}#{ci.copy} and {cj.shape_id}#{cj.copy} are {d:.3f} mm apart')
    frame = box(roll.margin_mm, roll.margin_mm, roll.fabric_width_mm - roll.margin_mm,
                layout.length_mm - roll.margin_mm).buffer(1e-3)
    for c, p in polys:
        if not frame.covers(p):
            issues.append(f'{c.shape_id}#{c.copy} leaves the roll frame')
    copies = [(c.shape_id, c.copy) for c, _ in polys]
    if len(copies) != len(set(copies)):
        issues.append('duplicate copies placed')
    return issues, (min_distance if polys and len(polys) > 1 else None)
