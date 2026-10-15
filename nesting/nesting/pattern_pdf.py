"""PDF pattern-sheet import: colour-coded vector paths become piece records.

Research importer for one drafting convention (grey cut line with seam
allowance, white-filled net line, blue-violet grain and fold lines, red 10 mm
notches, a 10x10 cm scale square); not a general pattern CAD reader. This is
the only module besides marker.py that imports PyMuPDF (AGPL).
"""
import math
import re

import pymupdf
from shapely import make_valid
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient

from .pieces import Piece, rotate_points

PT_TO_MM = 25.4 / 72
COLOUR_TOL = 0.02
CURVE_STEP_MM = 2.0          # flattening step; sagitta <= 0.1 mm for radii >= 5 mm
STRAIGHT_TOL_MM = 1.0        # max deviation from the chord for a "straight" line
MIN_GRAIN_LENGTH_MM = 100.0
SCALE_SQUARE_MM = 100.0
SCALE_TOL_MM = 0.2

COLOURS = {
    'net': (0.2, 0.2, 0.2),          # white fill + this stroke
    'cut': (0.353, 0.353, 0.353),
    'blue': (0.498, 0.459, 0.737),   # grain (FDL), fold and hem lines
    'notch': (1.0, 0.0, 0.0),
    'centre': (0.859, 0.204, 0.145), # thin lines only; the width-10 X over the template is ignored
    'scale': (0.549, 0.2, 0.2),      # the 10x10 cm rectangle
}
FLAG_WORDS = {'UMBRUCH', '+EINLAGE', 'FDL'}
EXCLUDED_NAMES = {'SCHABLONE'}
QUANTITY = re.compile(r'^(\d+)XSTOFF$')
SIZE_LABEL = re.compile(r'^\d+x\d+cm$')
UMLAUTS = str.maketrans({'Ä': 'AE', 'Ö': 'OE', 'Ü': 'UE', 'ß': 'SS'})


def _close(colour, target):
    return colour is not None and all(abs(a - b) <= COLOUR_TOL for a, b in zip(colour, target))


def classify(drawing):
    colour, fill, width = drawing.get('color'), drawing.get('fill'), drawing.get('width') or 0
    if fill is not None and _close(colour, COLOURS['net']):
        return 'net'
    if fill is None and _close(colour, COLOURS['cut']):
        return 'cut'
    if _close(colour, COLOURS['blue']):
        return 'blue'
    if _close(colour, COLOURS['notch']):
        return 'notch'
    if _close(colour, COLOURS['centre']) and width < 1:
        return 'centre'
    if _close(colour, COLOURS['scale']) and any(item[0] == 're' for item in drawing['items']):
        return 'scale'
    return 'ignore'


def _bezier(p0, c1, c2, p1, t):
    u = 1 - t
    return (u*u*u*p0.x + 3*u*u*t*c1.x + 3*u*t*t*c2.x + t*t*t*p1.x,
            u*u*u*p0.y + 3*u*u*t*c1.y + 3*u*t*t*c2.y + t*t*t*p1.y)


def flatten_item(item):
    kind = item[0]
    if kind == 'l':
        return [(item[1].x, item[1].y), (item[2].x, item[2].y)]
    if kind == 'c':
        p0, c1, c2, p1 = item[1:5]
        control = (abs(c1 - p0) + abs(c2 - c1) + abs(p1 - c2)) * PT_TO_MM
        n = max(2, min(64, math.ceil(control / CURVE_STEP_MM)))
        return [_bezier(p0, c1, c2, p1, i / n) for i in range(n + 1)]
    if kind == 're':
        r = item[1]
        return [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)]
    if kind == 'qu':
        q = item[1]
        return [(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y), (q.ul.x, q.ul.y)]
    raise ValueError(f'unsupported path item {kind}')


def polylines(drawing, join_tol_pt=0.05):
    """Split a drawing's items into connected polylines (page points)."""
    chains, current = [], []
    for item in drawing['items']:
        seg = flatten_item(item)
        if current and math.dist(current[-1], seg[0]) > join_tol_pt:
            chains.append(current)
            current = []
        current.extend(seg if not current else seg[1:])
    if current:
        chains.append(current)
    return chains


def _is_closed(chain, tol_pt=0.05):
    return len(chain) > 3 and math.dist(chain[0], chain[-1]) <= tol_pt


