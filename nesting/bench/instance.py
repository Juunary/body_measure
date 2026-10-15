"""Benchmark instance: the nine shirt copies, prepared once for every nester.

Every tool packs the same polygons: each cut line simplified with 0.25 mm
tolerance and grown back by the same amount with mitre joins, so the polygon a
tool packs always contains the true cut line. Copy 2 of a 2x piece is
pre-mirrored (single-ply left/right pairs) because the external tools cannot
mirror parts. Tool frame: x along the roll (the length being minimised), y
across it, grain along +x. Study frame (nesting.pieces): x across, y along,
grain along +y. A tool placement P = R(r) Q + t of the tool polygon Q maps to
the study frame as rotation r, translation (width - t_y, t_x).
"""
from dataclasses import dataclass, field
import json
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from nesting.pieces import load_pieces
from nesting.polygons import orient_coords

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PIECES = ROOT / 'out' / 'pieces.json'
SIMPLIFY_MM = 0.25
MODES = {'4rot': (0.0, 90.0, 180.0, 270.0), '2rot': (0.0, 180.0)}
MODE_LABELS = {'4rot': 'grain parallel or perpendicular (0/90/180/270)', '2rot': 'grain parallel only (0/180)'}
# Markers are cut on the Bullmer PremiumCut 1620 CV installed at ITA (offer 0912241527): rolls up to
# 1600 mm wide and a 2000 mm cutting zone on a conveyor, so a longer marker is cut in several windows.
CUTTING_ZONE_MM = 2000.0
# Grain rule the benchmark runs by default, the study's rule since 2026-10-01: every grain line along or
# across the roll, never tilted (90/270 cut a piece cross-grain). `--rules 2rot` keeps them all along.
DEFAULT_RULES = ('4rot',)
# Roll setups: the pattern PDF's 1007 mm plot width, and the cutter's full working width. Each keeps
# its runs under out/bench/<folder>/ and its report in docs/<doc>.md.
SPECS = {
    'roll1007': {'fabric_width_mm': 1007.0, 'folder': '', 'doc': 'benchmark',
                 'roll': 'the plot width of the pattern PDF'},
    'bullmer1600': {'fabric_width_mm': 1600.0, 'folder': 'bullmer1600', 'doc': 'benchmark-bullmer1600',
                    'roll': "the cutter's full working width"},
}


@dataclass
class Copy:
    key: str              # 'VORDERTEIL-2'
    piece_id: str
    copy: int
    mirrored: bool
    tool: np.ndarray      # conservative polygon in the tool frame, CCW, open ring
    area_mm2: float       # true cut-line area

    @property
    def tool_bounds(self):
        return (float(self.tool[:, 0].min()), float(self.tool[:, 1].min()),
                float(self.tool[:, 0].max()), float(self.tool[:, 1].max()))


@dataclass
class Instance:
    pieces: dict                          # piece id -> nesting.pieces.Piece
    copies: list = field(default_factory=list)
    fabric_width_mm: float = 1007.0
    gap_mm: float = 5.0
    margin_mm: float = 5.0
    spec: str = 'roll1007'

    @property
    def total_area_mm2(self):
        return sum(c.area_mm2 for c in self.copies)

    def copy(self, key):
        return next(c for c in self.copies if c.key == key)


def conservative_polygon(contour, tolerance=SIMPLIFY_MM):
    """Simplified cut line grown by the simplification tolerance: always contains the true line."""
    true = Polygon(contour)
    simple = true.simplify(tolerance, preserve_topology=True)
    grown = simple.buffer(tolerance + 0.01, join_style='mitre', mitre_limit=2.0)
    if grown.geom_type != 'Polygon' or not grown.covers(true):
        raise ValueError('conservative polygon does not contain the cut line')
    return orient(grown, 1.0)


def build(pieces_path=DEFAULT_PIECES, fabric_width_mm=1007.0, gap_mm=5.0, margin_mm=5.0):
    _, pieces = load_pieces(pieces_path)
    return build_pieces(pieces, fabric_width_mm, gap_mm, margin_mm)


