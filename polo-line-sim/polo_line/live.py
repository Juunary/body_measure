# -*- coding: utf-8 -*-
"""Live line — replays in the terminal how the numbers accumulate while one
polo passes through the machines.

It follows the plan's data flow exactly: on entering a module the AI assistant
generates the work instruction (<2 s), sensors read the process parameters in
real time (<1 s), and when the module finishes those readings are committed as
a DPP block and sent to the SaaS.

The replay is produced by `frames()` as a sequence of events and printed by
`run()`. The split exists so that something other than a terminal — a web
page streaming the same line — can render the identical text: every printed
line travels as *segments*, `(text, styles)` pairs, and `run()` colours them
with `term.render` exactly as it always did. Nothing here decides how the
segments look; that stays in `term`.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from typing import Iterator

from . import passport, term
from .spec import (
    CO2_G_PER_KWH,
    DEPRECIATION_EUR,
    DPP_PAYLOAD_KB,
    ENERGY_EUR_PER_KWH,
    LINE_OVERHEAD_KW,
    MATERIAL_EUR,
    SENSOR_CHANNELS,
    SENSOR_HZ,
    TARGET_MINUTES,
    WAGE_EUR_PER_HOUR,
    active_stations,
)

AI_HINT = {
    "cut": "marker projected onto the fabric — align to the pique grain",
    "ovl": "shoulder seam then side seam · lower the feed pressure for knit",
    "lock": "placket alignment guide projected · stitch length set to 2.6 mm",
    "cov": "fold the hem 25 mm · differential feed set automatically",
    "rib": "hold rib stretch at 12-13% — over-stretch warning armed",
    "btn": "three button positions projected · buttonhole direction checked",
    "emb": "hoop mounting position projected",
    "prn": "registration marks found · pre-treatment volume set",
    "fin": "low-temperature profile for knit loaded (-15 °C vs a dress shirt)",
    "qc": "inspect the four seam sections closely",
    "lbl": "payload signed · SaaS hand-off confirmed",
}

STEPS_PER_STATION = 6

# Fixed part of the progress line: indent 6 + clock 5 + space 1 + bar 14 + spaces 2
PREFIX_WIDTH = 28
BAR_WIDTH = 14


def fit_readouts(station, progress: float, limit: int | None):
    """Pick only the readouts that fit the terminal width.

    The progress line is overwritten with \r. If the line exceeds the terminal
    width it wraps to the next row, and \r then returns only to the start of
    the last row — leaving the first row on screen, truncated. One leftover row
    accumulates per frame, so a line meant to be overwritten must fit on one row.

    A limit of None (the final frame) does not truncate: nothing overwrites it
    afterwards, so wrapping leaves no residue, and the readouts should stay
    whole rather than lose information.
    """
    pieces = []
    used = 0
    for label, unit, render in station.readouts:
        value = render(progress)
        plain = f"{label} {value}" + (f" {unit}" if unit else "")
        need = term.dwidth(plain) + (2 if pieces else 0)
        if limit is not None and PREFIX_WIDTH + used + need > limit:
            break
        pieces.append((label, value, unit))
        used += need
    return pieces


def terminal_width() -> int:
    return shutil.get_terminal_size(fallback=(term.WIDTH, 24)).columns


def build_block(station) -> dict:
    """The process block a finished machine contributes to the passport.

    `machine` is taken straight from the station definition. Written by hand
    per block, some get it and the rest do not — 7 of 11 were in fact missing.
    Per-item traceability is why the DPP exists, so which machine did the work
    belongs in every block.
    """
    block = {"module": station.dpp["module"], "machine": station.machine}
    block.update({k: v for k, v in station.dpp.items() if k != "module"})
    block["duration_min"] = round(station.minutes, 2)
    block["energy_kWh"] = round((station.kw + LINE_OVERHEAD_KW) * station.minutes / 60.0, 4)
    return block


def _clock(minutes: float) -> str:
    return f"{int(minutes):02d}:{int((minutes - int(minutes)) * 60):02d}"


def _bar_segments(progress: float) -> list:
    """The same cells `term.bar` draws, as segments. Empty runs are kept:
    `term.c` wraps an empty string in colour codes too, and the printed
    bytes must not change."""
    filled = max(0, min(BAR_WIDTH, round(BAR_WIDTH * progress)))
    return [["█" * filled, ["cyan"]], ["░" * (BAR_WIDTH - filled), ["grey"]]]


def frames(embroidery: bool = False, printing: bool = False,
           size: "passport.CustomerSize | None" = None,
           width: int | None = None) -> Iterator[dict]:
    """The live line as events, in the order they happen.

    Each printable event carries `segments`, a list of `[text, styles]`
    pairs whose styles are `term` style names, so a consumer renders it with
    `term.render` (a terminal) or with a CSS class per style (a browser) and
    shows the same characters either way. `frame` events are the lines the
    terminal overwrites in place; everything else is a line that stays.

    `width` is the row width readouts must fit into; None means the real
    terminal, which is what `run()` wants. A consumer that never overwrites
    a row can pass something generous.
    """
    stations = active_stations(embroidery, printing)
    size = size or passport.UNKNOWN
    nominal = sum(st.minutes for st in stations)
    width = terminal_width() if width is None else width

    yield {
        "type": "header",
        "stations": [st.key for st in stations],
        "n": len(stations),
        "nominal_min": round(nominal, 2),
        "target_min": TARGET_MINUTES,
        "sensor_hz": SENSOR_HZ,
        "sensor_channels": SENSOR_CHANNELS,
        "size": {
            "known": size.known,
            "label": size.label,
            "chart_name": size.chart_name,
            "on_boundary": size.on_boundary,
            "alternative": size.alternative,
            "reason": size.reason,
        },
    }

    elapsed = 0.0
    kwh = 0.0
    blocks: list[dict] = []

    for index, st in enumerate(stations, start=1):
        yield {
            "type": "station_start",
            "index": index, "n": len(stations), "key": st.key,
            "machine": st.machine, "role": st.role, "minutes": st.minutes,
            "hint": AI_HINT.get(st.key, ""),
            "segments": [
                [f"  [{index:02d}/{len(stations)}] ", ["grey"]],
                [st.machine, ["bold", "cyan"]],
                [f"  {st.role}", ["grey"]],
            ],
        }
        yield {
            "type": "line",
            "kind": "ai",
            "segments": [
                ["      ", []],
                ["AI ▸ ", ["yellow"]],
                [AI_HINT.get(st.key, ""), ["grey"]],
            ],
        }

        for step in range(1, STEPS_PER_STATION + 1):
            progress = step / STEPS_PER_STATION
            slice_minutes = st.minutes / STEPS_PER_STATION
            elapsed += slice_minutes
            kwh += (st.kw + LINE_OVERHEAD_KW) * slice_minutes / 60.0

            # Only the final frame shows everything. That line stays on screen
            # with nothing overwriting it afterwards, so length is safe there.
            final = step == STEPS_PER_STATION
            pieces = fit_readouts(st, progress, None if final else width - 1)
            segments = [["      ", []], [_clock(elapsed), ["blue"]], [" ", []]]
            segments += _bar_segments(progress)
            segments.append(["  ", []])
            for i, (label, value, unit) in enumerate(pieces):
                if i:
                    segments.append(["  ", []])
                segments += [[label, ["grey"]], [" ", []], [value, ["yellow"]]]
                if unit:
                    segments.append([f" {unit}", ["grey"]])
            yield {
                "type": "frame",
                "index": index, "key": st.key,
                "step": step, "steps": STEPS_PER_STATION, "final": final,
                "elapsed_min": round(elapsed, 3),
                "kwh": round(kwh, 4),
                "readouts": [{"label": label, "value": value, "unit": unit}
                             for label, value, unit in pieces],
                "segments": segments,
            }

        block = build_block(st)
        blocks.append(block)
        payload = DPP_PAYLOAD_KB * elapsed / nominal

        # Show what was actually written to the passport alongside it. The last
        # readout on screen is the value at that instant and may differ from the
        # recorded one — the finisher reads 70 °C because cooling has finished,
        # while the passport keeps the peak of 164 °C.
        recorded = " · ".join(
            f"{key} {value}" for key, value in block.items()
            if key not in ("module", "machine", "duration_min", "energy_kWh")
        )
        yield {
            "type": "station_done",
            "index": index, "key": st.key,
            "block": block, "blocks": len(blocks), "payload_kb": round(payload, 2),
            "lines": [
                [["      ", []], ["✓ DPP ", ["green"]], [block["module"], ["green"]],
                 [f" · {block['machine']}", ["grey"]]],
                [["        ", []], [f"recorded  {recorded}", ["grey"]]],
                [["        ", []],
                 [f"{len(blocks)} blocks · payload {payload:.1f} kB · validated", ["grey"]]],
            ],
        }

    cost = MATERIAL_EUR + DEPRECIATION_EUR + elapsed / 60.0 * WAGE_EUR_PER_HOUR + kwh * ENERGY_EUR_PER_KWH
    ok = elapsed < TARGET_MINUTES

    def kv_line(label: str, value_segments: list) -> list:
        return [["   ", []], [term.pad(label, 26), ["grey"]]] + value_segments

    yield {
        "type": "totals",
        "elapsed_min": round(elapsed, 2),
        "kwh": round(kwh, 3),
        "co2_g": round(kwh * CO2_G_PER_KWH),
        "cost_eur": round(cost, 2),
        "blocks": len(blocks),
        "payload_kb": DPP_PAYLOAD_KB,
        "target_min": TARGET_MINUTES,
        "ok": ok,
        "lines": [
            kv_line("Flow time", [
                [f"{_clock(elapsed)}  ({elapsed:.1f} min)", ["green" if ok else "red"]],
                [f"   target {TARGET_MINUTES:.0f} min — " + ("met" if ok else "missed"), ["grey"]],
            ]),
            kv_line("Energy and CO2", [[f"{kwh:.3f} kWh · {kwh * CO2_G_PER_KWH:.0f} g", []]]),
            kv_line("Cost (dedicated worker)", [[f"{cost:.2f} €", []]]),
            kv_line("DPP", [[f"{len(blocks)} blocks · {DPP_PAYLOAD_KB:.1f} kB · QR label issued", []]]),
            kv_line("Size in passport",
                    [[f"{size.label}" + (f"  (or {size.alternative})" if size.on_boundary else ""), []]]
                    if size.known else [["none — not recorded", ["yellow"]]]),
        ],
    }

    yield {
        "type": "dpp",
        "document": {
            "dpp_id": "MDPP-2026-POLO-0001",
            "product": "polo shirt · lot size 1",
            "schema": "colordigital/dpp-syntax v0.9",
            # the size and its provenance come from the measurement
            # document; the line does not compute or invent either
            "customer_spec": {**size.to_dpp(),
                              "fit": "regular",
                              "fabric": "organic pique 220g"},
            "process_chain": blocks,
            "totals": {
                "process_min": round(elapsed, 1),
                "energy_kWh": round(kwh, 3),
                "co2_g": round(kwh * CO2_G_PER_KWH),
            },
        },
    }


def run(embroidery: bool = False, printing: bool = False,
        delay: float = 0.10, dump_dpp: bool = False,
        size: "passport.CustomerSize | None" = None) -> None:
    """Print the live line to the terminal, animated when `delay` > 0."""
    size = size or passport.UNKNOWN

    for event in frames(embroidery, printing, size):
        kind = event["type"]

        if kind == "header":
            term.section("L", "Live line — one polo shirt (lot size 1)")
            print()
            term.note(f"{event['n']} modules · nominal flow time {event['nominal_min']:.1f} min"
                      f" · target under {TARGET_MINUTES:.0f} min")
            term.note(f"sensors {SENSOR_HZ:.0f} Hz x {SENSOR_CHANNELS} channels · AI assistant issuing instructions")
            if size.known:
                line = f"customer size {size.label} · {size.chart_name}"
                if size.on_boundary:
                    line += f" · on a band boundary, {size.alternative} equally defensible"
                term.note(line)
            else:
                term.note(term.c(f"customer size unknown — {size.reason}", "yellow"))
            print()

        elif kind in ("station_start", "line"):
            print(term.render(event["segments"]))

        elif kind == "frame":
            line = term.render(event["segments"])
            sys.stdout.write("\r\033[K" + line if delay > 0 else line + "\n")
            sys.stdout.flush()
            if delay > 0:
                time.sleep(delay)
                if event["final"]:
                    print()

        elif kind == "station_done":
            for segments in event["lines"]:
                print(term.render(segments))
            print()

        elif kind == "totals":
            print(term.rule())
            for segments in event["lines"]:
                print(term.render(segments))

        elif kind == "dpp" and dump_dpp:
            print()
            print(term.c("   DPP payload", "bold"))
            for line in json.dumps(event["document"], indent=2, ensure_ascii=False).splitlines():
                print(term.c("   " + line, "grey"))
