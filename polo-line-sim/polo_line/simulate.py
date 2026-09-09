# -*- coding: utf-8 -*-
"""3. 제조 공정에서 나올 수 있는 산업 수치 데이터 예측 시뮬레이션.

세 가지를 계산한다.
  (a) 공정 시간 분포 — 계획서의 36분 목표를 얼마나 지키는가
  (b) 1벌 원가 — 계획서의 13~15 EUR 목표와의 간극, 그리고 그 간극을 메우는 조건
  (c) 라인 밸런싱 — 시간당 2벌에서 20벌 초과까지 확장할 때 필요한 설비/인원 수

(b)의 원가 모델은 두 가지로 나뉜다. 작업자가 셔츠 1벌을 처음부터 끝까지 전담하면
인건비는 흐름시간 전체에 붙는다. 반면 모듈을 병렬로 두면 기계가 도는 동안 작업자는
다른 셔츠를 잡을 수 있으므로, 1벌에 실제로 붙는 인건비는 '손을 붙들고 있는 시간'
(attended time)만큼이다. 계획서가 병렬 모듈 구성을 강조하는 이유가 여기에 있다.
"""
from __future__ import annotations

import math
import random
import statistics as stats
from dataclasses import dataclass

from . import term
from .spec import (
    BENCHMARK_MASS_PRODUCTION,
    CO2_G_PER_KWH,
    DEPRECIATION_EUR,
    DPP_PAYLOAD_KB,
    ENERGY_EUR_PER_KWH,
    LINE_OVERHEAD_KW,
    MATERIAL_EUR,
    SENSOR_CHANNELS,
    SENSOR_HZ,
    SEWING_KEYS,
    TARGET_COST_EUR,
    TARGET_MINUTES,
    WAGE_EUR_PER_HOUR,
    Station,
    active_stations,
)

CV = 0.12            # 가정: 모듈 처리 시간의 변동계수
REWORK_RATE = 0.06   # 가정: 카메라 QC 에서 잡히는 재작업 비율
REWORK_MIN = (3.0, 8.0)
UTILISATION = 0.85   # 가정: 전환·대기를 뺀 실가동률


@dataclass
class Result:
    runs: int
    stations: list[Station]
    flow_times: list[float]     # 벌당 흐름시간 (분)
    energies: list[float]       # 벌당 에너지 (kWh)
    reworks: int

    @property
    def mean_time(self) -> float:
        return stats.fmean(self.flow_times)

    @property
    def sd_time(self) -> float:
        return stats.pstdev(self.flow_times)

    def pct(self, q: float) -> float:
        ordered = sorted(self.flow_times)
        idx = min(len(ordered) - 1, int(len(ordered) * q))
        return ordered[idx]

    @property
    def on_target(self) -> float:
        """36분 목표를 지킨 비율 (%)."""
        return 100.0 * sum(1 for t in self.flow_times if t < TARGET_MINUTES) / len(self.flow_times)

    @property
    def mean_energy(self) -> float:
        return stats.fmean(self.energies)

    @property
    def attended_minutes(self) -> float:
        """1벌에 작업자가 실제로 붙어 있는 시간 (분)."""
        return sum(st.minutes * st.attended for st in self.stations)

    @property
    def nominal_minutes(self) -> float:
        return sum(st.minutes for st in self.stations)


def run(runs: int = 1000, seed: int = 42, embroidery: bool = False,
        printing: bool = False) -> Result:
    rng = random.Random(seed)
    chosen = active_stations(embroidery, printing)
    flow, energy, reworks = [], [], 0

    for _ in range(runs):
        total = 0.0
        kwh = 0.0
        for st in chosen:
            minutes = max(0.4, rng.gauss(st.minutes, st.minutes * CV))
            total += minutes
            kwh += (st.kw + LINE_OVERHEAD_KW) * minutes / 60.0
        if rng.random() < REWORK_RATE:
            extra = rng.uniform(*REWORK_MIN)
            total += extra
            kwh += (0.55 + LINE_OVERHEAD_KW) * extra / 60.0
            reworks += 1
        flow.append(total)
        energy.append(kwh)

    return Result(runs, chosen, flow, energy, reworks)


