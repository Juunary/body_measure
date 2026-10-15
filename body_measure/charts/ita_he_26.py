"""ITA_HE_26 (men's shirt, Konfektionsgröße 40-58) as body targets, and a
body's nearest size on it.

The table is a pinned copy of studio/studio/desktop/size_chart.py, which
stays the source: the desktop simulator is packaged on its own and must
not start importing body_measure. studio/tests/test_ita_he_26_pin.py fails
when the two drift.

What the targets are. The chart lists GARMENT dimensions in cm. A body
target is the garment dimension minus the design ease, the same research
mapping `size_chart.manual_measurements` feeds the polo drafter. Only
size 52 was measured in production; the rest are graded estimates. So the
nearest row is a research mapping from a body to the shirt the line would
cut, not a published body-to-size standard, and its flags say so.

Which keys choose the size. Only chest and neck. The chart grades on
them (Oberweite in pairs of sizes, Kragenweite every size), and both are
girths whose body value is the garment value minus an ease. The chart's
lengths and widths (Taillenlänge, RT Breite) start from garment
landmarks the pipeline does not measure from — on an average SMPL body
they sit 10-15 grading steps from every row — so they are reported as
residuals beside the size and never move it.

One known bias. This pipeline's chest reads about 27 mm above the ISO
definition (decision #36), and an ease-derived target is ISO-like. That
is one full chest step on this chart. `nearest_size` reports the size the
bias-corrected chest would get beside the plain one and never applies it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

CHART = "ITA_HE_26"
SIZES = (40, 42, 44, 46, 48, 50, 52, 54, 56, 58)
REFERENCE = 52

# chart row id -> values for SIZES, cm (studio/studio/desktop/size_chart.py _ROWS)
ROWS = {
    "kragenweite": (35, 36, 37, 38, 39, 40, 41, 42, 43, 44),
    "oberweite_half": (50, 50, 53, 53, 56, 56, 59, 59, 62, 62),
    "taillenweite_half": (47, 47, 50, 50, 53, 49.5, 53.5, 53.5, 57.5, 57.5),
    "saumweite_half": (49, 49, 52, 52, 55, 55, 60, 60, 63, 63),
    "taillenlaenge": (44.6, 44.6, 45.3, 45.3, 46.1, 46.1, 46.8, 46.8, 47.6, 47.6),
    "rt_breite_schulter": (42.2, 42.3, 44, 44.1, 45.8, 45.9, 47.6, 47.7, 49.4, 49.5),
    "oberarmweite_half": (19.6, 19.6, 20.4, 20.4, 21.2, 21.2, 22, 22, 22.8, 22.8),
}


@dataclass(frozen=True)
class Ease:
    """Design ease, mm. Defaults are studio.simulation.config.Design's."""
    chest_mm: float = 100.0
    waist_mm: float = 100.0
    hip_mm: float = 80.0
    arm_mm: float = 60.0


DEFAULT_EASE = Ease()

#: keys whose distance chooses the size
SIZE_KEYS = ("chest_circumference", "neck_circumference")
#: keys reported as residuals against the chosen size, never used to choose it
RESIDUAL_KEYS = ("waist_circumference", "hip_girth", "upper_arm_girth",
                 "across_back_shoulder_width", "back_length")
TARGET_KEYS = SIZE_KEYS + RESIDUAL_KEYS

#: decision #36, Texel n=10; reported beside the plain result, never applied
CHEST_BIAS_MM = 26.9
#: a body further than this from every row, in size steps, is off the chart
MAX_DISTANCE_STEPS = 1.5


def body_targets(size: int, ease: Ease = DEFAULT_EASE) -> dict[str, float]:
    """Body measures (mm) the chart's size implies, as
    `size_chart.manual_measurements` computes them."""
    if size not in SIZES:
        raise ValueError(f"size must be one of {SIZES}; got {size!r}")
    i = SIZES.index(size)
    d = {key: float(values[i]) for key, values in ROWS.items()}
    return {
        "chest_circumference": 20 * d["oberweite_half"] - ease.chest_mm,
        "waist_circumference": 20 * d["taillenweite_half"] - ease.waist_mm,
        "hip_girth": 20 * d["saumweite_half"] - ease.hip_mm,
        "neck_circumference": 10 * d["kragenweite"] - 20,
        "across_back_shoulder_width": 10 * d["rt_breite_schulter"],
        "back_length": 10 * d["taillenlaenge"],
        "upper_arm_girth": 20 * d["oberarmweite_half"] - ease.arm_mm,
    }


