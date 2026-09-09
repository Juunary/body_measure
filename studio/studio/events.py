"""One event vocabulary for everything the page streams.

Every event is `{id, t, job, phase, type, ...}`. The terminal panel draws
only `stage`, `line`, `frame` and `error`; every other type feeds a panel
(the viewer, the table, the size card, the QR card).

A printable line travels as *segments*: `[[text, [styles]], ...]`, where
the style names are polo-line's `term._CODES` keys (`bold dim red green
yellow blue cyan grey`). The browser maps each to a CSS class; the
terminal maps each to an ANSI code. The measurement phase uses the same
shape so the panel is one component.
"""
from __future__ import annotations

PHASE_MEASURE = "measure"
PHASE_SIZE = "size"
PHASE_REPLAY = "replay"
PHASE_QR = "qr"

STYLES = ("bold", "dim", "red", "green", "yellow", "blue", "cyan", "grey")


def seg(*pairs) -> list:
    """`seg("text", ("more", "grey"), ("bold text", "bold", "cyan"))`."""
    out = []
    for pair in pairs:
        if isinstance(pair, str):
            out.append([pair, []])
        else:
            text, *styles = pair
            out.append([text, list(styles)])
    return out


def note(text: str) -> list:
    return seg(("   · " + text, "grey"))


def stage_line(index: int, total: int, name: str, detail: str = "") -> list:
    return seg((f"  [{index}/{total}] ", "grey"), (name, "bold", "cyan"),
               (f"  {detail}" if detail else "", "grey"))


def done_line(text: str, elapsed_s: float | None = None) -> list:
    tail = f"  {elapsed_s:.1f} s" if elapsed_s is not None else ""
    return seg("      ", ("✓ ", "green"), (text, "green"), (tail, "grey"))


def warn_line(text: str) -> list:
    return seg("      ", ("! ", "yellow"), (text, "yellow"))
