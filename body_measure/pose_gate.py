"""Is this scan in the pose the spec was written for?

The spec measures a standing body in an A pose (`posture_default:
standing`; the arms abducted so that an arm and the torso are separate
loops in a horizontal slice). A scan that is not that — a fashion scan
with boots and the arms hanging against a jacket, a T pose — still
produces numbers, and every one of them is refused or flagged downstream:
the orientation-dependent paths refuse, the upper arm finds a loop that
is not an arm, the chest clips at a level nobody chose. Better to say so
once, before measuring, than to hand back a table of refusals that reads
as though the scan had been measured.

Each check is one of this package's own estimators asked a yes/no
question — nothing is estimated a second way:

* **standing** — the vertical extent is a human stature;
* **orientation** — `estimate_facing` resolved front from back (the
  three surface-path measurements require it, spec `requires:`);
* **arms clear** — `arm_loops_at` finds BOTH arms apart from the torso
  at most levels of the upper-arm window; a body with the arms held
  against it has no such slice, and neither has a T pose, whose arms
  are horizontal.

The verdict is about the pose, not the subject. A clothed body in a good
pose passes and is the clothed pathway's business (decision #20).

Where it runs: at the entry points that measure a user's scan — the CLI
and the studio — and NOT inside `run_estimated_measurements`. The core
is also what the validation scripts call over the Texel and NOMO
subjects, and a gate inside it would change every statistic silently
when it fired. Calling it explicitly keeps the refusal a decision the
caller made and can see (decision #45).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh

from .landmarks.estimated import (
    arm_loops_at,
    estimate_armpit_level,
    estimate_facing,
    upper_arm_window,
)

#: a canonical mesh taller or shorter than this is not a standing person
STANDING_MM = (1200.0, 2300.0)
#: the upper-arm window is scanned at this step for both-arm slices
ARM_STEP_MM = 10.0
#: fraction of those levels at which BOTH arms must slice apart from the
#: torso. Hanging arms (HSRD) give 0.00 and a T pose at most 0.09; SMPL
#: and Texel A poses give 1.00, and NOMO's A poses go down to 0.29 —
#: not because the arms are closer but because NOMO ships segmented
#: meshes whose seams open some arm loops. The threshold sits in the
#: gap between 0.09 and 0.29 (decision #45); it is not a tuning knob.
MIN_ARM_LEVEL_FRACTION = 0.2

REJECTED_FLAG = "pose_rejected"


@dataclass
class PoseVerdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "reasons": list(self.reasons), "checks": self.checks}


def check_pose(mesh: trimesh.Trimesh) -> PoseVerdict:
    """The verdict on a canonical mesh (millimetres, Y-up, floor at 0).
    Every reason is a sentence a user can act on."""
    reasons: list[str] = []
    checks: dict = {}

    height = float(mesh.bounds[1][1] - mesh.bounds[0][1])
    checks["stature_mm"] = round(height, 1)
    if not STANDING_MM[0] <= height <= STANDING_MM[1]:
        reasons.append(
            f"not a standing body: vertical extent {height:.0f} mm is outside "
            f"{STANDING_MM[0]:.0f}-{STANDING_MM[1]:.0f} mm")

    facing = estimate_facing(mesh)
    checks["facing"] = facing.to_dict()
    if facing.confidence <= 0.0 or "orientation_unknown" in facing.flags:
        reasons.append(
            "front and back cannot be told apart from the feet ("
            + ", ".join(facing.flags) + ") - three of seven measurements need "
            "the orientation and would refuse")

    armpit = estimate_armpit_level(mesh)
    if armpit is None:
        checks["arms"] = None
        reasons.append(
            "no armpit level: the arms do not separate from the torso in any "
            "horizontal slice - an A pose with the arms held clear is required")
    else:
        lo, hi, _ = upper_arm_window(mesh, armpit, None)
        levels = np.arange(lo, hi, ARM_STEP_MM)
        both = 0
        for level in levels:
            loops, _ = arm_loops_at(mesh, float(level), armpit)
            both += int("left" in loops and "right" in loops)
        fraction = both / max(len(levels), 1)
        checks["arms"] = {
            "armpit_mm": round(float(armpit.position_mm[1]), 1),
            "armpit_confidence": round(float(armpit.confidence), 2),
            "levels": int(len(levels)),
            "levels_with_both_arms": int(both),
            "fraction": round(float(fraction), 2),
        }
        if fraction < MIN_ARM_LEVEL_FRACTION:
            reasons.append(
                f"arms are not clear of the torso: both arms slice apart from it "
                f"at only {both} of {len(levels)} upper-arm levels "
                f"(need {MIN_ARM_LEVEL_FRACTION:.0%}) - an A pose is required")

    return PoseVerdict(not reasons, reasons, checks)