def target_matrix(keys=TARGET_KEYS, ease: Ease = DEFAULT_EASE) -> np.ndarray:
    return np.array([[body_targets(s, ease)[k] for k in keys] for s in SIZES])


def size_steps(keys=TARGET_KEYS, ease: Ease = DEFAULT_EASE) -> np.ndarray:
    """Mean change per size over the chart's span, per key: a distance of
    1 means one size of that key. Floored at 1 mm for a flat row."""
    T = target_matrix(keys, ease)
    return np.maximum((T[-1] - T[0]) / (len(SIZES) - 1), 1.0)


@dataclass
class ShirtSize:
    size: int | None
    distance: float | None
    second: int | None
    second_distance: float | None
    keys_used: list[str]
    size_if_chest_bias_holds: int | None
    reason: str
    flags: list[str] = field(default_factory=list)
    #: body minus target of the chosen size, in that key's size steps
    residual_steps: dict[str, float] = field(default_factory=dict)
    chart: str = CHART

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def nearest_size(values: dict[str, float | None], usable: dict[str, bool] | None = None,
                 *, ease: Ease = DEFAULT_EASE) -> ShirtSize:
    """The chart row nearest to a body by chest and neck.

    Distance is the root-mean-square of (body - target) / size step over
    the size keys the body has. The chest is required. Without the neck
    the chest cannot separate the paired sizes (40/42, 44/46, ...), so
    both are named. A body more than MAX_DISTANCE_STEPS from every row is
    refused rather than given an edge size, the same rule as
    `sizing.assign` outside a chart."""
    flags = ["research_mapping_graded_from_size_52", "garment_minus_ease_targets"]

    def ok(key):
        return values.get(key) is not None and (usable is None or usable.get(key, True))

    used = [k for k in SIZE_KEYS if ok(k)]
    if "chest_circumference" not in used:
        return ShirtSize(None, None, None, None, used, None,
                         "the chest is not usable, and the chart grades on it", flags)
    if "neck_circumference" not in used:
        flags.append("neck_unusable_paired_sizes_unresolved")

    T = target_matrix(tuple(used), ease)
    step = size_steps(tuple(used), ease)

    def ranked(body):
        d = np.sqrt((((T - body[None, :]) / step[None, :]) ** 2).mean(axis=1))
        return d, np.argsort(d, kind="stable")

    body = np.array([float(values[k]) for k in used])
    d, order = ranked(body)
    shifted = body.copy()
    shifted[used.index("chest_circumference")] -= CHEST_BIAS_MM
    _, order_b = ranked(shifted)
    best, second = int(order[0]), int(order[1])
    if d[best] > MAX_DISTANCE_STEPS:
        return ShirtSize(None, round(float(d[best]), 3), None, None, used, None,
                         f"the nearest row ({SIZES[best]}) is {d[best]:.1f} size steps away; "
                         "the chart does not reach this body", flags + ["off_chart"])
    if SIZES[int(order_b[0])] != SIZES[best]:
        flags.append("size_moves_if_chest_bias_holds")

    targets = body_targets(SIZES[best], ease)
    all_steps = dict(zip(TARGET_KEYS, size_steps(TARGET_KEYS, ease)))
    residual = {k: round((float(values[k]) - targets[k]) / float(all_steps[k]), 2)
                for k in RESIDUAL_KEYS if ok(k)}
    return ShirtSize(
        size=SIZES[best], distance=round(float(d[best]), 3),
        second=SIZES[second], second_distance=round(float(d[second]), 3),
        keys_used=used, size_if_chest_bias_holds=SIZES[int(order_b[0])],
        reason=(f"nearest {CHART} row by {' and '.join(k.split('_')[0] for k in used)} is "
                f"{SIZES[best]} at {d[best]:.2f} size steps (next {SIZES[second]} at "
                f"{d[second]:.2f})"),
        flags=flags, residual_steps=residual)
