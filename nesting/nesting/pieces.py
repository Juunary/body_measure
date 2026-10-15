"""Piece and placement records: the study's data contract, not a CAD exchange format.

Units are millimetres, y up. A piece's local frame has its grain line along +y
and its bounding-box minimum at the origin. A placement is the composition
mirror (x -> -x) -> rotation about the local origin -> translation, in that
order, so the same three numbers reproduce every output contour.
"""
from dataclasses import dataclass, field
import json
import math
from pathlib import Path

from shapely.geometry import Polygon

FIELD_ORDER = ('id', 'quantity', 'flags', 'grain_angle_deg', 'contour', 'seam_line',
               'grain_line', 'marks', 'area_mm2', 'width_mm', 'height_mm')


@dataclass
class Piece:
    id: str
    quantity: int
    contour: list                      # cut line with seam allowance, CCW ring, no repeated end point
    seam_line: list                    # net line, same convention
    grain_line: list                   # [[x0, y0], [x1, y1]] in the local frame (vertical)
    grain_angle_deg: float             # grain direction in the source page frame, 0 = +x, 90 = +y
    flags: list = field(default_factory=list)
    marks: list = field(default_factory=list)   # [{'kind': notch|fold|centre, 'points': [[x, y], ...]}]

    @property
    def polygon(self):
        return Polygon(self.contour)

    @property
    def area_mm2(self):
        return float(self.polygon.area)

    @property
    def bounds(self):
        return self.polygon.bounds

    @property
    def width_mm(self):
        b = self.bounds
        return float(b[2] - b[0])

    @property
    def height_mm(self):
        b = self.bounds
        return float(b[3] - b[1])

    def to_dict(self):
        return {'id': self.id, 'quantity': self.quantity, 'flags': list(self.flags),
                'grain_angle_deg': self.grain_angle_deg,
                'contour': _round(self.contour), 'seam_line': _round(self.seam_line),
                'grain_line': _round(self.grain_line),
                'marks': [{'kind': m['kind'], 'points': _round(m['points'])} for m in self.marks],
                'area_mm2': round(self.area_mm2, 3), 'width_mm': round(self.width_mm, 3),
                'height_mm': round(self.height_mm, 3)}

    @classmethod
    def from_dict(cls, d):
        piece = cls(id=d['id'], quantity=int(d['quantity']), contour=d['contour'],
                    seam_line=d['seam_line'], grain_line=d['grain_line'],
                    grain_angle_deg=float(d['grain_angle_deg']), flags=list(d.get('flags', [])),
                    marks=[{'kind': m['kind'], 'points': m['points']} for m in d.get('marks', [])])
        piece.validate()
        return piece

    def validate(self):
        p = self.polygon
        if not p.is_valid or p.area <= 1:
            raise ValueError(f'{self.id}: cut contour is not a valid polygon')
        if self.quantity < 1:
            raise ValueError(f'{self.id}: quantity must be positive')
        if len(self.grain_line) != 2:
            raise ValueError(f'{self.id}: grain line needs two points')
        (x0, y0), (x1, y1) = self.grain_line
        if abs(x1 - x0) > 1e-6 * max(1.0, abs(y1 - y0)):
            raise ValueError(f'{self.id}: grain line is not vertical in the local frame')
        return self


def _round(points, digits=4):
    return [[round(float(x), digits), round(float(y), digits)] for x, y in points]


def rotate_points(points, degrees, origin=(0.0, 0.0)):
    """Rotate CCW about origin. Multiples of 90 are exact (no cos(90) residue)."""
    ox, oy = origin
    quarter = degrees / 90.0
    if abs(quarter - round(quarter)) < 1e-12:
        q = int(round(quarter)) % 4
        if q == 0:
            return [[float(x), float(y)] for x, y in points]
        if q == 1:
            return [[ox - (y - oy), oy + (x - ox)] for x, y in points]
        if q == 2:
            return [[ox - (x - ox), oy - (y - oy)] for x, y in points]
        return [[ox + (y - oy), oy - (x - ox)] for x, y in points]
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return [[ox + c * (x - ox) - s * (y - oy), oy + s * (x - ox) + c * (y - oy)] for x, y in points]


def transform_points(points, mirrored, rotation_deg, tx, ty):
    """mirror (x -> -x) -> rotate about the local origin -> translate."""
    pts = [[-x, y] for x, y in points] if mirrored else [[float(x), float(y)] for x, y in points]
    pts = rotate_points(pts, rotation_deg)
    return [[x + tx, y + ty] for x, y in pts]


def transform_marks(marks, mirrored, rotation_deg, tx, ty):
    return [{'kind': m['kind'], 'points': transform_points(m['points'], mirrored, rotation_deg, tx, ty)}
            for m in marks]


def save_pieces(path, meta, pieces):
    document = {'source': meta, 'pieces': [p.to_dict() for p in pieces]}
    Path(path).write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding='utf-8')
    return document


def load_pieces(path):
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    pieces = [Piece.from_dict(d) for d in document['pieces']]
    ids = [p.id for p in pieces]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate piece ids')
    return document.get('source', {}), pieces
