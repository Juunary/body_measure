"""Marker outputs: SVG drawing, PNG preview, JSON result and a Markdown report.

Presentation only; every number comes from the nesting result. The SVG uses
1 user unit = 1 mm with the roll start at the bottom (y flipped for display).
"""
import json
from pathlib import Path

HEADER_MM = 28.0   # band above the roll for the title, so labels never overlap pieces
PALETTE = ['#cfe3f5', '#f5dfc9', '#d9edd2', '#efd6e6', '#f2ecc4', '#d6e6ee', '#e5d9f2', '#e8e8e8']


def _fmt(points, length):
    return ' '.join(f'{x:.2f},{HEADER_MM + length - y:.2f}' for x, y in points)


def _label(placement):
    text = f"{placement['piece_id']} #{placement['copy']}"
    if placement['mirrored']:
        text += ' M'
    return f"{text} {placement['rotation_deg']:g}°"


def marker_svg(result):
    totals, settings = result['totals'], result['settings']
    width, length, margin = totals['fabric_width_mm'], totals['length_mm'], settings['edge_margin_mm']
    total = length + HEADER_MM
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{total}mm" '
           f'viewBox="0 0 {width} {total}" font-family="Arial, Helvetica, sans-serif">',
           f'<rect x="0" y="0" width="{width}" height="{total}" fill="#ffffff"/>',
           f'<rect x="0" y="{HEADER_MM}" width="{width}" height="{length}" fill="#f8f4ec" stroke="#555" stroke-width="0.6"/>',
           f'<rect x="{margin}" y="{HEADER_MM + margin}" width="{width - 2 * margin}" height="{length - 2 * margin}" '
           f'fill="none" stroke="#999" stroke-width="0.4" stroke-dasharray="6 4"/>']
    piece_ids = sorted({p['piece_id'] for p in result['placements']})
    colour = {pid: PALETTE[i % len(PALETTE)] for i, pid in enumerate(piece_ids)}
    for p in result['placements']:
        out.append(f'<polygon points="{_fmt(p["contour"], length)}" fill="{colour[p["piece_id"]]}" '
                   f'stroke="#111" stroke-width="0.7"/>')
        out.append(f'<polygon points="{_fmt(p["seam_line"], length)}" fill="none" stroke="#666" '
                   f'stroke-width="0.35" stroke-dasharray="3 2"/>')
        for m in p['marks']:
            style = {'notch': 'stroke="#d62728" stroke-width="0.9"',
                     'fold': 'stroke="#5b4fb5" stroke-width="0.4" stroke-dasharray="4 3"',
                     'centre': 'stroke="#8c1d1d" stroke-width="0.9"'}.get(m['kind'], 'stroke="#333" stroke-width="0.4"')
            out.append(f'<polyline points="{_fmt(m["points"], length)}" fill="none" {style}/>')
        (gx0, gy0), (gx1, gy1) = p['grain_line']
        out.append(f'<line x1="{gx0:.2f}" y1="{HEADER_MM + length - gy0:.2f}" x2="{gx1:.2f}" y2="{HEADER_MM + length - gy1:.2f}" '
                   f'stroke="#2b5fd9" stroke-width="0.8"/>')
        for (ax, ay), sign in (((gx0, gy0), 1), ((gx1, gy1), -1)):
            # arrowheads on both ends: grain is a direction, not a vector
            dx, dy = (gx1 - gx0), (gy1 - gy0)
            n = max((dx * dx + dy * dy) ** 0.5, 1e-9)
            ux, uy = dx / n * sign, dy / n * sign
            tip = (ax, ay)
            base = (ax + ux * 12, ay + uy * 12)
            left = (base[0] - uy * 4, base[1] + ux * 4)
            right = (base[0] + uy * 4, base[1] - ux * 4)
            out.append(f'<polygon points="{_fmt([tip, left, right], length)}" fill="#2b5fd9"/>')
        xs = [x for x, _ in p['contour']]
        ys = [y for _, y in p['contour']]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        size = max(9.0, min(20.0, (max(xs) - min(xs)) / 14))
        out.append(f'<text x="{cx:.1f}" y="{HEADER_MM + length - cy:.1f}" font-size="{size:.1f}" text-anchor="middle" '
                   f'fill="#111">{_label(p)}</text>')
    out.append(f'<text x="{margin + 4}" y="{HEADER_MM - 9}" font-size="12" fill="#333">'
               f'{width:g} x {length:.0f} mm, efficiency {totals["efficiency_pct"]:.1f} %, '
               f'gap {settings["gap_mm"]:g} mm, rotations {",".join(f"{r:g}" for r in settings["rotations"])}</text>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def marker_png(svg_path, png_path, target_width_px=1600):
    """Render the SVG with PyMuPDF; returns False (and writes nothing) if MuPDF cannot parse it."""
    try:
        import pymupdf
        doc = pymupdf.open(str(svg_path))
        page = doc[0]
        scale = target_width_px / page.rect.width
        page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(str(png_path))
        doc.close()
        return True
    except Exception as exc:  # rendering is a convenience, never a failure of the nesting
        print(f'PNG preview skipped: {exc}')
        return False


def report_md(result, pieces):
    t, s = result['totals'], result['settings']
    lines = ['# Nesting report', '',
             'Research marker for one shirt pattern; not a production marker.', '',
             '## Settings', '', '| setting | value |', '|---|---|']
    for k, v in s.items():
        lines.append(f'| {k} | {v} |')
    lines += ['', '## Totals', '', '| metric | value |', '|---|---|']
    for k, v in t.items():
        lines.append(f'| {k} | {v} |')
    lines += ['', '## Pieces', '', '| piece | qty | area mm2 | size mm | placed as |', '|---|---|---|---|---|']
    by_id = {}
    for p in result['placements']:
        by_id.setdefault(p['piece_id'], []).append(p)
    for piece in pieces:
        placed = ', '.join(f"#{p['copy']}{' M' if p['mirrored'] else ''} {p['rotation_deg']:g}° "
                           f"@({p['x_mm']:.0f},{p['y_mm']:.0f})" for p in by_id.get(piece.id, []))
        lines.append(f'| {piece.id} | {piece.quantity} | {piece.area_mm2:.0f} | '
                     f'{piece.width_mm:.0f} x {piece.height_mm:.0f} | {placed} |')
    grain = result.get('grain')
    if grain:
        lines += ['', '## Grain', '',
                  f"{grain['along']} piece(s) with the grain line along the roll, {grain['across']} across it "
                  f"(cut cross-grain), {grain['off']} tilted; largest deviation {grain['max_deviation_deg']:g} deg.",
                  '', '| piece | rotation | mirrored | grain line |', '|---|---|---|---|']
        lines += [f"| {r['piece']} | {r['rotation_deg']:g} | {'yes' if r['mirrored'] else 'no'} | {r['grain']} |"
                  for r in grain['pieces']]
        if grain['problems']:
            lines += ['', '**Grain rule broken:** ' + '; '.join(grain['problems'])]
    lines += ['', '## Sequence', '', ', '.join(result['sequence']), '']
    if result.get('stages'):
        lines += ['## Stages', '', '| stage | value |', '|---|---|']
        lines += [f'| {k} | {v} |' for k, v in result['stages'].items()]
        lines.append('')
    if t.get('time_limit_hit'):
        lines += ['**Time limit reached: this result is machine dependent.**', '']
    return '\n'.join(lines)


def write_outputs(result, pieces, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'marker.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'marker.svg').write_text(marker_svg(result), encoding='utf-8')
    (out / 'report.md').write_text(report_md(result, pieces), encoding='utf-8')
    png = marker_png(out / 'marker.svg', out / 'marker.png')
    return {'marker.json': out / 'marker.json', 'marker.svg': out / 'marker.svg',
            'report.md': out / 'report.md', 'marker.png': (out / 'marker.png') if png else None}
