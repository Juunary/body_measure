"""The human-range gate: the core's last word before a number leaves it.

Two values reached `accepted` that no body could have. A waist of 140.9 mm
came from a jacket-fold loop winning a minimum (decision #22), and a chest
of 3808 mm came from a horizontal loop around a torso *and both
outstretched arms* on a T-posed CAPE body (decision #34). The first was a
trust failure and was fixed by trusting fewer loops. The second was not:
the loop was correctly selected, the girth correctly measured, and no rule
about which slice to believe can catch it. What was missing was the
simplest check of all — is this a length a human being has?

Decision #22 argued against exactly this gate, on the grounds that a range
check would have masked the waist bug rather than fixing it. That was
right then and stays right: the gate is the last line, not the first, and
it runs *after* every trust rule, never instead of one. What it adds is
that a number nothing else caught cannot leave the core pretending to be a
measurement.

It refuses; it never corrects. Out of range means null plus a flag, with
the raw contour left in place so the failure can still be read. A gate
that clamped, or that re-shopped for the next-largest slice, would be
inventing a body — and re-shopping is the thing decision #22 forbade.
"""
from __future__ import annotations

from functools import lru_cache

from ..result import MeasurementValue
from ..spec import Spec, load_spec

#: Set when a value falls outside the spec's `plausible_mm` for it.
OUTSIDE_RANGE = "outside_plausible_range"
#: Set when the spec names no bound. A test pins that the shipped spec
#: bounds every measurement, so this marks a spec regression, not a body.
NO_RANGE = "plausible_range_unspecified"


@lru_cache(maxsize=1)
def _default_spec() -> Spec:
    return load_spec()


def gate_human_range(
    measurements: dict[str, MeasurementValue], spec: Spec | None = None
) -> dict[str, MeasurementValue]:
    """Reject any value outside its spec bound. Mutates and returns the
    same dict, so it can wrap a producer without copying.

    Idempotent: running it twice adds nothing the first run did not.
    """
    spec = spec or _default_spec()
    for name, value in measurements.items():
        if value is None or value.selected_value_mm is None:
            continue
        entry = spec.measurements.get(name)
        bounds = entry.plausible_mm if entry is not None else None
        if bounds is None:
            if NO_RANGE not in value.quality:
                value.quality = [f for f in value.quality if f != "ok"] + [NO_RANGE]
            continue
        lo, hi = bounds
        raw = float(value.selected_value_mm)
        if lo <= raw <= hi:
            continue
        # The number is kept in the flag rather than the field: a reader
        # needs to know WHAT was refused to debug it, and a consumer that
        # checks selected_value_mm first must not see it.
        value.selected_value_mm = None
        value.disposition = "rejected"
        value.quality = [f for f in value.quality if f != "ok"] + [
            OUTSIDE_RANGE, f"raw_value_{round(raw)}mm"
        ]
    return measurements
