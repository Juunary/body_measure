"""Polygon preparation and no-fit polygons (NFP) for the nesting study.

Research geometry for a handful of garment pieces, not a general-purpose
packing library. NFPs are exact Minkowski sums of convex parts (ear-clipping
triangulation merged Hertel-Mehlhorn style); the cutting gap is applied once,
as a round buffer of the raw NFP, which equals inflating both parts by half
the gap. Orientation is mirror (x -> -x) then rotation about the local origin,
never re-centred, so NFP(T A, T B) = T NFP(A, B) holds for every orientation.
"""
import math

import mapbox_earcut
import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient

SIMPLIFY_TOL_MM = 0.25      # collision contour tolerance; the NFP buffer pays it back twice
PRECISION_MM = 0.01         # grid for robust overlay of convex parts
INSCRIBED_SLACK_MM = 0.05   # round buffers are inscribed polygons; keep the true gap >= gap
EROSION_MM = 0.02           # keep exact-fit corridors from collapsing to zero area
BUFFER_QUAD_SEGS = 8


def exclusion_radius(gap_mm, tol=SIMPLIFY_TOL_MM):
    """Buffer radius turning a raw NFP into the region where the true contours are closer than gap."""
    return gap_mm + 2 * tol + INSCRIBED_SLACK_MM - EROSION_MM


def collision_polygon(contour, tol=SIMPLIFY_TOL_MM):
    poly = Polygon(contour).simplify(tol, preserve_topology=True)
    if poly.geom_type != 'Polygon' or not poly.is_valid or poly.area <= 0:
        raise ValueError('contour does not simplify to one valid polygon')
    return orient(poly, 1.0)


def rotate_coords(coords, degrees):
    """Rotate an (n, 2) array CCW about the origin; multiples of 90 are exact."""
    c = np.asarray(coords, dtype=float)
    quarter = degrees / 90.0
    if abs(quarter - round(quarter)) < 1e-12:
        q = int(round(quarter)) % 4
        if q == 0:
            return c.copy()
        if q == 1:
            return np.column_stack([-c[:, 1], c[:, 0]])
        if q == 2:
            return -c
        return np.column_stack([c[:, 1], -c[:, 0]])
    cs, sn = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return np.column_stack([cs * c[:, 0] - sn * c[:, 1], sn * c[:, 0] + cs * c[:, 1]])


def orient_coords(coords, mirrored, degrees):
    c = np.asarray(coords, dtype=float)
    if mirrored:
        c = np.column_stack([-c[:, 0], c[:, 1]])
    return rotate_coords(c, degrees)


def transform_geometry(geom, mirrored=False, degrees=0.0, dx=0.0, dy=0.0):
    """mirror -> rotate about the origin -> translate, applied to any shapely geometry."""
    def f(c):
        out = orient_coords(c, mirrored, degrees)
        return out + np.array([dx, dy]) if (dx or dy) else out
    return shapely.transform(geom, f)


def oriented_polygon(poly, mirrored, degrees):
    out = transform_geometry(poly, mirrored, degrees)
    return orient(out, 1.0) if out.geom_type == 'Polygon' else MultiPolygon([orient(p, 1.0) for p in out.geoms])


def reflex_count(poly):
    ring = np.asarray(orient(poly, 1.0).exterior.coords)[:-1]
    prev, nxt = np.roll(ring, 1, axis=0), np.roll(ring, -1, axis=0)
    cross = (ring[:, 0] - prev[:, 0]) * (nxt[:, 1] - ring[:, 1]) - (ring[:, 1] - prev[:, 1]) * (nxt[:, 0] - ring[:, 0])
    return int(np.sum(cross < -1e-9))


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _convex_at(ring, verts, index, eps=1e-9):
    n = len(ring)
    o = verts[ring[index]]
    a = verts[ring[index - 1]]
    b = verts[ring[(index + 1) % n]]
    return _cross(a, o, b) >= -eps


def convex_parts(poly):
    """Convex decomposition of a polygon (or multipolygon) as a list of CCW (k, 2) arrays."""
    if poly.geom_type == 'MultiPolygon':
        return [part for p in poly.geoms for part in convex_parts(p)]
    poly = orient(poly, 1.0)
    verts = np.asarray(poly.exterior.coords, dtype=np.float64)[:-1]
    holes = [np.asarray(h.coords, dtype=np.float64)[:-1] for h in poly.interiors]
    if holes:
        raise ValueError('convex_parts: holes are not supported')
    tris = mapbox_earcut.triangulate_float64(verts, np.array([len(verts)], dtype=np.uint32)).reshape(-1, 3)
    rings = {}
    for t, (a, b, c) in enumerate(tris):
        area2 = _cross(verts[a], verts[b], verts[c])
        if abs(area2) < 1e-9:
            continue
        rings[t] = [int(a), int(b), int(c)] if area2 > 0 else [int(a), int(c), int(b)]
    owners = {}
    for t, ring in rings.items():
        for i in range(3):
            edge = tuple(sorted((ring[i], ring[(i + 1) % 3])))
            owners.setdefault(edge, []).append(t)
    parent = {t: t for t in rings}

    def find(t):
        while parent[t] != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t

    for (a, b), ids in owners.items():
        if len(ids) != 2:
            continue
        p, q = find(ids[0]), find(ids[1])
        if p == q:
            continue
        rp, rq = rings[p], rings[q]
        ip = next((i for i in range(len(rp)) if rp[i] == a and rp[(i + 1) % len(rp)] == b), None)
        if ip is None:            # p traverses b -> a; swap roles
            p, q, rp, rq = q, p, rq, rp
            ip = next(i for i in range(len(rp)) if rp[i] == a and rp[(i + 1) % len(rp)] == b)
        iq = next(i for i in range(len(rq)) if rq[i] == b and rq[(i + 1) % len(rq)] == a)
        # rp: ... a b ... ; rq: ... b a ...
        rp_from_b = rp[ip + 1:] + rp[:ip + 1]      # starts at b, ends at a
        rq_from_a = rq[iq + 1:] + rq[:iq + 1]      # starts at a, ends at b
        merged = rp_from_b + rq_from_a[1:-1]
        ia = len(rp_from_b) - 1
        if _convex_at(merged, verts, ia) and _convex_at(merged, verts, 0):
            rings[p] = merged
            parent[q] = p
            del rings[q]
    return [verts[ring] for ring in rings.values()]


