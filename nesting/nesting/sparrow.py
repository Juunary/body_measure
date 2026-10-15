"""sparrow as the placement engine behind this study's constraint layer.

sparrow (MIT, https://github.com/JeroenGar/sparrow) packs polygons into a strip at the orientations it
is allowed and keeps a minimum distance between them and to the strip edges. It knows nothing else
about a garment, so this module keeps the study's constraints around it:

- grain: every copy may only take the rotations of the grain rule (`Settings.rotations`), counted from
  its pattern grain line, which the importer turned to run along +y;
- left/right: copy 2 of a 2x piece is mirrored before nesting (`--mirror pairs`), because sparrow
  cannot mirror a part itself;
- gap and selvedge margin: sparrow's minimum separation is the gap; a margin wider than the gap
  narrows the strip;
- verification: the marker is rebuilt from the true cut lines and checked for the gap, the roll edges,
  every copy exactly once and the grain (nesting.grain) before it is returned. A rule break raises.

Each copy is packed as its cut line simplified by 0.25 mm and grown back by 0.26 mm, so the packed
polygon always contains the true cut line. Research tool, not production CAD.
"""
import json
import math
import os
from pathlib import Path
import subprocess
import time

import numpy as np
from shapely import STRtree
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient

from .grain import check_grain
from .pieces import transform_marks, transform_points
from .polygons import orient_coords

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'sparrow v0.2.0 (ed1c72c)'
SIMPLIFY_MM = 0.25
GAP_TOLERANCE_MM = 0.05


def find_binary():
    """The sparrow executable: $SPARROW_EXE, else the build `python -m bench.fetch_tools` makes."""
    if os.environ.get('SPARROW_EXE'):
        exe = Path(os.environ['SPARROW_EXE'])
    else:
        exe = ROOT / '.bench' / 'tools' / 'sparrow' / 'target' / 'release' / ('sparrow.exe' if os.name == 'nt' else 'sparrow')
    if not exe.is_file():
        raise FileNotFoundError(f'sparrow not found at {exe}; build it with `python -m bench.fetch_tools` or set SPARROW_EXE')
    return exe


def packed_polygon(contour, tolerance=SIMPLIFY_MM):
    """The cut line simplified and grown back by the same amount: always contains the true cut line."""
    true = Polygon(contour)
    grown = true.simplify(tolerance, preserve_topology=True).buffer(tolerance + 0.01, join_style='mitre', mitre_limit=2.0)
    if grown.geom_type != 'Polygon' or not grown.covers(true):
        raise ValueError('packed polygon does not contain the cut line')
    return orient(grown, 1.0)


def copies_of(pieces, mirror):
    """(piece, copy, mirrored) for every copy; sparrow cannot pick a mirror, so `free` is refused."""
    if mirror not in ('pairs', 'none'):
        raise ValueError('the sparrow engine needs --mirror pairs or none')
    return [(piece, copy, mirror == 'pairs' and piece.quantity == 2 and copy == 2)
            for piece in pieces for copy in range(1, piece.quantity + 1)]


def strip_inset(settings):
    """How far the strip edges sit inside the roll edges; sparrow already keeps the gap to them."""
    return max(0.0, settings.edge_margin_mm - settings.gap_mm)


def build_instance(pieces, settings, name='marker'):
    """sparrow instance in its frame (x along the roll, y across it, grain along +x) and the copy list."""
    copies = copies_of(pieces, settings.mirror)
    items = []
    for i, (piece, _copy, mirrored) in enumerate(copies):
        ring = np.asarray(packed_polygon(piece.contour).exterior.coords)[:-1]
        tool = np.asarray(orient(Polygon(orient_coords(ring, mirrored, -90.0)), 1.0).exterior.coords)[:-1]
        data = [[round(float(x), 4), round(float(y), 4)] for x, y in tool]
        items.append({'id': i, 'demand': 1, 'allowed_orientations': [float(r) for r in settings.rotations],
                      'shape': {'type': 'simple_polygon', 'data': data + [data[0]]}})
    return {'name': name, 'items': items, 'strip_height': settings.fabric_width_mm - 2 * strip_inset(settings)}, copies


def snap(rotation, allowed):
    """sparrow's rotation as the allowed angle it stands for; anything else breaks the grain rule."""
    for a in allowed:
        if abs((float(rotation) - a + 180.0) % 360.0 - 180.0) < 1e-3:
            return float(a) % 360.0
    raise RuntimeError(f'sparrow returned rotation {rotation}, outside the grain rule {list(allowed)}')


def _round(points, digits=3):
    return [[round(float(x), digits), round(float(y), digits)] for x, y in points]


