# -*- coding: utf-8 -*-
"""Specification of a compact urban production line for polo shirts.

The source is the Maß-DPP business plan (Anlage zum Antrag ITA). Any value not
stated in the plan is marked as an "assumption" in the comments. If the code does
not clearly distinguish which figures are evidence and which are assumptions,
the result cannot be cited.

Page numbers follow the document's own "Seite N von 55" numbering (German original
checked against the text, 2026-08-26). The PDF viewer page number is this value + 4.

The plan contains no body-measurement table at all. Seite 38 says "customer-specific
requirements (e.g., size, color, cut, fabric selection)" but does not break size down
into individual body dimensions. Therefore, all entries in MEASUREMENTS are derived
from garment pattern practice and ISO 8559-1.
The plan does not mention "Polo" at all — the subject is consistently Hemd (dress shirt).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# ---------------------------------------------------------------------------
# Cost and environmental model (plan target: 13–15 EUR per piece, under 36 minutes)
# ---------------------------------------------------------------------------
TARGET_MINUTES = 36.0          # Seite 4 — "Maßhemden in Losgröße 1 in <36 Minuten"
TARGET_COST_EUR = (13.0, 15.0)  # Seite 4 — "zu Produktionskosten von 13 bis 15 Euro"
BENCHMARK_MASS_PRODUCTION = 37.0  # Seite 4 · 28 — shirts from Southeast Asia in mass production at ">37 Minuten"

WAGE_EUR_PER_HOUR = 22.0       # Assumption: unskilled labor + overhead
ENERGY_EUR_PER_KWH = 0.25      # Assumption: German industrial electricity rate
CO2_G_PER_KWH = 380.0          # Assumption: German grid mix
MATERIAL_EUR = 6.50            # Assumption: approx. 1.2 m² piqué fabric + rib trim + thread + buttons
DEPRECIATION_EUR = 1.50        # Assumption: equipment depreciation allocation
LINE_OVERHEAD_KW = 0.30        # Assumption: constant load from transport, lighting, and controls

DPP_PAYLOAD_KB = 15.0          # Seite 31 — 15 kB per JSON product description (basis for 6.25 TB/year design data)
SENSOR_HZ = 1.0                # Seite 37 — real-time process-parameter collection (<1 s)
SENSOR_CHANNELS = 10           # Assumption: average active channels per module (not mentioned in the plan)


# ---------------------------------------------------------------------------
# 1. Body dimensions to extract from the 3D scan
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Measurement:
    key: str                # key from the body-measure spec (or suggested if absent)
    name: str
    pattern_use: str        # pattern region determined by this measurement
    method: str             # derivation method from the 3D mesh
    spec_status: str        # body-measure measurement-spec v4 status
    polo_note: str = ""


# Comparison against body-measure/measurement-spec.v1.yaml (spec_version 4, 2026-08-25).
# Entries with spec_status set to "—" are dimensions currently absent from the spec but needed for polo shirts.
MEASUREMENTS: list[Measurement] = [
    Measurement(
        "neck_circumference", "Neck base girth", "Rib collar length, neckline",
        "plane_slice (horizontal approx.)", "core / implemented_v1",
        "The rib collar is knitted, so it is cut shorter than measured",
    ),
    Measurement(
        "chest_circumference", "Chest girth", "Body width — the critical one",
        "plane_slice (at max chest level)", "core / implemented_v1",
        "Pique knit takes less ease than a woven shirt",
    ),
    Measurement(
        "waist_circumference", "Waist girth", "Side seam silhouette (slim / regular)",
        "plane_slice (at min girth)", "core / implemented_v1",
    ),
    Measurement(
        "across_back_shoulder_width", "Across-back shoulder width", "Yoke and shoulder seam",
        "surface_path (via back neck point)", "core / implemented_v1",
    ),
    Measurement(
        "back_length", "Back length", "Body length, drop tail",
        "sagittal_slice_polyline", "core / implemented_v1",
        "A polo's back runs longer than its front (drop tail)",
    ),
    Measurement(
        "upper_arm_girth", "Upper arm girth", "Sleeve width",
        "plane_slice (armpit-to-wrist search)", "core / plane_slice_v1",
        "A short sleeve ends on the upper arm — required",
    ),
    Measurement(
        "sleeve_length", "Sleeve length", "Short sleeve length",
        "surface_path (shoulder-elbow-wrist)", "deferred / implemented_v1",
        "On a short sleeve this is a design choice, not a body measurement",
    ),
    Measurement(
        "hem_girth", "Hem girth (at hip level)", "Hem width",
        "plane_slice (at hem level)", "—",
        "Torso girth where the polo hem falls — not in the spec",
    ),
    Measurement(
        "sleeve_opening_girth", "Sleeve opening girth", "Rib cuff length",
        "plane_slice (at sleeve end)", "—",
"Decided together with rib cuff stretch — not in the spec",
    ),
    Measurement(
        "armhole_depth", "Armhole depth", "Armhole curve, sleeve cap",
        "landmark (shoulder to armpit, vertical)", "—",
        "Governs the sleeve attachment angle — not in the spec",
    ),
    Measurement(
        "shoulder_slope", "Shoulder slope", "Shoulder seam angle",
        "landmark (neck point to shoulder tip)", "—",
        "What a 3D scan gives you that a tape measure cannot — not in the spec",
    ),
    Measurement(
        "front_back_width", "Front / back width", "Front / back balance",
        "plane_slice arc (between armpits)", "—",
        "Handles front/back asymmetry — not in the spec",
    ),
]


# ---------------------------------------------------------------------------
# 2. Equipment chain
# ---------------------------------------------------------------------------
@dataclass
class Station:
    key: str
    machine: str
    role: str
    minutes: float          # Based on Table 4 in the plan or polo-specific decomposition
    kw: float               # Assumption: rated power
    # plan   — machine name appears directly in Table 3
    # unspec — needed for knit sewing, but Table 3 does not specify the machine.
    #          This is not "equipment absent from the plan" but "equipment not explicitly specified by the plan".
    # option — marked as optional in Table 3
    origin: str
    attended: float         # Assumption: proportion of time the operator must keep a hand on it
    readouts: list[tuple[str, str, Callable[[float], str]]] = field(default_factory=list)
    dpp: dict = field(default_factory=dict)
    optional: bool = False


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}"


# Table 4 (Seite 49) is based on a dress shirt and has only four modules:
#   cutter 3 min + sewing 25 min + finishing 6 min + packing 2 min = exactly 36 min.
# This means the plan's own estimate totals the upper target limit with zero slack, while
# quality control and DPP labeling are not assigned time in the table (they do appear in the flow on Seite 38).
# The configuration below allocates time to those two modules and decomposes the 25-minute sewing step for polo use.
#
# Note: the German source text for Table 3 is "Spezialisierte Pfaff Nähmaschinen" — plural, and the process name is only
# "Nähen". Because the plan does not specify the stitch type, the equipment marked with origin="unspec" below is not
# equipment excluded by the plan, but equipment not explicitly named by it. The basis for needing it in knit sewing comes
# from garment-making practice.
#
# The machine name is not written in dpp; it is derived from Station.machine (live.build_block).
# When blocks were filled manually, 7 of 11 entries were missing.
STATIONS: list[Station] = [
    Station(
        "cut", "Zünd S3 · ITA Laser", "Cutting — automatic cut from the CAD marker",
        3.0, 1.8, "plan", attended=0.35,
        readouts=[
            ("Cut speed", "m/min", lambda p: _fmt(34 + 6 * p)),
            ("Cut length", "m", lambda p: _fmt(8.6 * p, 2)),
            ("Marker yield", "%", lambda p: _fmt(81.4)),
        ],
        dpp={"module": "cutting", "cut_length_m": 8.6, "marker_yield_pct": 81.4},
    ),
    Station(
        "ovl", "Overlock 3/4-thread", "Overlock — knit side and shoulder seams",
        8.0, 0.55, "unspec", attended=1.00,
        readouts=[
            ("Stitch rate", "rpm", lambda p: _fmt(6300 + 700 * p, 0)),
            ("Seam length", "mm", lambda p: _fmt(2350 * p, 0)),
            ("Thread tension", "cN", lambda p: _fmt(38.0)),
        ],
        dpp={"module": "overlock", "seam_length_mm": 2350, "avg_rpm": 6300},
    ),
    Station(
        # The original Table 3 text is "Spezialisierte Pfaff Nähmaschinen" — plural and the stitch type is unspecified.
        # The "main stitch" below is the stitch type this model assigns to the placket and yoke requirements.
        "lock", "Pfaff Spezial", "Lockstitch — placket and yoke",
        5.0, 0.55, "plan", attended=1.00,
        readouts=[
            ("Stitch rate", "rpm", lambda p: _fmt(4100 + 400 * p, 0)),
            ("Seam length", "mm", lambda p: _fmt(920 * p, 0)),
            ("Stitches", "sts", lambda p: _fmt(3700 * p, 0)),
        ],
        dpp={"module": "lockstitch", "seam_length_mm": 920, "stitch_count": 3700},
    ),
    Station(
        "cov", "Coverstitch 3-needle", "Coverstitch — hem and sleeve edge",
        4.0, 0.55, "unspec", attended=1.00,
        readouts=[
            ("Stitch rate", "rpm", lambda p: _fmt(5400 + 500 * p, 0)),
            ("Hem length", "mm", lambda p: _fmt(1310 * p, 0)),
            ("Differential feed", "", lambda p: _fmt(1.30, 2)),
        ],
        dpp={"module": "coverstitch", "hem_length_mm": 1310, "differential_ratio": 1.3},
    ),
    Station(
        "rib", "Flat-knit rib feed", "Rib collar and cuff attach (flat-knit feed)",
        4.0, 1.2, "unspec", attended=1.00,
        readouts=[
            ("Rib stretch", "%", lambda p: _fmt(12.5)),
            ("Attach length", "mm", lambda p: _fmt(760 * p, 0)),
            ("Knit tension", "cN", lambda p: _fmt(52.0, 0)),
        ],
        dpp={"module": "rib_attach", "collar_stretch_pct": 12.5, "attach_length_mm": 760},
    ),
    Station(
        "btn", "Buttoner + buttonholer", "Buttons and buttonholes — three on the placket",
        2.0, 0.4, "unspec", attended=0.30,
        readouts=[
            ("Cycle", "/3", lambda p: str(min(3, int(p * 3.01)))),
            ("Cycle time", "s", lambda p: _fmt(11.8)),
            ("Pull test", "N", lambda p: _fmt(68.0, 0)),
        ],
        dpp={"module": "buttons", "count": 3, "pull_test_N": 68},
    ),
    Station(
        "emb", "ZSK Spezial", "Embroidery — logo personalisation",
        2.5, 0.6, "option", attended=0.15, optional=True,
        readouts=[
            ("Stitches", "sts", lambda p: _fmt(8400 * p, 0)),
            ("Head speed", "rpm", lambda p: _fmt(840, 0)),
            ("Trims", "", lambda p: str(int(p * 6))),
        ],
        dpp={"module": "embroidery", "stitch_count": 8400},
    ),
    Station(
        "prn", "Epson · Kornit DTG", "Textile print — graphic personalisation",
        2.0, 1.5, "option", attended=0.20, optional=True,
        readouts=[
            ("Ink used", "ml", lambda p: _fmt(14.2 * p)),
            ("Pass", "/8", lambda p: str(min(8, int(p * 8.05)))),
            ("Cure temp", "°C", lambda p: _fmt(158, 0)),
        ],
        dpp={"module": "dtg_print", "ink_ml": 14.2, "cure_temp_C": 158},
    ),
    Station(
        "fin", "Veit SF 27", "Finishing — steam press (pressure, temperature, humidity)",
        5.0, 4.5, "plan", attended=0.25,
        readouts=[
            ("Press temp", "°C", lambda p: _fmt(press_temp(p), 0)),
            ("Steam pressure", "bar", lambda p: _fmt(press_bar(p), 2)),
            ("Humidity", "%", lambda p: _fmt(press_humidity(p), 0)),
        ],
        dpp={"module": "finishing", "peak_temp_C": 164, "steam_bar": 4.8},
    ),
    Station(
        "qc", "Vision QC + CNN", "Quality control — camera and defect-recognition network",
        1.5, 0.3, "plan", attended=0.20,
        readouts=[
            ("Frames", "", lambda p: str(int(96 * p))),
            ("Defect score", "", lambda p: _fmt(0.021, 3)),
            ("Verdict", "", lambda p: "PASS" if p > 0.97 else "scanning"),
        ],
        dpp={"module": "quality", "frames": 96, "defect_score": 0.021, "verdict": "PASS"},
    ),
    Station(
        # Seite 38 says "label with a product-specific DPP" but there is no matching machine in Table 3.
        "lbl", "DPP label unit", "QR label and packing — issued via ColorDigital SaaS",
        2.0, 0.2, "unspec", attended=0.90,
        readouts=[
            ("DPP upload", "kB", lambda p: _fmt(DPP_PAYLOAD_KB * p, 1)),
            ("Validation (>99%)", "", lambda p: "VALID" if p > 0.5 else "sending"),
            ("QR print", "", lambda p: "done" if p > 0.8 else "waiting"),
        ],
        dpp={"module": "dpp_label", "validation": "passed", "qr": "printed"},
    ),
]

# Sewing cell — the bottleneck group replicated together as the line expands
SEWING_KEYS = ("ovl", "lock", "cov", "rib")


def press_temp(p: float) -> float:
    """Temperature curve for the Veit finisher: warm-up → hold → cooling."""
    if p < 0.25:
        return 25 + (164 - 25) * (p / 0.25)
    if p < 0.80:
        return 164.0
    return 164 - (164 - 70) * ((p - 0.80) / 0.20)


def press_bar(p: float) -> float:
    if p < 0.20:
        return 4.8 * (p / 0.20)
    if p < 0.80:
        return 4.8
    return 4.8 * (1 - (p - 0.80) / 0.20)


def press_humidity(p: float) -> float:
    return 45 + 40 * (p / 0.5) if p < 0.5 else 85 - 55 * ((p - 0.5) / 0.5)


def active_stations(embroidery: bool = False, printing: bool = False) -> list[Station]:
    """Return the set of active process steps depending on which optional modules are enabled."""
    chosen = []
    for st in STATIONS:
        if st.key == "emb" and not embroidery:
            continue
        if st.key == "prn" and not printing:
            continue
        chosen.append(st)
    return chosen
