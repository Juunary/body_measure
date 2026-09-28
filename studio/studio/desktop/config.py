"""Validated, editable research assumptions for the desktop simulator."""
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..simulation.config import Design, Machine, ManualValue, Resources


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SewingStation(StrictModel):
    """Step times come from the measured work-step table; only rates are editable."""
    active_kw: float = Field(.55, ge=0, le=100)
    idle_kw: float = Field(.04, ge=0, le=100)
    equipment_eur_h: float = Field(1, ge=0, le=10000)


class ButtonStation(StrictModel):
    count: int = Field(2, ge=1, le=4)
    top_offset_mm: float = Field(45, ge=0, le=250)
    spacing_mm: float = Field(70, ge=0, le=200)
    hole_length_mm: float = Field(18, ge=8, le=35)
    diameter_mm: float = Field(11, ge=5, le=25)
    hole_stitches: int = Field(80, ge=20, le=500)
    attach_stitches: int = Field(16, ge=4, le=100)
    stitches_per_min: float = Field(800, ge=60, le=3000)
    setup_s: float = Field(12, ge=.1, le=600)
    align_s: float = Field(3, ge=.1, le=120)
    cut_s: float = Field(1, ge=.05, le=30)
    active_kw: float = Field(.45, ge=0, le=100)
    idle_kw: float = Field(.04, ge=0, le=100)
    equipment_eur_h: float = Field(1, ge=0, le=10000)


class QcStation(StrictModel):
    load_s: float = Field(10, gt=0, le=3600)
    scan_s: float = Field(70, gt=0, le=3600)
    release_s: float = Field(10, gt=0, le=3600)
    active_kw: float = Field(.3, ge=0, le=100)
    idle_kw: float = Field(.05, ge=0, le=100)
    equipment_eur_h: float = Field(1, ge=0, le=10000)


class Process(StrictModel):
    transfer_s: float = Field(5, ge=.1, le=300)
    lockstitch: SewingStation = Field(default_factory=SewingStation)
    overlock: SewingStation = Field(default_factory=lambda: SewingStation(active_kw=.6, equipment_eur_h=1.2))
    buttons: ButtonStation = Field(default_factory=ButtonStation)
    qc: QcStation = Field(default_factory=QcStation)


class DesktopConfig(StrictModel):
    design: Design = Field(default_factory=Design)
    machine: Machine = Field(default_factory=Machine)
    resources: Resources = Field(default_factory=Resources)
    manual: dict[str, ManualValue] = Field(default_factory=dict)
    speed: float = Field(10, ge=.1, le=100)
    process: Process = Field(default_factory=Process)

    @model_validator(mode="after")
    def button_layout(self):
        b, d = self.process.buttons, self.design
        first = b.top_offset_mm
        last = first + (b.count - 1) * b.spacing_mm
        occupied_length = max(b.hole_length_mm, b.diameter_mm)
        margin = occupied_length / 2
        if first - margin < 0 or last + margin > d.placket_length_mm:
            raise ValueError("buttonholes must stay inside the placket length")
        if b.count > 1 and b.spacing_mm < occupied_length + 8:
            raise ValueError("buttonholes overlap or lack the required 8 mm clearance")
        if b.diameter_mm > d.placket_width_mm:
            raise ValueError("button diameter must fit inside the placket width")
        return self

    def base_config(self):
        """The established geometry engine stays the source of cutting and seam paths."""
        return {
            "design": self.design.model_dump(), "machine": self.machine.model_dump(),
            "resources": self.resources.model_dump(),
            "manual": {k: v.model_dump() for k, v in self.manual.items()},
            "speed": self.speed, "scope": "through_sewing",
        }