def _hulls_of_sums(parts_a, parts_b):
    """Convex hull of A_i + B_j for every pair, in one vectorised shapely call."""
    coords, indices, k = [], [], 0
    for pa in parts_a:
        for pb in parts_b:
            s = (pa[:, None, :] + pb[None, :, :]).reshape(-1, 2)
            coords.append(s)
            indices.append(np.full(len(s), k))
            k += 1
    pts = shapely.points(np.concatenate(coords))
    return shapely.convex_hull(shapely.multipoints(pts, indices=np.concatenate(indices)))


def nfp_raw(parts_a, parts_b):
    """A (+) (-B): translations of B's origin at which B overlaps or touches A."""
    hulls = _hulls_of_sums(parts_a, [-pb for pb in parts_b])
    region = shapely.union_all(shapely.set_precision(hulls, PRECISION_MM))
    if not region.is_valid:
        region = shapely.make_valid(region)
    return region


def ifp(true_bounds, fabric_width_mm, margin_mm, max_length_mm):
    """Translations keeping an oriented contour with these bounds inside the roll."""
    bx0, by0, bx1, by1 = true_bounds
    x0, x1 = margin_mm - bx0, fabric_width_mm - margin_mm - bx1
    y0, y1 = margin_mm - by0, max_length_mm - margin_mm - by1
    if x1 < x0 - 1e-9 or y1 < y0 - 1e-9:
        return None
    return box(x0, y0, x1, y1)


class Shape:
    """One pattern shape prepared for nesting: collision polygon and convex parts."""

    def __init__(self, piece, tol=SIMPLIFY_TOL_MM):
        self.id = piece.id
        self.area_mm2 = piece.area_mm2
        self.true = Polygon(piece.contour)
        self.collision = collision_polygon(piece.contour, tol)
        self.parts = convex_parts(self.collision)
        self._bounds = {}

    def true_bounds(self, mirrored, degrees):
        key = (bool(mirrored), float(degrees))
        if key not in self._bounds:
            self._bounds[key] = transform_geometry(self.true, mirrored, degrees).bounds
        return self._bounds[key]


class NfpCache:
    """Exclusion regions per ordered pair of oriented shapes, derived from 8 base NFPs per shape pair.

    exclusion(A, mA, tA, B, mB, tB) = translations of B's origin, relative to A's origin,
    at which the true contours would come closer than the gap.
    """

    def __init__(self, shapes, gap_mm):
        self.shapes = {s.id: s for s in shapes}
        self.radius = exclusion_radius(gap_mm)
        self._base = {}
        self._derived = {}
        self.computed = 0

    def _base_nfp(self, a, b, mb, delta):
        """NFP(A@(0,0), B@(mb, delta)) buffered.

        Halves the work with NFP(A@0, B@(m, d)) = -(R_d M^m) NFP(B@0, A@(m, d')),
        d' = -d for m = 0 and d' = d for m = 1 (point reflection of the reverse pair).
        """
        delta %= 360.0
        key = (a, b, mb, delta)
        if key in self._base:
            return self._base[key]
        reverse = (b, a, mb, ((-delta) if mb == 0 else delta) % 360.0)
        if reverse in self._base:
            region = shapely.transform(transform_geometry(self._base[reverse], bool(mb), delta), lambda c: -c)
        else:
            parts_b = [orient_coords(p, mb, delta) for p in self.shapes[b].parts]
            raw = nfp_raw(self.shapes[a].parts, parts_b)
            region = raw.buffer(self.radius, quad_segs=BUFFER_QUAD_SEGS, join_style='round')
            self.computed += 1
        self._base[key] = region
        return region

    def exclusion(self, a, ma, ta, b, mb, tb):
        key = (a, bool(ma), ta % 360.0, b, bool(mb), tb % 360.0)
        if key in self._derived:
            return self._derived[key]
        delta = (tb - ta) % 360.0
        if ma:
            rel_m, rel_t = (not mb), (-delta) % 360.0
        else:
            rel_m, rel_t = bool(mb), delta
        base = self._base_nfp(a, b, int(rel_m), rel_t)
        region = transform_geometry(base, bool(ma), ta % 360.0)
        self._derived[key] = region
        return region
