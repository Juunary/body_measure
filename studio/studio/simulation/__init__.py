"""Deterministic, geometry-based research cutting simulation (millimetres/seconds).

No machine controller, textile physics, or production accuracy claim lives here.
"""
from .config import SimulationConfig
from .engine import build_plan, snapshot

__all__ = ["SimulationConfig", "build_plan", "snapshot"]
