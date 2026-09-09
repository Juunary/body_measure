# -*- coding: utf-8 -*-
"""폴로 셔츠 도시형 생산 라인 분석 — 터미널 진입점.

    python run.py                 전체 보고 (측정 · 설비 · 시뮬레이션)
    python run.py --live          폴로 1벌이 라인을 통과하는 과정 재생
    python run.py --help          옵션 전체

표준 라이브러리만 사용한다. 설치할 것이 없다.
"""
from __future__ import annotations

import argparse
import sys

from polo_line import __version__, live, machines, measurements, passport, simulate, term
from polo_line.spec import TARGET_COST_EUR, TARGET_MINUTES


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run.py",
        description="Polo shirt production line, worked out from the Maß-DPP proposal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples\n"
            "  python run.py                        full report\n"
            "  python run.py --section simulation   simulation only\n"
            "  python run.py --live --dpp           replay the line, then print the DPP JSON\n"
            "  python run.py --embroidery --print   recalculate with the optional modules on\n"
            "  python run.py --runs 20000 -v        more samples, and show the assumptions\n"
        ),
    )
    p.add_argument("--section", choices=["all", "measurements", "machines", "simulation"],
                   default="all", help="which section to print (default: all)")
    p.add_argument("--live", action="store_true", help="replay one shirt travelling down the line")
    p.add_argument("--measurements", metavar="JSON", default=None,
                   help="a body-measure result document; its size block goes "
                        "into the passport")
    p.add_argument("--dpp", action="store_true", help="print the full DPP JSON once --live finishes")
    p.add_argument("--delay", type=float, default=0.10,
                   help="seconds between --live frames; 0 prints everything at once (default: 0.10)")
    p.add_argument("--runs", type=int, default=1000, help="Monte Carlo runs (default: 1000)")
    p.add_argument("--seed", type=int, default=42, help="random seed (default: 42)")
    p.add_argument("--embroidery", action="store_true", help="include the optional ZSK embroidery module")
    p.add_argument("--print", dest="printing", action="store_true",
                   help="include the optional Kornit textile printer")
    p.add_argument("-v", "--verbose", action="store_true", help="show detail and the assumptions behind the numbers")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colour")
    p.add_argument("--version", action="version", version=f"polo-line-sim {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    term.init(use_color=not args.no_color)

    if args.runs < 1:
        print("error: --runs must be at least 1.", file=sys.stderr)
        return 2

    term.title(
        "Polo shirt, urban production line",
        f"Maß-DPP (ITA x ColorDigital) · lot size 1 · target under {TARGET_MINUTES:.0f} min at "
        f"{TARGET_COST_EUR[0]:.0f}-{TARGET_COST_EUR[1]:.0f} EUR",
    )

    if args.live:
        size = (passport.load(args.measurements) if args.measurements
                else passport.UNKNOWN)
        live.run(args.embroidery, args.printing, delay=max(0.0, args.delay),
                 dump_dpp=args.dpp, size=size)
    else:
        if args.section in ("all", "measurements"):
            measurements.report(args.verbose)
        if args.section in ("all", "machines"):
            machines.report(args.verbose)
        if args.section in ("all", "simulation"):
            result = simulate.run(args.runs, args.seed, args.embroidery, args.printing)
            simulate.report(result, args.verbose)

    print()
    print(term.rule())
    print(term.c(
        " From the proposal: Seite 4 (36 min, 13-15 EUR), 37 (table 3 machines), 38 (process flow), 49 (table 4 times)", "grey"))
    print(term.c(
        " Derived: the 12 body measurements — the proposal lists none; from pattern practice and ISO 8559-1", "grey"))
    print(term.c(
        " Assumed: the polo module split, sensor readings, power, cost and worker-occupancy models — see spec.py", "grey"))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
