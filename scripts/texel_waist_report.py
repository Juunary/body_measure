"""Slice 1 report: estimated waist vs Texel portal_mx dataset reference.

Category: dataset_agreement (agreement with the dataset's automatic
measurements — NOT a measurement-accuracy or ISO-conformity claim).

Run:  .venv\\Scripts\\python scripts\\texel_waist_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.adapters.texel import TexelAdapter  # noqa: E402
from body_measure.canonicalize import canonicalize  # noqa: E402
from body_measure.landmarks.estimated import estimate_waist_level  # noqa: E402
from body_measure.measure.measurements import measure_waist_circumference  # noqa: E402

ROOT = PROJECT_ROOT / "data" / "external" / "texel"


def main() -> int:
    adapter = TexelAdapter()
    persons = adapter.persons(ROOT)
    if not persons:
        print(f"no dataset at {ROOT}", file=sys.stderr)
        return 1

    rows = []
    for person in persons:
        surface = adapter.load(person)
        mesh = canonicalize(surface)
        gt = adapter.checked_dataset_reference(person)
        aux = adapter.aux_reference(person)

        waist = estimate_waist_level(mesh)
        if waist is None:
            rows.append((person.name, None, None, None, None, None, ["no_waist_found"]))
            continue

        value = measure_waist_circumference(mesh, waist)
        rows.append(
            (
                person.name,
                float(waist.position_mm[1]),
                aux.get("waist_height"),
                value.selected_value_mm,
                gt.get("waist_circumference"),          # m102, definition-matched
                aux.get("waist_girth_iso_5_3_10"),      # m16, different definition (context only)
                value.quality,
            )
        )

    print("# Texel Part 1 waist — category: dataset_agreement (portal_mx pipeline)\n")
    print("GT = m102 Minimum Waist Girth (matches the spec definition).")
    print("m16 Waist Girth (ISO 5.3.10, natural waist level) shown for context only.\n")
    print("| person | est. waist h (mm) | GT waist h m43 | ours hull (mm) | GT m102 | d(GT) | m16 (context) | quality |")
    print("|---|---|---|---|---|---|---|---|")
    deltas, dheights = [], []
    for name, est_h, gt_h, ours, gt102, m16, quality in rows:
        def fmt(v):
            return f"{v:.1f}" if v is not None else "—"
        d = ours - gt102 if ours is not None and gt102 is not None else None
        if d is not None:
            deltas.append(d)
        if est_h is not None and gt_h is not None:
            dheights.append(est_h - gt_h)
        print(f"| {name} | {fmt(est_h)} | {fmt(gt_h)} | {fmt(ours)} | {fmt(gt102)} | {fmt(d)} | {fmt(m16)} | {','.join(quality)} |")

    def stats(label, values):
        if not values:
            return
        import statistics

        mean = statistics.mean(values)
        mabs = max(abs(v) for v in values)
        print(f"- {label}: mean {mean:+.1f} mm, max |d| {mabs:.1f} mm, n={len(values)}")

    print("\n## Summary")
    stats("vs GT m102 (definition-matched)", deltas)
    stats("waist height vs m43", dheights)
    return 0


if __name__ == "__main__":
    sys.exit(main())
