# -*- coding: utf-8 -*-
"""What the line knows about the customer, and where it got it.

The size is not computed here. It is computed by body-measure from a 3D
scan and arrives as that tool's result document, which this module reads.
The two are separate systems on purpose — measuring a body and running a
line are different jobs — and a JSON hand-off is what the plan's SaaS
architecture describes anyway (Seite 31).

Reading rather than recomputing also keeps one rule intact: the size and
the provenance of the size travel together. A passport that carries the
label but not the chart it came from cannot answer the only question that
matters after a return, which is whether the label was right.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CustomerSize:
    """The size block a passport carries, or the reason it has none."""

    label: str | None = None
    chart: str | None = None
    chart_name: str | None = None
    chart_source: str | None = None
    chart_checked: str | None = None
    chest_mm: float | None = None
    #: the neighbouring label a boundary case could equally have taken
    alternative: str | None = None
    reason: str = ""
    flags: list[str] = field(default_factory=list)
    source_document: str | None = None

    @property
    def known(self) -> bool:
        return self.label is not None

    @property
    def on_boundary(self) -> bool:
        return self.alternative is not None

    def to_dpp(self) -> dict:
        """The customer_spec block. Written the same shape whether or not a
        size is known, so a reader never has to guess why a field is
        missing — the reason is a field.

        The customer's chest girth is NOT in it. The passport records the
        garment, not the body: body dimensions are excluded from the DPP by
        design, and that exclusion is the system's main privacy boundary
        (body-measure `docs/licenses/ethics.md`). `chest_mm` is still read
        and kept on this object, because the boundary case below is decided
        from it — but it is decided here, and only the decision travels.
        """
        if not self.known:
            return {
                "size": None,
                "size_source": "unknown",
                "size_reason": self.reason or "no measurement document supplied",
            }
        block = {
            "size": self.label,
            "size_source": "3d_scan",
            "size_chart": self.chart_name,
            "size_chart_id": self.chart,
            "size_chart_source": self.chart_source,
            "size_chart_checked": self.chart_checked,
            "measurement_document": self.source_document,
        }
        if self.on_boundary:
            # A boundary case is the passport's most useful field after a
            # return: it says the label was one of two, and which.
            block["size_alternative"] = self.alternative
            block["size_note"] = (
                "chest sits within the chart's boundary margin, so "
                f"{self.alternative} was equally defensible at this measurement "
                "quality")
        if self.flags:
            block["measurement_flags"] = self.flags
        return block


UNKNOWN = CustomerSize(
    reason="no measurement document supplied; run body-measure with "
           "--size-chart and pass its result with --measurements")


def load(path: str | Path) -> CustomerSize:
    """Read a body-measure result document and take its size block.

    Refuses rather than guesses: a result written without --size-chart has
    no size, and inventing one here would defeat the point of computing it
    against a cited chart in the first place.
    """
    path = Path(path)
    if not path.is_file():
        return CustomerSize(reason=f"measurement document not found: {path}",
                            source_document=str(path))
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CustomerSize(reason=f"measurement document is not valid JSON: {exc}",
                            source_document=str(path))

    size = (document.get("meta") or {}).get("size")
    if not size:
        return CustomerSize(
            reason="the measurement document carries no size block; it was "
                   "written without --size-chart",
            source_document=str(path))

    return CustomerSize(
        label=size.get("size"),
        chart=size.get("chart"),
        chart_name=size.get("chart_name"),
        chart_source=size.get("chart_source"),
        chart_checked=size.get("chart_checked"),
        chest_mm=size.get("chest_mm"),
        alternative=size.get("alternative"),
        reason=size.get("reason", ""),
        flags=list(size.get("flags") or []),
        source_document=str(path),
    )
