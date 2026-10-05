"""Size chart ITA_HE_26 (men's shirt, Konfektionsgröße 40-58) and its mapping to the simulator.

The chart is transcribed from the company size table. Only column 52 (size L) was measured
in production; every other size is a research estimate graded from it.
All chart values are centimetres.
"""
from __future__ import annotations

from ..simulation.config import Design

CHART = "ITA_HE_26"
SIZES = (40, 42, 44, 46, 48, 50, 52, 54, 56, 58)
REFERENCE = 52
INTL = dict(zip(SIZES, ("XS", "XS", "S", "S", "M", "M", "L", "L", "XL", "XL")))

# chart row id -> (German row label, values for SIZES)
_ROWS = {
    "kragenweite": ("KRAGENWEITE", (35, 36, 37, 38, 39, 40, 41, 42, 43, 44)),
    "oberweite_half": ("1/2 OBERWEITE", (50, 50, 53, 53, 56, 56, 59, 59, 62, 62)),
    "taillenweite_half": ("1/2 TAILLENWEITE", (47, 47, 50, 50, 53, 49.5, 53.5, 53.5, 57.5, 57.5)),
    "saumweite_half": ("1/2 SAUMWEITE", (49, 49, 52, 52, 55, 55, 60, 60, 63, 63)),
    "laenge_hm": ("LÄNGE HM", (75, 75, 75, 75, 80, 80, 80, 80, 80, 80)),
    "taillenlaenge": ("TAILLENLÄNGE", (44.6, 44.6, 45.3, 45.3, 46.1, 46.1, 46.8, 46.8, 47.6, 47.6)),
    "aermellaenge": ("ÄRMELLÄNGE", (23.5, 23.5, 24, 24, 24.5, 24.5, 25, 25, 25.5, 25.5)),
    "aermellaenge_ab_hm": ("ÄRMELLÄNGE ab HM", (44.6, 44.7, 46, 46.1, 47.4, 47.5, 48.8, 48.9, 50.2, 50.3)),
    "schulterbreite_vt": ("SCHULTERBREITE an VT", (14.6, 14.6, 15, 15, 15.4, 15.4, 15.8, 15.8, 16.2, 16.2)),
    "rt_breite_schulter": ("RT BREITE an natürlicher Schulter", (42.2, 42.3, 44, 44.1, 45.8, 45.9, 47.6, 47.7, 49.4, 49.5)),
    "rt_breite_passe": ("RT BREITE an Passe", (41.5, 41.5, 43.5, 43.5, 45.5, 45.5, 47.5, 47.5, 49.5, 49.5)),
    "oberarmweite_half": ("1/2 OBERARMWEITE", (19.6, 19.6, 20.4, 20.4, 21.2, 21.2, 22, 22, 22.8, 22.8)),
    "ae_saumweite_half": ("1/2 Ä-SAUMWEITE", (18.5, 18.5, 18.5, 18.5, 12, 12, 19, 12, 19.5, 19.5)),
    "knopfleiste": ("BREITE KNOPFLEISTE", (3.5,) * 10),
}

# The sleeve-hem row shows 12.0 at sizes 48, 50 and 54 between values of 18.5-19.5. That is read
# as a transcription error; the neighbouring value 19.0 (size 52) is used instead.
CORRECTIONS = {"ae_saumweite_half": {48: 19.0, 50: 19.0, 54: 19.0}}


def _used(key: str) -> tuple[float, ...]:
    fixes = CORRECTIONS.get(key, {})
    return tuple(float(fixes.get(size, v)) for size, v in zip(SIZES, _ROWS[key][1]))


DIMS = {key: _used(key) for key in _ROWS}
RAW = {key: tuple(float(v) for v in row[1]) for key, row in _ROWS.items()}
LABELS = {key: row[0] for key, row in _ROWS.items()}


def check_size(size) -> int:
    if size not in SIZES:
        raise ValueError(f"size must be one of {', '.join(map(str, SIZES))}; got {size!r}")
    return int(size)


def dims(size: int) -> dict[str, float]:
    i = SIZES.index(check_size(size))
    return {key: values[i] for key, values in DIMS.items()}


def ratio(dim: str, size: int, reference: int = REFERENCE) -> float:
    return dims(size)[dim] / dims(reference)[dim]


def manual_measurements(size: int, design: Design) -> dict[str, dict]:
    """Body measures (mm) for the polo drafter so its pattern scales with the shirt chart.
    Garment dimension minus the design ease; a research mapping, not a body scan."""
    d = dims(size)
    chest = 20 * d["oberweite_half"] - design.chest_ease_mm
    values = {
        "chest_circumference": (chest, "mm"),
        "waist_circumference": (20 * d["taillenweite_half"] - design.waist_ease_mm, "mm"),
        "hip_girth": (20 * d["saumweite_half"] - design.hip_ease_mm, "mm"),
        "neck_circumference": (10 * d["kragenweite"] - 20, "mm"),
        "across_back_shoulder_width": (10 * d["rt_breite_schulter"], "mm"),
        "back_length": (10 * d["taillenlaenge"], "mm"),
        "upper_arm_girth": (20 * d["oberarmweite_half"] - design.arm_ease_mm, "mm"),
        "sleeve_opening_girth": (20 * d["ae_saumweite_half"] - design.arm_ease_mm, "mm"),
        "armhole_depth": (round(.21 * chest, 3), "mm"),
        "shoulder_slope": (12., "deg"),
        "front_back_width": (0., "mm"),
    }
    reason = f"{CHART} size {size}, research mapping (garment dimension minus design ease)"
    return {k: {"value": round(float(v), 3), "unit": unit, "reason": reason}
            for k, (v, unit) in values.items()}


def design_overrides(size: int) -> dict[str, float]:
    d = dims(size)
    return {"length_mm": 10 * d["laenge_hm"], "sleeve_length_mm": 10 * d["aermellaenge"]}


def document(size: int) -> dict:
    """Measurement document carrying only the size label; the numbers come from `manual`."""
    check_size(size)
    return {"measurements": {}, "meta": {}, "units": "mm",
            "sizing": {"chart": CHART, "size": str(size), "size_source": "size_chart"}}


def config_for(size: int, base: dict) -> dict:
    """Desktop config dict for one size, built on a base config dict (plain JSON)."""
    from .config import DesktopConfig
    cfg = DesktopConfig.model_validate(base).model_dump()
    design = Design.model_validate(cfg["design"])
    cfg["manual"] = manual_measurements(size, design)
    cfg["design"].update(design_overrides(size))
    cfg["process"]["shirt_size"] = check_size(size)
    return DesktopConfig.model_validate(cfg).model_dump()


# Pattern piece -> (chart row scaling local x, chart row scaling local y); None = unchanged.
# Local frame: grain along +y. Passe and collars run their width/length along local y.
PIECE_AXES = {
    "RUECKEN": ("saumweite_half", "laenge_hm"),
    "VORDERTEIL": ("saumweite_half", "laenge_hm"),
    "AERMEL": ("oberarmweite_half", "aermellaenge"),
    "PASSE": (None, "rt_breite_passe"),
    "OBERKRAGEN": (None, "kragenweite"),
    "UNTERKRAGEN": (None, "kragenweite"),
}


def piece_factors(size: int) -> dict[str, tuple[float, float]]:
    out = {}
    for piece, (ax, ay) in PIECE_AXES.items():
        out[piece] = (ratio(ax, size) if ax else 1., ratio(ay, size) if ay else 1.)
    return out
