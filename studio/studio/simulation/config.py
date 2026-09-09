"""Editable research assumptions, NOT manufacturer operating specifications."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Design(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    chest_ease_mm: float = Field(100, ge=0, le=400)
    waist_ease_mm: float = Field(100, ge=0, le=400)
    hip_ease_mm: float = Field(80, ge=0, le=400)
    arm_ease_mm: float = Field(60, ge=10, le=200)
    length_mm: float = Field(700, ge=350, le=1200)
    sleeve_length_mm: float = Field(270, ge=150, le=500)
    seam_mm: float = Field(10, ge=2, le=30)
    shrink_pct: float = Field(0, ge=0, le=15)
    placket_length_mm: float = Field(160, ge=80, le=250)
    placket_width_mm: float = Field(30, ge=20, le=60)
    collar_width_mm: float = Field(70, ge=30, le=120)
    cuff_width_mm: float = Field(35, ge=15, le=70)
    rib_ratio: float = Field(.9, ge=.7, le=1)


class Machine(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    fabric_width_mm: float = Field(1500, ge=300, le=3000)
    rib_width_mm: float = Field(1000, ge=300, le=3000)
    bed_width_mm: float = Field(1600, ge=300, le=3200)
    bed_length_mm: float = Field(2000, ge=400, le=4000)
    gap_mm: float = Field(5, ge=1, le=30)
    cut_speed_mm_s: float = Field(100, ge=1, le=1000)
    travel_speed_mm_s: float = Field(300, ge=1, le=1500)
    mark_speed_mm_s: float = Field(150, ge=1, le=1000)
    feed_speed_mm_s: float = Field(200, ge=1, le=1000)
    tool_change_s: float = Field(.4, ge=.05, le=10)
    load_s: float = Field(20, ge=1, le=600)
    align_s: float = Field(5, ge=1, le=60)
    vacuum_s: float = Field(2, ge=.1, le=30)
    pickup_s: float = Field(3, ge=.1, le=60)
    stitch_length_mm: float = Field(3, ge=1, le=6)
    stitches_per_min: float = Field(600, ge=60, le=3000)
    sewing_setup_s: float = Field(15, ge=1, le=300)
    seam_align_s: float = Field(4, ge=.1, le=60)
    presser_s: float = Field(.5, ge=.1, le=5)
    thread_trim_s: float = Field(1, ge=.1, le=10)
    transfer_s: float = Field(5, ge=.1, le=60)


class ManualValue(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    value: float
    unit: Literal["mm", "deg"] = "mm"
    reason: str = Field(min_length=1, max_length=500)


class Resources(BaseModel):
    """Versioned research assumptions; no manufacturer or tariff claims."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    currency: Literal['EUR'] = 'EUR'
    zund_active_kw: float = Field(1, ge=0, le=100)
    zund_idle_kw: float = Field(.1, ge=0, le=100)
    vacuum_kw: float = Field(.8, ge=0, le=100)
    overhead_kw: float = Field(.3, ge=0, le=100)
    pfaff_active_kw: float = Field(.55, ge=0, le=100)
    pfaff_idle_kw: float = Field(.04, ge=0, le=100)
    electricity_eur_kwh: float = Field(.25, ge=0, le=100)
    grid_gco2e_kwh: float = Field(380, ge=0, le=10000)
    labour_eur_h: float = Field(22, ge=0, le=10000)
    zund_eur_h: float = Field(6, ge=0, le=10000)
    pfaff_eur_h: float = Field(1, ge=0, le=10000)
    body_eur_m2: float = Field(5, ge=0, le=10000)
    rib_eur_m2: float = Field(8, ge=0, le=10000)
    thread_eur_m: float = Field(.01, ge=0, le=100)
    thread_ratio: float = Field(3, ge=0, le=100)
    thread_tail_m: float = Field(.1, ge=0, le=10)


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    design: Design = Field(default_factory=Design)
    machine: Machine = Field(default_factory=Machine)
    resources: Resources = Field(default_factory=Resources)
    manual: dict[str, ManualValue] = Field(default_factory=dict)
    speed: float = Field(10, ge=.1, le=100)
    scope: Literal['through_cutting', 'through_sewing'] = 'through_sewing'


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    run_id: str
    action: Literal["play", "pause", "seek", "speed", "restart", "next", "previous"]
    value: float | None = None


# Dimensions used by this construction, not a redefinition of body_measure's
# broader pattern-readiness gate. Wrist sleeve length is deliberately absent.
REQUIRED = {
    "chest_circumference": ("mm", 500, 1800),
    "waist_circumference": ("mm", 400, 1800),
    "neck_circumference": ("mm", 200, 700),
    "across_back_shoulder_width": ("mm", 200, 700),
    "back_length": ("mm", 200, 700),
    "upper_arm_girth": ("mm", 120, 700),
    "hip_girth": ("mm", 500, 1900),
    "sleeve_opening_girth": ("mm", 100, 700),
    "armhole_depth": ("mm", 100, 400),
    "shoulder_slope": ("deg", 0, 40),
    "front_back_width": ("mm", -300, 300),
}

MACHINES = [
    ("zund", "Zünd S3", "active", "plan", "cutting"),
    ("laser", "ITA Lasercutter", "alternative", "plan", "laser"),
    ("pfaff", "Pfaff", "active_sewing", "plan", "sewing"),
    ("veit", "Veit SF 27", "downstream", "plan", "finisher"),
    ("qc", "Camera QC", "downstream", "plan", "camera"),
    ("zsk", "ZSK", "optional", "plan", "embroidery"),
    ("epson", "Epson", "optional", "plan", "printer"),
    ("kornit", "Kornit", "optional", "plan", "printer"),
    ("overlock", "Overlock", "downstream", "polo_addition", "sewing"),
    ("coverstitch", "Coverstitch", "downstream", "polo_addition", "sewing"),
    ("rib", "Rib supply", "downstream", "polo_addition", "rib"),
    ("button", "Button / buttonhole", "downstream", "polo_addition", "sewing"),
]


def machine_catalogue():
    return [dict(zip(("id", "name", "role", "source", "shape"), row)) for row in MACHINES]
