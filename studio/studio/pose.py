"""The pose gate is body-measure's (`body_measure.pose_gate`, decision
#45); the studio only calls it at the same place the CLI does — before
`run_estimated_measurements` — and shows the verdict. Nothing about what
counts as a good pose lives here."""
from __future__ import annotations

from . import paths  # noqa: F401
from body_measure.pose_gate import check_pose

__all__ = ["check_pose"]
