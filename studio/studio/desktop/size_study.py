"""Size study: how fabric map, time, energy, power and cost change over ITA_HE_26 sizes 40-58.

    python -m studio.desktop.size_study --out runs/size-study

Every size runs the desktop plan with step times graded from the measured size 52 (see
`shirt_steps.duration_at`) and the Herrenhemd pattern graded from the size-52 pieces. The marker
search needs the nesting package's compiled earcut library; when that cannot load, the study
still reports graded piece areas and the area lower bound, and says so.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import shirt_steps, size_chart
from .engine import build_plan, resources_at

STUDIO = Path(__file__).parents[2]
DEFAULT_NESTING = Path(__file__).parents[4] / "nesting"
RELATIVE = ("sewing_duration_s", "duration_s", "energy_kwh", "mean_power_kw", "cost_eur", "thread_used_m",
            "sewn_length_mm", "stitches", "net_piece_area_m2", "marker_length_mm", "fabric_m2", "fabric_eur")


def load_nesting(root: Path):
    sys.path.insert(0, str(root))
    import nesting.grading as grading
    import nesting.pieces as pieces
    try:
        import nesting.search as search
    except ImportError as exc:   # e.g. a blocked compiled dependency
        return grading, pieces, None, f"{type(exc).__name__}: {exc}"
    return grading, pieces, search, None


def plan_row(size, base) -> dict:
    config = size_chart.config_for(size, base)
    plan = build_plan(size_chart.document(size), config)
    t, end = plan["totals"], resources_at(plan, plan["totals"]["duration_s"])
    row = {"size": size, "intl": size_chart.INTL[size], "plan_id": plan["plan_id"],
           "sewing_duration_s": t["sewing_duration_s"], "cutting_duration_s": t["cutting_duration_s"],
           "button_duration_s": t["button_duration_s"], "qc_duration_s": t["qc_duration_s"],
           "duration_s": t["duration_s"], "sewn_length_mm": t["sewn_length_mm"], "stitches": t["stitches"],
           "energy_kwh": end["energy_kwh"], "mean_power_kw": end["energy_kwh"] * 3600 / t["duration_s"],
           "co2e_g": end["co2e_g"], "cost_eur": end["cost_eur"], "labour_time_s": end["labour_time_s"],
           "thread_used_m": end["thread_used_m"], "polo_fabric_m2": sum(end["fabric_used_m2"].values())}
    row.update({f"energy_{k}_kwh": v for k, v in end["energy_breakdown_kwh"].items()})
    row.update({f"cost_{k}_eur": v for k, v in end["cost_breakdown_eur"].items()})
    row.update({f"step_{r['no']:02d}_s": r["duration_s"] for r in plan["work_steps"] if r["scheduled"]})
    return row


def fabric_row(size, grading, pieces, search, args, resources) -> dict:
    graded = grading.grade(pieces, size_chart.piece_factors(size))
    area = sum(p.area_mm2 * p.quantity for p in graded)
    usable = args.width - 2 * args.margin
    row = {"net_piece_area_m2": area / 1e6, "lower_bound_length_mm": area / usable}
    row.update({f"area_{p.id.lower()}_cm2": p.area_mm2 / 100 for p in graded})
    if search is not None:
        settings = search.Settings(fabric_width_mm=args.width, gap_mm=args.gap, edge_margin_mm=args.margin,
                                   rotations=tuple(int(r) for r in args.rotations.split(",")),
                                   iterations=args.iterations, time_limit_s=args.time_limit,
                                   beam=args.beam, window=args.window, seed=args.seed)
        totals = search.nest(graded, settings)["totals"]
        length = totals["length_mm"]
        row.update(marker_length_mm=length, efficiency_pct=totals["efficiency_pct"],
                   fabric_m2=length * args.width / 1e6,
                   fabric_eur=length * args.width / 1e6 * resources["body_eur_m2"])
    return row


def add_relative(rows):
    ref = next(r for r in rows if r["size"] == size_chart.REFERENCE)
    for r in rows:
        for key in RELATIVE:
            if key in r and ref.get(key):
                r[f"{key}_vs52_pct"] = (r[key] / ref[key] - 1) * 100


def report(rows, args, note) -> str:
    def table(title, cols):
        head = "| size | " + " | ".join(label for label, _, _ in cols) + " |\n|" + "---|" * (len(cols) + 1) + "\n"
        body = ""
        for r in rows:
            cells = [f"{r[key]:{fmt}}" if key in r else "-" for _, key, fmt in cols]
            body += f"| {r['size']} ({r['intl']}) | " + " | ".join(cells) + " |\n"
        return f"### {title}\n\n{head}{body}\n"

    out = [f"# Herrenhemd size study ({size_chart.CHART}, reference size {size_chart.REFERENCE})\n",
           "Step times are graded from the measured size 52 with fixed handling time plus needle time "
           f"proportional to the sewn length ({args.stitches_per_min:.0f} stitches/min). "
           "Other sizes are estimates until they are measured.\n",
           "Chart correction: row 1/2 Ä-Saumweite shows 12.0 at sizes 48, 50 and 54; 19.0 is used instead.\n"]
    if note:
        out.append(f"**Marker search not run:** {note}. Fabric columns show net piece area and the "
                   "area lower bound only.\n")
    out.append(table("Time", [("sewing s", "sewing_duration_s", ".1f"), ("total s", "duration_s", ".1f"),
                              ("total vs 52 %", "duration_s_vs52_pct", "+.2f"), ("sewn m", "sewn_length_mm", ".0f"),
                              ("stitches", "stitches", ".0f")]))
    out.append(table("Energy, power, cost", [("energy kWh", "energy_kwh", ".3f"), ("vs 52 %", "energy_kwh_vs52_pct", "+.2f"),
                                            ("mean kW", "mean_power_kw", ".3f"), ("CO2e g", "co2e_g", ".1f"),
                                            ("cost EUR", "cost_eur", ".3f"), ("thread m", "thread_used_m", ".1f")]))
    out.append(table("Fabric map (Herrenhemd pieces)", [("net m2", "net_piece_area_m2", ".4f"),
                                                       ("vs 52 %", "net_piece_area_m2_vs52_pct", "+.2f"),
                                                       ("LB length mm", "lower_bound_length_mm", ".0f"),
                                                       ("marker mm", "marker_length_mm", ".0f"),
                                                       ("util %", "efficiency_pct", ".1f"), ("fabric EUR", "fabric_eur", ".2f")]))
    out.append(table("Piece areas cm2", [(p.lower(), f"area_{p.lower()}_cm2", ".0f") for p in size_chart.PIECE_AXES]))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=STUDIO / "runs" / "size-study")
    ap.add_argument("--nesting-root", type=Path, default=DEFAULT_NESTING)
    ap.add_argument("--sizes", default=",".join(map(str, size_chart.SIZES)))
    ap.add_argument("--config", type=Path, default=STUDIO / "examples" / "cutting-config.json")
    ap.add_argument("--width", type=float, default=1007.)
    ap.add_argument("--gap", type=float, default=5.)
    ap.add_argument("--margin", type=float, default=5.)
    ap.add_argument("--rotations", default="0,180")
    ap.add_argument("--iterations", type=int, default=1500)
    ap.add_argument("--time-limit", type=float, default=120.)
    ap.add_argument("--beam", type=int, default=16)
    ap.add_argument("--window", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-nesting", action="store_true")
    args = ap.parse_args(argv)
    sizes = [int(s) for s in args.sizes.split(",")]
    if size_chart.REFERENCE not in sizes:
        sizes.append(size_chart.REFERENCE)   # the percentage columns need the reference
    sizes.sort()
    base = json.loads(args.config.read_text(encoding="utf-8"))
    args.stitches_per_min = base.get("machine", {}).get("stitches_per_min", shirt_steps.DEFAULT_STITCHES_PER_MIN)
    grading, pieces_mod, search, note = load_nesting(args.nesting_root)
    if args.no_nesting:
        search, note = None, "disabled with --no-nesting"
    _, pieces = pieces_mod.load_pieces(args.nesting_root / "examples" / "hemd-pieces.json")
    resources = size_chart.config_for(sizes[0], base)["resources"]
    rows = []
    for size in sizes:
        row = plan_row(size, base)
        row.update(fabric_row(size, grading, pieces, search, args, resources))
        rows.append(row)
        print(f"size {size}: sewing {row['sewing_duration_s']:.1f} s, energy {row['energy_kwh']*1000:.1f} Wh, "
              f"net fabric {row['net_piece_area_m2']:.4f} m2", flush=True)
    add_relative(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with (args.out / "size-study.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows(rows)
    (args.out / "size-study.json").write_text(json.dumps(
        {"chart": size_chart.CHART, "reference": size_chart.REFERENCE, "corrections": size_chart.CORRECTIONS,
         "marker_note": note, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    (args.out / "size-study.md").write_text(report(rows, args, note), encoding="utf-8")
    print(f"wrote {args.out}")
    return rows


if __name__ == "__main__":
    main()
