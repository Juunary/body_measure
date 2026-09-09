"""Stage `replay`: polo-line's live line, event by event.

`polo_line.live.frames()` yields the same lines `python run.py --live`
prints; this forwards them and paces the frames. Nothing about the line
is computed here — the studio only chooses how fast to show it.
"""
from __future__ import annotations

import time

from . import events as ev
from . import paths  # noqa: F401
from .jobs import Job
from polo_line import live, passport

PHASE = ev.PHASE_REPLAY
ROW_WIDTH = 160        # the browser never overwrites a wrapped row


def run_replay(job: Job) -> None:
    replay = job.params.get("replay") or {}
    delay = max(0.0, float(replay.get("delay", 0.1)))
    embroidery = bool(replay.get("embroidery"))
    printing = bool(replay.get("printing"))
    size = job.customer_size or passport.UNKNOWN

    job.state = "replaying"
    job.stage(PHASE, "replay", "start",
              f"{'with' if embroidery else 'without'} embroidery · "
              f"{'with' if printing else 'without'} DTG print · delay {delay:.2f} s")
    blocks, totals, document = [], None, None
    for event in live.frames(embroidery, printing, size, width=ROW_WIDTH):
        kind = event["type"]
        if kind == "header":
            job.line(PHASE, ev.seg((" [L] ", "yellow"), ("Live line — one polo shirt (lot size 1)", "bold")), "head")
            job.line(PHASE, ev.note(f"{event['n']} modules · nominal flow time {event['nominal_min']:.1f} min"
                                    f" · target under {event['target_min']:.0f} min"))
            job.line(PHASE, ev.note(f"sensors {event['sensor_hz']:.0f} Hz x {event['sensor_channels']} channels"
                                    " · AI assistant issuing instructions"))
            s = event["size"]
            if s["known"]:
                text = f"customer size {s['label']} · {s['chart_name']}"
                if s["on_boundary"]:
                    text += f" · on a band boundary, {s['alternative']} equally defensible"
                job.line(PHASE, ev.note(text))
            else:
                job.line(PHASE, ev.seg(("   · ", "grey"), (f"customer size unknown — {s['reason']}", "yellow")))
            job.emit("header", PHASE, **{k: v for k, v in event.items() if k != "type"})
        elif kind == "station_start":
            job.emit("station_start", PHASE, **{k: v for k, v in event.items() if k not in ("type", "segments")})
            job.line(PHASE, event["segments"], "head")
        elif kind == "line":
            job.line(PHASE, event["segments"], event.get("kind", "note"))
        elif kind == "frame":
            job.emit("frame", PHASE, station_index=event["index"], key=event["key"],
                     step=event["step"], steps=event["steps"], final=event["final"],
                     elapsed_min=event["elapsed_min"], kwh=event["kwh"],
                     readouts=event["readouts"], segments=event["segments"])
            if delay > 0:
                time.sleep(delay)
        elif kind == "station_done":
            blocks.append(event["block"])
            job.emit("station_done", PHASE, index=event["index"], key=event["key"],
                     block=event["block"], blocks=event["blocks"], payload_kb=event["payload_kb"])
            for segments in event["lines"]:
                job.line(PHASE, segments, "done")
        elif kind == "totals":
            totals = {k: v for k, v in event.items() if k not in ("type", "lines")}
            job.line(PHASE, ev.seg(("─" * 96, "grey")), "rule")
            for segments in event["lines"]:
                job.line(PHASE, segments, "kv")
            job.emit("totals", PHASE, **totals)
        elif kind == "dpp":
            document = event["document"]
            job.emit("dpp", PHASE, document=document)
    job.replay = {"blocks": blocks, "totals": totals, "document": document,
                  "embroidery": embroidery, "printing": printing}
    job.stage(PHASE, "replay", "done")
    job.state = "replayed"