def _straightness(points_mm):
    chord = LineString([points_mm[0], points_mm[-1]])
    if chord.length < 1e-6:
        return float('inf')
    return max(chord.distance(Point(p)) for p in points_mm[1:-1]) if len(points_mm) > 2 else 0.0


def _ring_polygon(points_mm, label):
    poly = Polygon(points_mm[:-1] if math.dist(points_mm[0], points_mm[-1]) < 1e-9 else points_mm)
    if not poly.is_valid:
        poly = make_valid(poly)
        if poly.geom_type != 'Polygon':
            raise ValueError(f'{label}: outline does not form one simple polygon')
    return orient(poly, 1.0)


def read_sheet(pdf_path):
    """Return the classified geometry of page 1 in mm, y up."""
    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    height_pt = page.rect.height

    def to_mm(p):
        return (p[0] * PT_TO_MM, (height_pt - p[1]) * PT_TO_MM)

    sheet = {'page_size_mm': [round(page.rect.width * PT_TO_MM, 2), round(height_pt * PT_TO_MM, 2)],
             'cut': [], 'net': [], 'blue': [], 'notch': [], 'centre': [], 'scale': []}
    for drawing in page.get_drawings():
        role = classify(drawing)
        if role == 'ignore':
            continue
        for chain in polylines(drawing):
            sheet[role].append({'points': [to_mm(p) for p in chain], 'closed': _is_closed(chain)})
    words = []
    for x0, y0, x1, y1, text, *_ in page.get_text('words'):
        words.append({'text': text.strip(), 'centre': to_mm(((x0 + x1) / 2, (y0 + y1) / 2))})
    sheet['words'] = words
    doc.close()
    return sheet


def _scale_check(sheet):
    squares = [s for s in sheet['scale'] if s['closed']]
    if not squares:
        raise ValueError('no 10x10 cm scale square found; cannot confirm the sheet is 1:1')
    b = Polygon(squares[0]['points']).bounds
    w, h = b[2] - b[0], b[3] - b[1]
    if abs(w - SCALE_SQUARE_MM) > SCALE_TOL_MM or abs(h - SCALE_SQUARE_MM) > SCALE_TOL_MM:
        raise ValueError(f'scale square measures {w:.2f} x {h:.2f} mm, expected {SCALE_SQUARE_MM}')
    return round((w + h) / 2, 3)


def _grain_angle(points_mm):
    (x0, y0), (x1, y1) = points_mm[0], points_mm[-1]
    angle = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180.0
    snapped = (round(angle / 90.0) * 90.0) % 180.0
    off = min(abs(angle - snapped), abs(angle - snapped - 180.0), abs(angle - snapped + 180.0))
    return snapped if off <= 1.0 else angle


def _local_frame(points, rotation_deg, shift):
    return [[x - shift[0], y - shift[1]] for x, y in rotate_points(points, rotation_deg)]


def _midpoint(points):
    return LineString(points).interpolate(0.5, normalized=True)


