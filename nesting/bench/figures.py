"""Figures for the benchmark report: convergence curves and markers drawn at one common scale.

Colours are the validated categorical slots 1-4 (blue, orange, aqua, yellow) in a
fixed order per tool; every line is also labelled directly, and the report's
table carries the same numbers, so identity never rests on colour alone.
"""
import io

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from nesting.marker import marker_svg

from .instance import MODE_LABELS, MODES

SURFACE = '#fcfcfb'
INK = '#0b0b0b'
INK_2 = '#52514e'
GRID = '#e4e3de'
COLOURS = {'ours': '#2a78d6', 'sparrow': '#eb6834', 'sparrow-1w': '#eb6834', 'deepnest': '#1baf7a', 'svgnest': '#eda100'}
STYLES = {'sparrow-1w': (0, (4, 2))}
FONT = 'C:/Windows/Fonts/arial.ttf'
FONT_BOLD = 'C:/Windows/Fonts/arialbd.ttf'


def _key(record):
    return record['tool'] + ('-' + record['variant'] if record.get('variant') else '')


def _step(trace, grid):
    """Best-so-far length at each grid time; NaN before the first marker."""
    times = np.array([t for t, _ in trace])
    lengths = np.minimum.accumulate(np.array([length for _, length in trace]))
    idx = np.searchsorted(times, grid, side='right') - 1
    out = np.full(grid.shape, np.nan)
    ok = idx >= 0
    out[ok] = lengths[idx[ok]]
    return out


def convergence(records, lower_bound_mm, path, labels, budget_s=120, width_mm=1007.0, zone_mm=None, rules=None):
    rules = tuple(rules or MODES)
    plt.rcParams.update({'font.family': 'Arial', 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK_2,
                         'xtick.color': INK_2, 'ytick.color': INK_2})
    fig, axes = plt.subplots(1, len(rules), figsize=(max(7.0, 5.5 * len(rules)), 4.6), sharey=True, dpi=160)
    fig.patch.set_facecolor(SURFACE)
    grid = np.geomspace(0.5, budget_s, 400)
    ymax, ends_by_axis = 0, []
    for ax, mode in zip(np.atleast_1d(axes), rules):
        ax.set_facecolor(SURFACE)
        ends = []
        ends_by_axis.append((ax, ends))
        for key in ('svgnest', 'deepnest', 'sparrow-1w', 'sparrow', 'ours'):
            runs = [r for r in records if r['mode'] == mode and _key(r) == key and r['budget_s'] == budget_s
                    and 'error' not in r and r['trace']]
            if not runs:
                continue
            curves = np.vstack([_step(r['trace'], grid) for r in runs])
            complete = ~np.isnan(curves).any(axis=0)
            median = np.where(complete, np.nanmedian(curves, axis=0), np.nan)
            low = np.where(complete, np.nanmin(curves, axis=0), np.nan)
            high = np.where(complete, np.nanmax(curves, axis=0), np.nan)
            colour = COLOURS[key]
            ax.fill_between(grid, low, high, color=colour, alpha=0.14, linewidth=0)
            ax.plot(grid, median, color=colour, linewidth=1.6, linestyle=STYLES.get(key, '-'),
                    label=f'{labels[key]} (median of {len(runs)})', solid_capstyle='round')
            if complete.any():
                ends.append((median[complete][-1], labels[key]))
                ymax = max(ymax, np.nanmax(high[complete][: max(1, complete.sum() // 8)]))
        ax.axhline(lower_bound_mm, color=INK_2, linewidth=0.9, linestyle=(0, (1, 2)))
        ax.text(0.55, lower_bound_mm - 12, f'area lower bound {lower_bound_mm:.0f} mm', color=INK_2, fontsize=8, va='top')
        ax.set_xscale('log')
        ax.set_xlim(0.5, budget_s)
        ax.set_xticks([1, 2, 5, 10, 30, 60, 120])
        ax.set_xticklabels(['1', '2', '5', '10', '30', '60', '120'])
        ax.set_xlabel('Wall-clock time (s, log scale)')
        ax.set_title(MODE_LABELS[mode], color=INK, fontsize=10, loc='left')
        ax.grid(True, color=GRID, linewidth=0.6)
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
    first = np.atleast_1d(axes)[0]
    first.set_ylabel('Marker length (mm), lower is better')
    y0, y1 = lower_bound_mm - 60, min(ymax + 40, lower_bound_mm + 900)
    first.set_ylim(y0, y1)
    step = 0.045 * (y1 - y0)            # about one label height, so direct labels never overlap
    for ax, ends in ends_by_axis:
        if zone_mm and y0 < zone_mm < y1:
            ax.axhline(zone_mm, color=INK_2, linewidth=0.9, linestyle=(0, (4, 3)))
            ax.text(0.55, zone_mm + 12, f'cutting zone {zone_mm:.0f} mm, one conveyor window', color=INK_2,
                    fontsize=8, va='bottom')
        placed = []
        for y, text in sorted(ends):
            while any(abs(y - p) < step for p in placed):
                y += step
            placed.append(y)
            ax.text(budget_s * 1.04, y, text, color=INK, fontsize=8, va='center')
    handles, texts = first.get_legend_handles_labels()
    fig.legend(handles, texts, loc='lower center', ncol=len(texts) if len(rules) > 1 else 3, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, -0.01), labelcolor=INK)
    fig.suptitle(f'Best marker found so far, {width_mm:g} mm roll, 9 pieces, gap 5 mm (band = min to max over runs)',
                 x=0.01, ha='left', color=INK, fontsize=11)
    fig.tight_layout(rect=(0, 0.06 if len(rules) > 1 else 0.11, 0.9 if len(rules) > 1 else 0.76, 0.95))
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def _render(result, px_per_mm):
    import pymupdf
    doc = pymupdf.open(stream=marker_svg(result).encode('utf-8'), filetype='svg')
    page = doc[0]
    scale = px_per_mm * result['totals']['fabric_width_mm'] / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    image = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    doc.close()
    return image


def markers(chosen, path, title, px_per_mm=0.34):
    """Markers side by side at the same px per mm, so a longer marker is drawn longer."""
    images = [(label, result, _render(result, px_per_mm)) for label, result in chosen]
    head, gap, pad = 58, 26, 24
    font, bold, big = ImageFont.truetype(FONT, 15), ImageFont.truetype(FONT_BOLD, 16), ImageFont.truetype(FONT_BOLD, 18)
    title_width = int(big.getlength(title))
    width = pad * 2 + max(title_width, sum(im.width for _, _, im in images) + gap * (len(images) - 1))
    height = 44 + head + max(im.height for _, _, im in images) + pad
    canvas = Image.new('RGB', (width, height), SURFACE)
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, 12), title, fill=INK, font=big)
    x = pad
    for label, result, im in images:
        t = result['totals']
        draw.text((x, 44), label, fill=INK, font=bold)
        draw.text((x, 66), f"{t['length_mm']:.0f} mm, {t['efficiency_pct']:.1f} %", fill=INK_2, font=font)
        canvas.paste(im, (x, 44 + head))
        x += im.width + gap
    canvas.save(path)
