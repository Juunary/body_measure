"""Command line: `python -m nesting import <pdf>` and `python -m nesting nest <pieces.json>`."""
import argparse
import json
from pathlib import Path
import sys

from .marker import write_outputs
from .pattern_pdf import import_pdf, pieces_svg
from .pieces import load_pieces, save_pieces
from .placer import PLACEMENT_RULES
from .search import DEFAULT_ROTATIONS, MIRROR_RULES, Settings, nest


def _rotations(text):
    values = tuple(float(v) for v in text.split(',') if v.strip())
    if not values:
        raise argparse.ArgumentTypeError('at least one rotation is required')
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(prog='nesting', description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    imp = sub.add_parser('import', help='read a 1:1 pattern PDF into pieces.json (+ pieces.svg)')
    imp.add_argument('pdf')
    imp.add_argument('-o', '--out', default='out/pieces.json')
    imp.add_argument('--width', type=float, default=1007.0, help='bin width for pieces.svg (mm)')

    run = sub.add_parser('nest', help='nest pieces.json on a roll of fixed width')
    run.add_argument('pieces')
    run.add_argument('-o', '--out', default='out/marker')
    run.add_argument('--width', type=float, default=1007.0, help='fabric width (mm)')
    run.add_argument('--gap', type=float, default=5.0, help='minimum distance between pieces (mm)')
    run.add_argument('--margin', type=float, default=5.0, help='selvedge / roll-end margin (mm)')
    run.add_argument('--rotations', type=_rotations, default=DEFAULT_ROTATIONS, help='default 0,90,180,270 (grain along or across the roll); 0,180 keeps every grain line along it')
    run.add_argument('--mirror', choices=MIRROR_RULES, default='pairs')
    run.add_argument('--beam', type=int, default=16)
    run.add_argument('--window', type=int, default=4)
    run.add_argument('--iterations', type=int, default=1500, help='decode budget of the iterated local search')
    run.add_argument('--seed', type=int, default=0)
    run.add_argument('--time-limit', type=float, default=120.0, help='seconds; stopping early makes the result machine dependent')
    run.add_argument('--pairs', action='store_true',
                     help='also offer each 2x shape as one pre-nested mirrored pair (the local search cannot split it)')
    run.add_argument('--restart-patience', type=int, default=2500,
                     help='decodes without a better layout before the local search restarts')
    run.add_argument('--placement', choices=PLACEMENT_RULES, default='bottom-left', help='candidate ranking rule')
    run.add_argument('--engine', choices=('study', 'sparrow'), default='study',
                     help="placement engine: this study's beam and local search, or sparrow behind the same "
                          'grain, mirror and gap rules (runs for the whole --time-limit)')
    run.add_argument('--workers', type=int, default=None, help='sparrow separator threads (default 3)')

    args = parser.parse_args(argv)
    if args.command == 'import':
        meta, pieces = import_pdf(args.pdf)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        save_pieces(out, meta, pieces)
        svg = out.with_suffix('.svg')
        svg.write_text(pieces_svg(pieces, args.width), encoding='utf-8')
        for p in pieces:
            print(f'{p.id:12s} x{p.quantity}  {p.width_mm:6.1f} x {p.height_mm:6.1f} mm  grain {p.grain_angle_deg:g} deg  '
                  f'{len(p.marks)} marks')
        print(f'{len(pieces)} shapes, {sum(p.quantity for p in pieces)} placements -> {out} and {svg}')
        return 0

    _, pieces = load_pieces(args.pieces)
    settings = Settings(fabric_width_mm=args.width, gap_mm=args.gap, edge_margin_mm=args.margin,
                        rotations=args.rotations, mirror=args.mirror, beam=args.beam, window=args.window,
                        iterations=args.iterations, seed=args.seed, time_limit_s=args.time_limit,
                        pairs=args.pairs, placement=args.placement, restart_patience=args.restart_patience)
    if args.engine == 'sparrow':
        from .sparrow import nest_with_sparrow
        result = nest_with_sparrow(pieces, settings, Path(args.out) / 'sparrow', workers=args.workers)
    else:
        result = nest(pieces, settings)
    files = write_outputs(result, pieces, args.out)
    t = result['totals']
    print(f"length {t['length_mm']:.0f} mm on {t['fabric_width_mm']:g} mm, efficiency {t['efficiency_pct']:.2f} % "
          f"(lower bound {t['lower_bound_length_mm']:.0f} mm), min distance {t['min_distance_mm']} mm, "
          f"{t['runtime_s']} s")
    g = result['grain']
    print(f"grain: {g['along']} along the roll, {g['across']} across, {g['off']} tilted"
          + (f"; RULE BROKEN: {'; '.join(g['problems'])}" if g['problems'] else ''))
    print('wrote ' + ', '.join(str(v) for v in files.values() if v))
    return 0


if __name__ == '__main__':
    sys.exit(main())