# ---------------------------------------------------------------------------
# 원가
# ---------------------------------------------------------------------------
def unit_cost(minutes: float, kwh: float) -> dict[str, float]:
    labour = minutes / 60.0 * WAGE_EUR_PER_HOUR
    energy = kwh * ENERGY_EUR_PER_KWH
    return {
        "labour": labour,
        "energy": energy,
        "material": MATERIAL_EUR,
        "depreciation": DEPRECIATION_EUR,
        "total": labour + energy + MATERIAL_EUR + DEPRECIATION_EUR,
    }


def required_attended_minutes(target_eur: float, kwh: float) -> float:
    """목표 원가를 맞추려면 작업자 실투입 시간이 몇 분 이하여야 하는가."""
    room = target_eur - MATERIAL_EUR - DEPRECIATION_EUR - kwh * ENERGY_EUR_PER_KWH
    return max(0.0, room / WAGE_EUR_PER_HOUR * 60.0)


# ---------------------------------------------------------------------------
# 라인 밸런싱
# ---------------------------------------------------------------------------
def balance(stations: list[Station], rate_per_hour: float,
            attended: float) -> dict:
    """목표 생산율을 맞추기 위한 모듈별 대수와 필요 인원.

    흐름 라인의 생산율은 공정 시간의 합이 아니라 가장 느린 한 공정이 정한다.
    takt(1벌을 내보내야 하는 간격)보다 긴 공정은 그 배수만큼 병렬로 둔다.
    """
    takt = 60.0 * UTILISATION / rate_per_hour
    counts = {st.key: max(1, math.ceil(st.minutes / takt)) for st in stations}
    workers = max(1, math.ceil(attended / takt))
    slowest = max(stations, key=lambda st: st.minutes / counts[st.key])
    return {
        "rate": rate_per_hour,
        "takt": takt,
        "counts": counts,
        "machines": sum(counts.values()),
        "workers": workers,
        "bottleneck": slowest,
        "bottleneck_takt": slowest.minutes / counts[slowest.key],
    }


def short(station: Station) -> str:
    """표 안에서 쓰는 짧은 기계 이름."""
    return station.machine.split(" ")[0]


def max_rate_single_line(stations: list[Station]) -> float:
    """각 설비를 1대씩만 둔 선형 구성의 최대 생산율 (벌/시간)."""
    slowest = max(st.minutes for st in stations)
    return 60.0 / slowest * UTILISATION


