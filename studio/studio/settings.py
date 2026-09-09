"""What the settings drawer can choose from, and what a job request
carries. The enumerations come from the projects that own them; nothing
here is a catalogue of its own."""
from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from . import paths  # noqa: F401
from . import sizing_map
from .meshio import UNITS, UP_AXES
from app.schemas import LANGS
from body_measure import sizing

POPULATIONS = ("men", "women")


class ReplaySettings(BaseModel):
    delay: float = Field(default=0.10, ge=0.0, le=2.0)
    embroidery: bool = False
    printing: bool = False


class JobRequest(BaseModel):
    file_id: str
    unit: str | None = None
    up_axis: str | None = None
    clothed: bool = False
    population: str | None = None
    chart: str = sizing.DEFAULT_CHART
    replay: ReplaySettings = Field(default_factory=ReplaySettings)


class SizeRequest(BaseModel):
    chart: str = sizing.DEFAULT_CHART
    population: str | None = None
    clothed: bool = False


class OverrideRequest(BaseModel):
    size: str | None = None
    reason: str = ""


class ReportRequest(BaseModel):
    target: str = "measurement"
    key: str
    value: float | list[float] | None = None
    unit: str = "mm"
    text: str


class PassportRequest(BaseModel):
    config: dict[str, Any]
    base_url: str


def default_lang() -> str:
    """`run.ps1 KR` sets STUDIO_LANG; English otherwise. The page opens in
    this language every time — the switcher changes it for the session."""
    lang = os.environ.get("STUDIO_LANG", "en").lower()
    return lang if lang in LANGS else "en"


def options() -> dict:
    return {
        "default_lang": default_lang(),
        "charts": sizing_map.chart_options(),
        "default_chart": sizing.DEFAULT_CHART,
        "populations": list(POPULATIONS),
        "units": list(UNITS),
        "up_axes": list(UP_AXES),
        "langs": list(LANGS),
        "replay": ReplaySettings().model_dump(),
        "size_options": list(sizing_map.SIZE_OPTIONS),
        "boundary_margin_mm": sizing.BOUNDARY_MARGIN_MM,
    }
