"""One evaluator for every nester: rebuild the true cut lines and measure the marker.

A tool result is a mapping copy key -> (rotation_deg, tx, ty) in the tool frame,
meaning P = R(r) Q + t for the tool polygon Q of that copy. The result is moved
into the study frame, pushed against the roll start and one selvedge (a pure
translation of the whole marker), and checked on the original contours: every
copy once, allowed rotations only, pairwise gap, fit across the roll.
Length = extent along the roll + 2 x margin, the same definition the study uses.
"""
import math

import numpy as np
from shapely import STRtree
from shapely.geometry import Polygon

from nesting.pieces import transform_marks, transform_points

from .instance import MODES

GAP_TOLERANCE_MM = 0.1      # cutting precision; also absorbs the tools' arc approximations
FIT_TOLERANCE_MM = 0.1


def snap_rotation(r):
    r = float(r) % 360.0
    q = round(r / 90.0) * 90.0
    return (q % 360.0) if abs(r - q) < 1e-3 else r


def to_study(inst, key, rotation_deg, tx, ty):
    """(rotation, mirrored, X, Y) of a copy in the study frame for a tool placement."""
    c = inst.copy(key)
    return snap_rotation(rotation_deg), c.mirrored, inst.fabric_width_mm - ty, tx


def _placed(inst, placements):
    out = {}
    for key, (r, tx, ty) in placements.items():
        c = inst.copy(key)
        rot, mirrored, X, Y = to_study(inst, key, r, tx, ty)
        contour = np.asarray(transform_points(inst.pieces[c.piece_id].contour, mirrored, rot, X, Y))
        out[key] = (rot, mirrored, X, Y, contour)
    return out


def length_only(inst, placements):
    """Marker length from bounding boxes only (fast, for convergence traces)."""
    placed = _placed(inst, placements)
    ys = np.concatenate([p[4][:, 1] for p in placed.values()])
    return float(ys.max() - ys.min() + 2 * inst.margin_mm)


def evaluate(inst, placements, mode):
    issues = []
    keys = {c.key for c in inst.copies}
    missing, extra = keys - set(placements), set(placements) - keys
    if missing:
        issues.append('missing copies: ' + ', '.join(sorted(missing)))
    if extra:
        issues.append('unknown copies: ' + ', '.join(sorted(extra)))
    placed = _placed(inst, {k: v for k, v in placements.items() if k in keys})
    allowed = MODES[mode]
    for key, (rot, *_rest) in placed.items():
        if not any(abs(rot - a) < 1e-3 for a in allowed):
            issues.append(f'{key}: rotation {rot:g} is not allowed in mode {mode}')
    pts = np.concatenate([p[4] for p in placed.values()])
    sx, sy = inst.margin_mm - pts[:, 0].min(), inst.margin_mm - pts[:, 1].min()
    width_used = float(pts[:, 0].max() - pts[:, 0].min() + 2 * inst.margin_mm)
    length = float(pts[:, 1].max() - pts[:, 1].min() + 2 * inst.margin_mm)
    if width_used > inst.fabric_width_mm + FIT_TOLERANCE_MM:
        issues.append(f'marker is {width_used:.2f} mm wide on a {inst.fabric_width_mm:g} mm roll')
    polys = {k: Polygon(p[4] + [sx, sy]) for k, p in placed.items()}
    order = sorted(polys)
    tree = STRtree([polys[k] for k in order])
    min_distance = math.inf
    for i, k in enumerate(order):
        near = tree.query(polys[k].buffer(inst.gap_mm + 1.0))
        for j in near:
            if j <= i:
                continue
            d = polys[k].distance(polys[order[j]])
            min_distance = min(min_distance, d)
            if d < inst.gap_mm - GAP_TOLERANCE_MM:
                issues.append(f'{k} and {order[j]} are {d:.2f} mm apart')
    if min_distance is math.inf:        # nothing within reach: report the true minimum
        min_distance = min(polys[a].distance(polys[b]) for i, a in enumerate(order) for b in order[i + 1:])
    area = inst.total_area_mm2
    marker = []
    for key in order:
        c = inst.copy(key)
        piece = inst.pieces[c.piece_id]
        rot, mirrored, X, Y, _ = placed[key]
        X, Y = X + sx, Y + sy
        marker.append({
            'piece_id': c.piece_id, 'copy': c.copy, 'rotation_deg': rot, 'mirrored': mirrored,
            'x_mm': round(X, 4), 'y_mm': round(Y, 4),
            'contour': _round(transform_points(piece.contour, mirrored, rot, X, Y)),
            'seam_line': _round(transform_points(piece.seam_line, mirrored, rot, X, Y)),
            'grain_line': _round(transform_points(piece.grain_line, mirrored, rot, X, Y)),
            'marks': [{'kind': m['kind'], 'points': _round(m['points'])}
                      for m in transform_marks(piece.marks, mirrored, rot, X, Y)],
        })
    return {
        'valid': not issues, 'issues': issues,
        'length_mm': round(length, 2), 'width_used_mm': round(width_used, 2),
        'efficiency_pct': round(100.0 * area / (inst.fabric_width_mm * length), 2),
        'min_distance_mm': round(float(min_distance), 3),
        'placements': marker,
    }


def marker_document(inst, evaluation, mode, title):
    """A result dict in the study's marker format, so nesting.marker renders every tool alike."""
    return {
        'title': title,
        'settings': {'fabric_width_mm': inst.fabric_width_mm, 'gap_mm': inst.gap_mm,
                     'edge_margin_mm': inst.margin_mm, 'rotations': list(MODES[mode])},
        'totals': {'fabric_width_mm': inst.fabric_width_mm, 'length_mm': evaluation['length_mm'],
                   'efficiency_pct': evaluation['efficiency_pct'], 'min_distance_mm': evaluation['min_distance_mm']},
        'placements': evaluation['placements'],
    }


def _round(points, digits=3):
    return [[round(float(x), digits), round(float(y), digits)] for x, y in points]
