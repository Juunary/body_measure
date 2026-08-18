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
    disposition: str = "accepted"      # accepted | manual_review | rejected
    gap_chord_mm: float = 0.0
    gap_ratio: float = 0.0


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


from ..validate.thresholds import (  # noqa: E402  (single source for tiers)
    GAP_ACCEPT_MAX_CHORD_MM,
    GAP_ACCEPT_MAX_RATIO,
    GAP_REVIEW_MAX_CHORD_MM,
    GAP_REVIEW_MAX_RATIO,
)

ACCEPTED = "accepted"
MANUAL_REVIEW = "manual_review"
REJECTED = "rejected"


def loop_gap(loop: SliceLoop) -> tuple[float, float]:
    """(chord_mm, gap_ratio) with gap_ratio = chord / (open_path + chord).
    (0, 0) for closed loops."""
    if loop.closed:
        return 0.0, 0.0
    open_len = float(np.linalg.norm(np.diff(loop.points, axis=0), axis=1).sum())
    chord = float(np.linalg.norm(loop.points[0] - loop.points[-1]))
    if open_len + chord <= 0:
        return chord, 1.0
    return chord, chord / (open_len + chord)


def gap_disposition(loop: SliceLoop) -> tuple[str, float, float]:
    """Tier a loop's hole for measurement: closed loops are accepted;
    open loops are accepted / manual_review / rejected by BOTH an absolute
    chord bound and a relative ratio bound (see thresholds.py). Structural
    prerequisites (single component, exactly two endpoints, degree <= 2)
    hold by construction of _chain_segments — anything else was never
    chained into a loop in the first place."""
    if loop.closed:
        return ACCEPTED, 0.0, 0.0
    chord, ratio = loop_gap(loop)
    if len(loop.points) < 3:
        return REJECTED, chord, ratio
    if chord <= GAP_ACCEPT_MAX_CHORD_MM and ratio <= GAP_ACCEPT_MAX_RATIO:
        return ACCEPTED, chord, ratio
    if chord <= GAP_REVIEW_MAX_CHORD_MM and ratio <= GAP_REVIEW_MAX_RATIO:
        return MANUAL_REVIEW, chord, ratio
    return REJECTED, chord, ratio


def _valid_polygon(loop: SliceLoop) -> Polygon | None:
    """Polygon for a closed loop or an auto-closed open loop. Containment
    is a CANDIDATE test only — whether an open candidate may actually be
    measured is decided afterwards by gap_disposition (identify first,
    judge second; never re-shop among other loops after a reject)."""
    if len(loop.points2d) < 3:
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


def _tiered_selection(loop: SliceLoop, method: str, confidence: float,
                      flags: list[str]) -> LoopSelection:
    disposition, chord, ratio = gap_disposition(loop)
    if not loop.closed:
        if disposition == ACCEPTED:
            flags = flags + ["gap_closed_degraded"]
        elif disposition == MANUAL_REVIEW:
            flags = flags + ["gap_closed_manual_review"]
            confidence = min(confidence, 0.3)
        else:
            flags = flags + ["gap_rejected"]
            confidence = 0.0
    return LoopSelection(
        loop=loop, method=method, confidence=confidence, quality_flags=flags,
        disposition=disposition, gap_chord_mm=chord, gap_ratio=ratio,
    )


def select_torso_loop(loops: list[SliceLoop], axis2d: np.ndarray) -> LoopSelection | None:
    """Identify the torso candidate FIRST (axis containment over closed and
    auto-closable open loops), THEN judge its hole via gap_disposition. A
    rejected torso candidate stays selected with disposition "rejected" —
    the search never falls back to some other closed loop, because that is
    exactly how a closed ARM loop once produced a wrist-sized waist on
    NOMO. Callers must map "rejected" to a null measurement."""
    candidates = [lp for lp in loops if len(lp.points) >= 3]
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

    if containing:
        loop, _ = max(containing, key=lambda pair: pair[1].area)
        extra = ["multiple_axis_containing_loops"] if len(containing) > 1 else []
        return _tiered_selection(
            loop, "axis_containment", 0.9 if loop.closed else 0.6, flags + extra
        )

    loop = min(candidates, key=lambda lp: float(np.linalg.norm(lp.centroid2d - axis2d)))
    return _tiered_selection(
        loop, "nearest_centroid", 0.4 if loop.closed else 0.3,
        flags + ["axis_not_inside_any_loop"],
    )