def extract_pieces(sheet):
    """Assemble pieces from the classified sheet. Returns (meta, [Piece])."""
    scale = _scale_check(sheet)
    outlines = []
    for cut in sheet['cut']:
        if not cut['closed']:
            continue
        polygon = _ring_polygon(cut['points'], 'cut line')
        inside = [w for w in sheet['words'] if polygon.contains(Point(w['centre']))]
        names = [w['text'] for w in inside
                 if w['text'] not in FLAG_WORDS and not QUANTITY.match(w['text']) and not SIZE_LABEL.match(w['text'])]
        if not names:
            raise ValueError(f'cut outline at {polygon.bounds} has no name label')
        outlines.append({'polygon': polygon, 'name': names[0], 'words': inside})
    pieces, used = [], set()
    for o in outlines:
        polygon, name = o['polygon'], o['name']
        if name in EXCLUDED_NAMES:
            continue
        quantities = [int(QUANTITY.match(w['text']).group(1)) for w in o['words'] if QUANTITY.match(w['text'])]
        if len(quantities) != 1:
            raise ValueError(f'{name}: expected one nXSTOFF label, found {quantities}')
        flags = sorted({w['text'] for w in o['words'] if w['text'] in FLAG_WORDS})
        nets = [Polygon(n['points']) for n in sheet['net'] if n['closed']
                and polygon.contains(Polygon(n['points']).representative_point())]
        if len(nets) != 1:
            raise ValueError(f'{name}: expected one net line inside the cut line, found {len(nets)}')
        net = orient(nets[0], 1.0)
        fdl = [w['centre'] for w in o['words'] if w['text'] == 'FDL']
        straight, other = [], []
        for line in sheet['blue']:
            pts = line['points']
            if not polygon.contains(_midpoint(pts)):
                continue
            if math.dist(pts[0], pts[-1]) >= MIN_GRAIN_LENGTH_MM and _straightness(pts) <= STRAIGHT_TOL_MM:
                straight.append(pts)
            else:
                other.append(pts)
        if not straight:
            raise ValueError(f'{name}: no straight grain-line candidate inside the cut line')
        anchor = fdl[0] if fdl else polygon.centroid.coords[0]
        straight.sort(key=lambda pts: LineString(pts).distance(Point(anchor)))
        grain_pts, folds = straight[0], straight[1:] + other
        angle = _grain_angle(grain_pts)
        rotation = (90.0 - angle) % 360.0
        marks = [{'kind': 'fold', 'points': pts} for pts in folds]
        for kind in ('notch', 'centre'):
            for line in sheet[kind]:
                if id(line) not in used and polygon.buffer(6.0).contains(_midpoint(line['points'])):
                    used.add(id(line))
                    marks.append({'kind': kind, 'points': line['points']})
        contour = rotate_points(list(polygon.exterior.coords)[:-1], rotation)
        shift = (min(x for x, _ in contour), min(y for _, y in contour))
        grain_local = _local_frame([grain_pts[0], grain_pts[-1]], rotation, shift)
        gx = (grain_local[0][0] + grain_local[1][0]) / 2
        gy0, gy1 = sorted((grain_local[0][1], grain_local[1][1]))
        piece = Piece(id=name.translate(UMLAUTS), quantity=quantities[0],
                      contour=[[x - shift[0], y - shift[1]] for x, y in contour],
                      seam_line=_local_frame(list(net.exterior.coords)[:-1], rotation, shift),
                      grain_line=[[gx, gy0], [gx, gy1]], grain_angle_deg=angle, flags=flags,
                      marks=[{'kind': m['kind'], 'points': _local_frame(m['points'], rotation, shift)} for m in marks])
        piece.validate()
        pieces.append(piece)
    pieces.sort(key=lambda p: (-p.area_mm2, p.id))
    stray = [line for kind in ('notch', 'centre') for line in sheet[kind] if id(line) not in used]
    meta = {'page_size_mm': sheet['page_size_mm'], 'scale_check_mm': scale, 'units': 'mm',
            'excluded': sorted(o['name'] for o in outlines if o['name'] in EXCLUDED_NAMES),
            'unassigned_marks': len(stray)}
    return meta, pieces


def import_pdf(pdf_path):
    meta, pieces = extract_pieces(read_sheet(pdf_path))
    return {'file': str(pdf_path), **meta}, pieces


def pieces_svg(pieces, fabric_width_mm, spacing_mm=20.0):
    """SVG with 1 user unit = 1 mm for Deepnest / SVGnest baselines: a bin rectangle
    plus each piece repeated `quantity` times (those tools do not mirror parts)."""
    total_area = sum(p.area_mm2 * p.quantity for p in pieces)
    bin_length = math.ceil(2.0 * total_area / fabric_width_mm / 100) * 100
    x0 = fabric_width_mm + spacing_mm
    x, row_y, tallest, elements = x0, 0.0, 0.0, []
    for piece in pieces:
        for copy in range(1, piece.quantity + 1):
            if x > x0 and x + piece.width_mm > x0 + fabric_width_mm:
                x, row_y, tallest = x0, row_y + tallest + spacing_mm, 0.0
            pts = ' '.join(f'{x + px:.3f},{row_y + py:.3f}' for px, py in piece.contour)
            elements.append(f'<polygon id="{piece.id}-{copy}" data-piece="{piece.id}" data-copy="{copy}" '
                            f'data-quantity="{piece.quantity}" points="{pts}"/>')
            x += piece.width_mm + spacing_mm
            tallest = max(tallest, piece.height_mm)
    height = max(bin_length, row_y + tallest) + spacing_mm
    width = 2 * fabric_width_mm + 2 * spacing_mm
    body = '\n'.join(elements)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" '
            f'viewBox="0 0 {width} {height}" fill="none" stroke="#000" stroke-width="0.5">\n'
            f'<rect id="bin" x="0" y="0" width="{fabric_width_mm}" height="{bin_length}"/>\n{body}\n</svg>\n')
