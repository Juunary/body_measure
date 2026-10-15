"""Grain check on a finished marker: does every grain line (FDL) run along or across the roll?

The grain line of each placed piece is the pattern's line transformed exactly as the piece was placed.
It is `along` when parallel to the roll length (vertical in the marker drawings), `across` when
perpendicular to it (horizontal; the piece is cut cross-grain) and `off` otherwise, i.e. tilted or on
the bias. The study's grain rule allows along and across; `off` is never allowed. The check also
confirms that every placement uses an allowed rotation and that left/right copies are mirrored the way
the mirror rule says.
"""
import math

TOLERANCE_DEG = 0.5


def grain_state(grain_line):
    """('along' | 'across' | 'off', degrees from the nearer of the two allowed directions)."""
    (x0, y0), (x1, y1) = grain_line
    angle = math.degrees(math.atan2(x1 - x0, y1 - y0)) % 180.0     # 0 = along the roll, 90 = across
    along, across = min(angle, 180.0 - angle), abs(angle - 90.0)
    state = 'along' if along <= TOLERANCE_DEG else 'across' if across <= TOLERANCE_DEG else 'off'
    return state, min(along, across)


def check_grain(placements, rotations, mirror='pairs'):
    """Grain state of every placement and the list of rule breaks (empty when the marker keeps the rule)."""
    rows, problems, copies = [], [], {}
    for p in placements:
        state, deviation = grain_state(p['grain_line'])
        name = f"{p['piece_id']} #{p['copy']}"
        rows.append({'piece': name, 'rotation_deg': p['rotation_deg'], 'mirrored': p['mirrored'],
                     'grain': state, 'deviation_deg': round(deviation, 4)})
        if state == 'off':
            problems.append(f'{name}: grain line {deviation:.2f} deg away from along/across the roll')
        if not any(abs((p['rotation_deg'] - r + 180.0) % 360.0 - 180.0) < 1e-6 for r in rotations):
            problems.append(f"{name}: rotation {p['rotation_deg']:g} is not in the allowed set")
        copies.setdefault(p['piece_id'], []).append((p['copy'], p['mirrored']))
    for piece_id, found in copies.items():
        if mirror == 'pairs' and len(found) == 2 and sorted(found) != [(1, False), (2, True)]:
            problems.append(f'{piece_id}: the two copies are not one plain and one mirrored (left/right)')
        if mirror == 'none' and any(m for _, m in found):
            problems.append(f'{piece_id}: mirrored although the mirror rule is none')
    count = {s: sum(r['grain'] == s for r in rows) for s in ('along', 'across', 'off')}
    return {**count, 'max_deviation_deg': max((r['deviation_deg'] for r in rows), default=0.0),
            'pieces': rows, 'problems': problems}