def build_pieces(pieces, fabric_width_mm=1007.0, gap_mm=5.0, margin_mm=5.0):
    """The instance of an already loaded (or graded) list of pieces."""
    inst = Instance({p.id: p for p in pieces}, [], fabric_width_mm, gap_mm, margin_mm)
    for piece in pieces:
        grown = conservative_polygon(piece.contour)
        ring = np.asarray(grown.exterior.coords)[:-1]
        for copy in range(1, piece.quantity + 1):
            mirrored = piece.quantity == 2 and copy == 2
            tool = orient_coords(ring, mirrored, -90.0)
            tool = np.asarray(orient(Polygon(tool), 1.0).exterior.coords)[:-1]
            inst.copies.append(Copy(f'{piece.id}-{copy}', piece.id, copy, mirrored, tool, piece.area_mm2))
    return inst


def build_spec(spec, pieces_path=DEFAULT_PIECES):
    """The instance on one roll setup of SPECS."""
    inst = build(pieces_path, SPECS[spec]['fabric_width_mm'])
    inst.spec = spec
    return inst


def _layout(inst, top, spacing=30.0, row_width=None):
    """Offsets placing every tool polygon side by side below `top`, without overlaps."""
    row_width = row_width or 2 * inst.fabric_width_mm
    offsets, x, y, row_h = {}, 0.0, top, 0.0
    for c in inst.copies:
        bx0, by0, bx1, by1 = c.tool_bounds
        if x > 0 and x + (bx1 - bx0) > row_width:
            x, y, row_h = 0.0, y + row_h + spacing, 0.0
        offsets[c.key] = (x - bx0, y - by0)
        x += (bx1 - bx0) + spacing
        row_h = max(row_h, by1 - by0)
    return offsets, y + row_h


def _polygon(c, offset, digits=4):
    dx, dy = offset
    pts = ' '.join(f'{x + dx:.{digits}f},{y + dy:.{digits}f}' for x, y in c.tool)
    return f'<polygon id="{c.key}" points="{pts}"/>'


def svgnest_svg(inst, bin_length_mm):
    """One SVG: a bin rectangle `bin` (length x fabric width) and the nine parts below it. Units: mm."""
    offsets, bottom = _layout(inst, inst.fabric_width_mm + 50.0)
    width, height = max(bin_length_mm, 2 * inst.fabric_width_mm), bottom + 10.0
    body = ''.join(_polygon(c, offsets[c.key]) for c in inst.copies)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" '
           f'width="{width:.1f}" height="{height:.1f}">'
           f'<rect id="bin" x="0" y="0" width="{bin_length_mm:.1f}" height="{inst.fabric_width_mm:.1f}"/>{body}</svg>')
    return svg, offsets


def deepnest_svgs(inst, bin_length_mm, units_per_mm):
    """Parts SVG in mm (Deepnest scales it to its own units on import) and a sheet SVG built the
    way Deepnest's "add sheet" dialog builds one: a bare rectangle already in Deepnest units.
    Deepnest 1.5.6 does not shrink the sheet by half the spacing, so the sheet is
    (fabric width - gap) wide to keep the full margin to the selvedges."""
    offsets, bottom = _layout(inst, 0.0)
    width, height = 2 * inst.fabric_width_mm, bottom + 10.0
    body = ''.join(_polygon(c, offsets[c.key]) for c in inst.copies)
    parts = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.1f}mm" height="{height:.1f}mm" '
             f'viewBox="0 0 {width:.1f} {height:.1f}">{body}</svg>')
    sheet_h = inst.fabric_width_mm - 2 * (inst.margin_mm - inst.gap_mm / 2)
    sheet = (f'<svg xmlns="http://www.w3.org/2000/svg"><rect x="0" y="0" width="{bin_length_mm * units_per_mm:.4f}" '
             f'height="{sheet_h * units_per_mm:.4f}" class="sheet"/></svg>')
    return parts, sheet, offsets, sheet_h


def sparrow_json(inst, mode, name):
    """jagua-rs strip-packing instance: strip height = fabric width, one item per copy."""
    items = []
    for i, c in enumerate(inst.copies):
        ring = [[round(float(x), 4), round(float(y), 4)] for x, y in c.tool]
        items.append({'id': i, 'demand': 1, 'allowed_orientations': list(MODES[mode]),
                      'shape': {'type': 'simple_polygon', 'data': ring + [ring[0]]}})
    return {'name': name, 'items': items, 'strip_height': inst.fabric_width_mm}


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=1), encoding='utf-8')
