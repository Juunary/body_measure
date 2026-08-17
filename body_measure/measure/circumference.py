"""Circumference of a slice loop.

Both values are always reported (docs/decisions.md #3):
- raw_contour_mm: perimeter of the intersection polyline itself;
- taut_tape_hull_mm: perimeter of the 2D convex hull — a taut tape bridges
  concavities, so for a simple closed contour hull <= raw always holds.
Which one matches a real tape per measurement is undecided until the
scanner arrives and manual comparisons exist; selection_method is
provisional and recorded in the output.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import MultiPoint, Polygon, box

from .slicing import SliceLoop

PROVISIONAL_SELECTION = "convex_hull"


@dataclass
class CircumferenceResult:
    raw_contour_mm: float | None
    taut_tape_hull_mm: float | None
    selected_value_mm: float | None
    selection_method: str | None
    quality_flags: list[str] = field(default_factory=list)


def polyline_length(points: np.ndarray, *, closed: bool) -> float:
    diffs = np.diff(points, axis=0)
    length = float(np.linalg.norm(diffs, axis=1).sum())
    if closed:
        length += float(np.linalg.norm(points[0] - points[-1]))
    return length


def hull_perimeter(points2d: np.ndarray) -> float | None:
    hull = MultiPoint([tuple(p) for p in points2d]).convex_hull
    if hull.geom_type != "Polygon":
        return None  # degenerate (collinear points)
    return float(hull.exterior.length)


def clipped_circumference_xz(
    points_xz: np.ndarray,
    lo: float,
    hi: float,
    lateral: np.ndarray | None = None,
) -> CircumferenceResult:
    """Tape approximation for a merged torso+arms cross-section: clip the
    closed contour (x/z coordinates of a horizontal slice) to the torso's
    extent [lo, hi] measured ALONG the body's lateral axis (taken at the
    armpit level), keep the largest central piece, and measure its
    perimeter — the straight cut edges stand in for the tape bridging the
    armpits. The lateral axis comes from slice PCA, not world x: a scanner
    may deliver the subject at any yaw. Flagged
    `arm_clipped_at_merged_level` so the approximation is visible."""
    points_xz = np.asarray(points_xz, dtype=np.float64)
    if lateral is not None:
        lateral = np.asarray(lateral, dtype=np.float64)
        ortho = np.array([-lateral[1], lateral[0]])
        points_xz = np.column_stack([points_xz @ lateral, points_xz @ ortho])
    poly = Polygon(points_xz)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty:
        return CircumferenceResult(None, None, None, None, ["degenerate_merged_loop"])
    clipped = poly.intersection(box(lo, -1e9, hi, 1e9))
    if clipped.is_empty:
        return CircumferenceResult(None, None, None, None, ["clip_removed_everything"])
    if clipped.geom_type == "MultiPolygon":
        clipped = max(clipped.geoms, key=lambda g: g.area)
    if clipped.geom_type != "Polygon":
        return CircumferenceResult(None, None, None, None, ["degenerate_merged_loop"])
    raw = float(clipped.exterior.length)
    hull = float(clipped.convex_hull.exterior.length)
    return CircumferenceResult(
        raw_contour_mm=raw,
        taut_tape_hull_mm=hull,
        selected_value_mm=hull,
        selection_method=PROVISIONAL_SELECTION,
        quality_flags=["arm_clipped_at_merged_level"],
    )


def measure_circumference(loop: SliceLoop, *, close_gap: bool = False) -> CircumferenceResult:
    if not loop.closed:
        from .slicing import MAX_GAP_RATIO, loop_gap_ratio

        if not (close_gap and loop_gap_ratio(loop) <= MAX_GAP_RATIO):
            return CircumferenceResult(
                raw_contour_mm=polyline_length(loop.points, closed=False),
                taut_tape_hull_mm=None,
                selected_value_mm=None,
                selection_method=None,
                quality_flags=["open_loop"],
            )
        # scan hole: the closing chord stands in for the tape crossing it
        raw = polyline_length(loop.points, closed=True)
        hull = hull_perimeter(loop.points2d)
        if hull is None:
            return CircumferenceResult(raw, None, None, None, ["degenerate_hull"])
        return CircumferenceResult(raw, hull, hull, PROVISIONAL_SELECTION, ["gap_closed_open_loop"])
    raw = polyline_length(loop.points, closed=True)
    hull = hull_perimeter(loop.points2d)
    if hull is None:
        return CircumferenceResult(
            raw_contour_mm=raw,
            taut_tape_hull_mm=None,
            selected_value_mm=None,
            selection_method=None,
            quality_flags=["degenerate_hull"],
        )
    return CircumferenceResult(
        raw_contour_mm=raw,
        taut_tape_hull_mm=hull,
        selected_value_mm=hull,
        selection_method=PROVISIONAL_SELECTION,
        quality_flags=[],
    )