# ---------------------------------------------------------------------------
# 보고
# ---------------------------------------------------------------------------
def report(result: Result, verbose: bool = False) -> None:
    term.section("3", "Predicted production figures")
    print()
    term.note(f"Monte Carlo, {result.runs:,} shirts · module time CV {CV:.0%} · rework {REWORK_RATE:.0%} (assumed)")
    print()

    # (a) 공정 시간 -----------------------------------------------------
    print(term.c("   (a) Flow time", "bold"))
    print()
    on_target = result.on_target
    time_style = "green" if result.mean_time < TARGET_MINUTES else "red"
    term.kv("Mean flow time", term.c(f"{result.mean_time:.1f} min", time_style)
            + term.c(f"   (sd {result.sd_time:.1f})", "grey"))
    term.kv("Median / P95", f"{result.pct(0.50):.1f} / {result.pct(0.95):.1f} min")
    term.kv("Plan target", f"under {TARGET_MINUTES:.0f} min"
            + term.c(f"   (mass-production benchmark {BENCHMARK_MASS_PRODUCTION:.0f} min)", "grey"))
    term.kv("Shirts under target", term.c(f"{on_target:.1f}%", "green" if on_target > 90 else "yellow")
            + "  " + term.bar(on_target, 100, 24, "green" if on_target > 90 else "yellow"))
    term.kv("Rework", f"{result.reworks} of {result.runs} ({result.reworks / result.runs:.1%})")

    print()
    print(term.c("   Where the time goes", "bold"))
    rows = []
    for st in result.stations:
        share = st.minutes / result.nominal_minutes * 100
        rows.append([
            st.machine,
            f"{st.minutes:.1f}",
            f"{st.attended:.0%}",
            f"{st.minutes * st.attended:.2f}",
            term.bar(st.minutes, 8.0, 18, "cyan"),
            f"{share:.0f}%",
        ])
    term.table(["Machine", "min", "Worker", "Attended", "", "Share"], rows,
               aligns=["left", "right", "right", "right", "left", "right"])

    # (b) 원가 -----------------------------------------------------------
    print()
    print(term.c("   (b) Cost per shirt — the plan wants 13-15 EUR", "bold"))
    print()
    kwh = result.mean_energy
    dedicated = unit_cost(result.mean_time, kwh)
    parallel = unit_cost(result.attended_minutes, kwh)

    rows = []
    for label, model, minutes in (
        ("Worker owns the shirt", dedicated, result.mean_time),
        ("Parallel modules, hands-on time only", parallel, result.attended_minutes),
    ):
        hit = TARGET_COST_EUR[0] <= model["total"] <= TARGET_COST_EUR[1]
        verdict = term.c("on target", "green") if hit else term.c("over target", "red")
        rows.append([
            label,
            f"{minutes:.1f} min",
            f"{model['labour']:.2f}",
            f"{model['material']:.2f}",
            f"{model['depreciation']:.2f}",
            f"{model['energy']:.2f}",
            term.c(f"{model['total']:.2f} €", "bold"),
            verdict,
        ])
    term.table(["Labour model", "Paid time", "Labour", "Material", "Depr.", "Energy", "Total", ""], rows,
               aligns=["left", "right", "right", "right", "right", "right", "right", "left"])

    print()
    need = required_attended_minutes(TARGET_COST_EUR[1], kwh)
    gap = result.attended_minutes - need
    term.kv("To reach 15 EUR", term.c(f"attended time must fall to {need:.1f} min", "yellow"))
    term.kv("Attended today", f"{result.attended_minutes:.1f} min")
    if gap > 0:
        sewing = sum(st.minutes * st.attended for st in result.stations if st.key in SEWING_KEYS)
        term.kv("Gap to close", term.c(f"{gap:.1f} min", "red")
                + term.c(f"   ({gap / sewing:.0%} of the {sewing:.1f} min spent sewing)", "grey"))
        print()
        term.note("Sewing is the constraint. At the cutter, press and camera the worker can step away while")
        term.note("the machine runs; at the overlock, lockstitch, coverstitch and rib feed they cannot.")
        term.note("If the plan's AI assistant does not shorten that stretch, the cost target is out of reach.")

        print()
        print(term.c("   Cost if the AI assistant cuts sewing time", "bold"))
        rows = []
        for cut in (0.0, 0.10, 0.20, 0.30, 0.40, 0.50):
            att = result.attended_minutes - sewing * cut
            total = unit_cost(att, kwh)["total"]
            hit = total <= TARGET_COST_EUR[1]
            rows.append([
                f"{cut:.0%}",
                f"{att:.1f} min",
                (term.c(f"{total:.2f} €", "green") if hit else f"{total:.2f} €"),
                term.bar(total, 22, 22, "green" if hit else "red"),
                term.c("in range", "green") if hit else "",
            ])
        term.table(["Cut", "Attended", "Per shirt", "", ""], rows,
                   aligns=["right", "right", "right", "left", "left"])

    # (c) 라인 확장 ------------------------------------------------------
    print()
    print(term.c("   (c) Scaling — the plan spans <2 shirts/h startups to >20 shirts/h labels", "bold"))
    print()
    single = max_rate_single_line(result.stations)
    term.kv("One machine of each type", f"{single:.1f} shirts/h at most"
            + term.c(f"   (utilisation {UTILISATION:.0%} assumed)", "grey"))

    print()
    plans = [(rate, balance(result.stations, rate, result.attended_minutes)) for rate in (2, 5, 10, 20)]
    rows = []
    for rate, b in plans:
        rows.append([
            f"{rate}/h",
            f"{b['takt']:.1f} min",
            f"{b['machines']}",
            f"{b['workers']}",
            f"{short(b['bottleneck'])} ({b['bottleneck_takt']:.1f} min)",
        ])
    term.table(["Rate", "Takt", "Machines", "Workers", "Bottleneck once duplicated"], rows,
               aligns=["right", "right", "right", "right", "left"])

    print()
    print(term.c("   What has to be duplicated", "bold"))
    for rate, b in plans:
        dup = [(st, b["counts"][st.key]) for st in result.stations if b["counts"][st.key] > 1]
        if not dup:
            print(f"     {term.pad(f'{rate}/h', 8, 'right')}  " + term.c("nothing — one of each is enough", "grey"))
            continue
        detail = " · ".join(f"{short(st)}×{n}" for st, n in dup)
        print(f"     {term.pad(f'{rate}/h', 8, 'right')}  " + detail)

    print()
    term.note("Takt is the interval the line must release a shirt at; anything slower is duplicated to match.")
    term.note("As the rate climbs the bottleneck moves off the overlock (8 min) onto lockstitch and")
    term.note("finishing (5 min each) — the Veit press has to be duplicated alongside the sewing cells.")

    # (d) 데이터 --------------------------------------------------------
    print()
    print(term.c("   (d) Data captured and footprint", "bold"))
    print()
    co2 = kwh * CO2_G_PER_KWH
    points = result.mean_time * 60 * SENSOR_HZ * SENSOR_CHANNELS
    raw_kb = points * 0.05
    term.kv("Energy per shirt", f"{kwh:.3f} kWh")
    term.kv("CO2, production stage", f"{co2:.0f} g" + term.c(f"   (grid {CO2_G_PER_KWH:.0f} g/kWh assumed)", "grey"))
    term.kv("Sensor points", f"{points:,.0f}" + term.c(f"   ({SENSOR_HZ:.0f} Hz x {SENSOR_CHANNELS} channels x {result.mean_time:.0f} min)", "grey"))
    term.kv("Raw to passport", f"{raw_kb:,.0f} kB → DPP {DPP_PAYLOAD_KB:.0f} kB"
            + term.c(f"   ({raw_kb / DPP_PAYLOAD_KB:.0f}:1)", "grey"))

    b10 = balance(result.stations, 10, result.attended_minutes)
    annual = 10 * 8 * 250 * DPP_PAYLOAD_KB / 1e6
    term.kv("DPP volume per year", f"{annual:.2f} GB for one store"
            + term.c(f"   (10/h x 8h x 250 days, {b10['machines']} machines)", "grey"))

    if verbose:
        print()
        print(term.c("   Assumptions", "bold"))
        for label, value in (
            ("Wage incl. overhead", f"{WAGE_EUR_PER_HOUR:.2f} EUR/h"),
            ("Electricity", f"{ENERGY_EUR_PER_KWH:.2f} EUR/kWh"),
            ("Material", f"{MATERIAL_EUR:.2f} EUR"),
            ("Depreciation share", f"{DEPRECIATION_EUR:.2f} EUR"),
            ("Standing line load", f"{LINE_OVERHEAD_KW:.2f} kW"),
            ("Utilisation", f"{UTILISATION:.0%}"),
            ("Processing time CV", f"{CV:.0%}"),
            ("Rework rate", f"{REWORK_RATE:.0%}"),
        ):
            term.kv(label, value)