def to_placements(output, copies, settings):
    """sparrow's placed items as the study's placement records, the marker pushed to the roll start.
    A placement P = R(r) Q + t of the packed polygon Q is rotation r with the origin at
    (width - inset - t_y, t_x) in the study frame (x across the roll, y along it)."""
    width, inset = settings.fabric_width_mm, strip_inset(settings)
    placed = []
    for item in output['solution']['layout']['placed_items']:
        piece, copy, mirrored = copies[int(item['item_id'])]
        tf = item['transformation']
        rotation = snap(tf['rotation'], settings.rotations)
        placed.append((piece, copy, mirrored, rotation, width - inset - float(tf['translation'][1]),
                       float(tf['translation'][0])))
    low = min(y for p in placed for _, y in transform_points(p[0].contour, p[2], p[3], p[4], p[5]))
    shift = settings.edge_margin_mm - low
    records = []
    for piece, copy, mirrored, rotation, x, y in placed:
        y += shift
        records.append({
            'piece_id': piece.id, 'copy': copy, 'rotation_deg': rotation, 'mirrored': mirrored,
            'x_mm': round(x, 4), 'y_mm': round(y, 4), 'item': f'{piece.id}#{copy}',
            'contour': _round(transform_points(piece.contour, mirrored, rotation, x, y)),
            'seam_line': _round(transform_points(piece.seam_line, mirrored, rotation, x, y)),
            'grain_line': _round(transform_points(piece.grain_line, mirrored, rotation, x, y)),
            'marks': [{'kind': m['kind'], 'points': _round(m['points'])}
                      for m in transform_marks(piece.marks, mirrored, rotation, x, y)],
        })
    records.sort(key=lambda r: (r['piece_id'], r['copy']))
    return records


def verify(records, copies, settings):
    """Gap between true cut lines, roll edges and copies; returns (issues, min_distance_mm, length_mm)."""
    issues = []
    polys = [Polygon(r['contour']) for r in records]
    tree = STRtree(polys)
    min_distance = math.inf
    for i, poly in enumerate(polys):
        for j in tree.query(poly.buffer(settings.gap_mm + 1.0)):
            if j <= i:
                continue
            d = poly.distance(polys[j])
            min_distance = min(min_distance, d)
            if d < settings.gap_mm - GAP_TOLERANCE_MM:
                issues.append(f"{records[i]['item']} and {records[j]['item']} are {d:.2f} mm apart")
    if min_distance == math.inf:          # nothing within reach: report the true minimum
        min_distance = min(a.distance(b) for i, a in enumerate(polys) for b in polys[i + 1:])
    length = max(y for r in records for _, y in r['contour']) + settings.edge_margin_mm
    frame = box(settings.edge_margin_mm, settings.edge_margin_mm, settings.fabric_width_mm - settings.edge_margin_mm,
                length - settings.edge_margin_mm).buffer(1e-3)
    issues += [f"{r['item']} leaves the roll frame" for r, poly in zip(records, polys) if not frame.covers(poly)]
    expected = sorted((p.id, c) for p, c, _ in copies)
    if sorted((r['piece_id'], r['copy']) for r in records) != expected:
        issues.append('the marker does not hold every copy exactly once')
    return issues, min_distance, length


def nest_with_sparrow(pieces, settings, work_dir, workers=None, binary=None):
    """Run sparrow under the study's constraints and return a result in the study's marker format."""
    started = time.time()
    exe = binary or find_binary()
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    instance, copies = build_instance(pieces, settings)
    (work / 'instance.json').write_text(json.dumps(instance), encoding='utf-8')
    args = [str(exe), '-i', 'instance.json', '-t', str(max(1, int(round(settings.time_limit_s)))),
            '-s', str(settings.seed), '--min-item-separation', f'{settings.gap_mm:g}']
    if workers:
        args += ['--workers', str(workers)]
    run = subprocess.run(args, cwd=work, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (work / 'sparrow.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    if run.returncode != 0:
        raise RuntimeError('sparrow failed:\n' + '\n'.join((run.stdout + run.stderr).splitlines()[-20:]))
    output = json.loads((work / 'output' / f"final_{instance['name']}.json").read_text(encoding='utf-8'))
    records = to_placements(output, copies, settings)
    issues, min_distance, length = verify(records, copies, settings)
    grain = check_grain(records, settings.rotations, settings.mirror)
    if issues or grain['problems']:
        raise RuntimeError('sparrow marker breaks the rules: ' + '; '.join(issues + grain['problems']))
    width, margin = settings.fabric_width_mm, settings.edge_margin_mm
    piece_area = sum(p.area_mm2 * p.quantity for p in pieces)
    naive = sum(p.height_mm * p.quantity for p in pieces) + settings.gap_mm * (len(copies) - 1) + 2 * margin
    order = sorted(records, key=lambda r: min(y for _, y in r['contour']))
    return {
        'version': 'nesting-study/1',
        'engine': VERSION,
        'settings': {'engine': 'sparrow', 'fabric_width_mm': width, 'gap_mm': settings.gap_mm, 'edge_margin_mm': margin,
                     'rotations': list(settings.rotations), 'mirror': settings.mirror, 'seed': settings.seed,
                     'time_limit_s': settings.time_limit_s, 'workers': workers or 3},
        'sequence': [f"{r['item']}@{r['rotation_deg']:g}" for r in order],     # along the roll, for reading only
        'placements': records,
        'totals': {
            'fabric_width_mm': width,
            'length_mm': round(length, 3),
            'piece_area_mm2': round(piece_area, 1),
            'efficiency_pct': round(100.0 * piece_area / (width * length), 2),
            'lower_bound_length_mm': round(piece_area / (width - 2 * margin) + 2 * margin, 1),
            'naive_stack_length_mm': round(naive, 1),
            'min_distance_mm': round(float(min_distance), 3),
            'placements': len(records),
            'runtime_s': round(time.time() - started, 2),
            'time_limit_hit': True,         # sparrow searches until its time limit: the result depends on the machine
        },
        'stages': {'strip_width_reported_mm': output['solution'].get('strip_width')},
        'grain': grain,
    }
