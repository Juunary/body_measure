"""Scale pattern pieces by per-axis factors to study how size changes the marker.

A research simplification, not pattern grading: every outline point of a piece is scaled about
the local origin, so seam allowances scale with the piece. The local frame keeps its bounding-box
minimum at the origin and its grain line vertical.
"""
from .pieces import Piece


def scale_piece(piece: Piece, sx: float, sy: float) -> Piece:
    if sx <= 0 or sy <= 0:
        raise ValueError(f'{piece.id}: scale factors must be positive')

    def pts(points):
        return [[x * sx, y * sy] for x, y in points]

    graded = Piece(id=piece.id, quantity=piece.quantity, contour=pts(piece.contour),
                   seam_line=pts(piece.seam_line), grain_line=pts(piece.grain_line),
                   grain_angle_deg=piece.grain_angle_deg, flags=list(piece.flags),
                   marks=[{'kind': m['kind'], 'points': pts(m['points'])} for m in piece.marks])
    return graded.validate()


def grade(pieces, factors):
    """Scale each piece by factors[id] = (sx, sy); a missing id keeps its size."""
    unknown = set(factors) - {p.id for p in pieces}
    if unknown:
        raise ValueError(f'factors for unknown pieces: {sorted(unknown)}')
    return [scale_piece(p, *factors.get(p.id, (1.0, 1.0))) for p in pieces]
