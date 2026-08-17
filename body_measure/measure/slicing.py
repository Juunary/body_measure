"""Plane–mesh intersection and torso-loop selection.

Torso-loop selection priority (docs/decisions.md #4):
  1. closed loops whose 2D polygon contains the body-axis point;
  2. among those, the largest enclosed area;
  3. otherwise the loop whose centroid is nearest the axis (low confidence);
  4. nothing usable -> None (callers must report null, never force a number).
"Largest loop" alone is never a criterion — a bigger non-torso component
(equipment, another person, merged arms) would win. The two-cylinder test
in tests/test_slicing.py exists to catch that regression.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from trimesh.intersections import mesh_plane

_MERGE_EPS_MM = 1e-6


@dataclass
class SliceLoop:
    points: np.ndarray    # (n, 3) ordered, closed loops do NOT repeat the first point
    points2d: np.ndarray  # (n, 2) in the slice-plane basis
    closed: bool

    @property
    def centroid2d(self) -> np.ndarray:
        return self.points2d.mean(axis=0)


@dataclass
class LoopSelection:
    loop: SliceLoop
    method: str            # "axis_containment" | "nearest_centroid"
    confidence: float
    quality_flags: list[str] = field(default_factory=list)


def plane_basis(normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    normal = np.asarray(normal, dtype=np.float64)
    normal = normal / np.linalg.norm(normal)
    helper = np.array([1.0, 0.0, 0.0])
    if abs(normal @ helper) > 0.9:
        helper = np.array([0.0, 1.0, 0.0])
    u = np.cross(normal, helper)
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    return u, v


def _chain_segments(segments: np.ndarray) -> list[tuple[np.ndarray, bool]]:
    """Chain (n, 2, 3) intersection segments into ordered polylines.

    Endpoints are merged on a 1e-6 mm grid. Components where every node has
    degree <= 2 become one closed loop (Euler circuit) or one open polyline
    (Euler path); non-manifold junctions are skipped — better no number than
    a wrong one.
    """
    def key(p: np.ndarray) -> tuple[int, int, int]:
        return tuple(np.round(p / _MERGE_EPS_MM).astype(np.int64))

    graph = nx.Graph()
    for a, b in segments:
        ka, kb = key(a), key(b)
        if ka == kb:
            continue
        graph.add_node(ka, point=a)
        graph.add_node(kb, point=b)
        graph.add_edge(ka, kb)

    chains: list[tuple[np.ndarray, bool]] = []
    for component in nx.connected_components(graph):
        sub = graph.subgraph(component)
        degrees = [d for _, d in sub.degree()]
        if max(degrees) > 2:
            continue  # non-manifold junction in the cross-section
        endpoints = [n for n, d in sub.degree() if d == 1]
        closed = not endpoints
        start = endpoints[0] if endpoints else next(iter(component))
        ordered = [start]
        previous, current = None, start
        while True:
            neighbors = [n for n in sub.neighbors(current) if n != previous]
            if not neighbors:
                break
            previous, current = current, neighbors[0]
            if current == start:
                break
            ordered.append(current)
        points = np.array([sub.nodes[n]["point"] for n in ordered], dtype=np.float64)
        if (closed and len(points) >= 3) or (not closed and len(points) >= 2):
            chains.append((points, closed))
    return chains


def slice_mesh(mesh: trimesh.Trimesh, origin: np.ndarray, normal: np.ndarray) -> list[SliceLoop]:
    """Intersect the mesh with a plane; return ordered loops (closed or open)."""
    origin = np.asarray(origin, dtype=np.float64)
    segments = mesh_plane(mesh, plane_normal=normal, plane_origin=origin)
    if len(segments) == 0:
        return []
    u, v = plane_basis(normal)
    loops: list[SliceLoop] = []
    for pts, closed in _chain_segments(np.asarray(segments, dtype=np.float64)):
        rel = pts - origin
        points2d = np.column_stack([rel @ u, rel @ v])
        loops.append(SliceLoop(points=pts, points2d=points2d, closed=closed))
    return loops


MAX_GAP_RATIO = 0.2


def loop_gap_ratio(loop: SliceLoop) -> float:
    """Gap between endpoints relative to polyline length (0 for closed)."""
    if loop.closed:
        return 0.0
    length = float(np.linalg.norm(np.diff(loop.points, axis=0), axis=1).sum())
    if length <= 0:
        return np.inf
    return float(np.linalg.norm(loop.points[0] - loop.points[-1])) / length


def _valid_polygon(loop: SliceLoop) -> Polygon | None:
    """Polygon for a closed loop, or for an open loop whose endpoint gap is
    small enough to close (scan-hole tolerance — Polygon auto-closes)."""
    if len(loop.points2d) < 3:
        return None
    if not loop.closed and loop_gap_ratio(loop) > MAX_GAP_RATIO:
        return None
    poly = Polygon(loop.points2d)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or poly.area <= 0:
        return None
    return poly


def project_axis_to_plane(axis_point_xz: np.ndarray, origin: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Project the vertical body-axis line (given as world x,z) into the
    slice-plane basis. Assumes the canonical Y-up frame, i.e. the axis is the
    vertical line {(x, t, z)}; its intersection with the plane is projected."""
    u, v = plane_basis(normal)
    origin = np.asarray(origin, dtype=np.float64)
    normal = np.asarray(normal, dtype=np.float64) / np.linalg.norm(normal)
    line_point = np.array([axis_point_xz[0], 0.0, axis_point_xz[1]])
    line_dir = np.array([0.0, 1.0, 0.0])
    denom = normal @ line_dir
    if abs(denom) < 1e-12:
        rel = line_point - origin
    else:
        t = ((origin - line_point) @ normal) / denom
        rel = line_point + t * line_dir - origin
    return np.array([rel @ u, rel @ v])


def select_torso_loop(loops: list[SliceLoop], axis2d: np.ndarray) -> LoopSelection | None:
    """Closed loops plus nearly-closed open loops (scan holes, gap <=
    MAX_GAP_RATIO) are candidates — a torso slice crossing a hole must not
    lose to a closed ARM loop (seen on NOMO: waist came out wrist-sized).
    Selecting a gap-closed loop is flagged `gap_closed_open_loop`."""
    candidates = [
        lp for lp in loops
        if lp.closed or (len(lp.points) >= 3 and loop_gap_ratio(lp) <= MAX_GAP_RATIO)
    ]
    if not candidates:
        return None
    axis = Point(axis2d)

    containing: list[tuple[SliceLoop, Polygon]] = []
    for lp in candidates:
        poly = _valid_polygon(lp)
        if poly is not None and poly.contains(axis):
            containing.append((lp, poly))

    flags = []
    if any(not lp.closed for lp in loops):
        flags.append("open_loops_present")

    def selection_flags(loop: SliceLoop, extra: list[str]) -> list[str]:
        gap = [] if loop.closed else ["gap_closed_open_loop"]
        return flags + extra + gap

    if containing:
        loop, _ = max(containing, key=lambda pair: pair[1].area)
        extra = ["multiple_axis_containing_loops"] if len(containing) > 1 else []
        return LoopSelection(
            loop=loop,
            method="axis_containment",
            confidence=0.9 if loop.closed else 0.6,
            quality_flags=selection_flags(loop, extra),
        )

    loop = min(candidates, key=lambda lp: float(np.linalg.norm(lp.centroid2d - axis2d)))
    return LoopSelection(
        loop=loop,
        method="nearest_centroid",
        confidence=0.4 if loop.closed else 0.3,
        quality_flags=selection_flags(loop, ["axis_not_inside_any_loop"]),
    )
