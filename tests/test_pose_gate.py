"""The pose gate refuses what the estimated pathway was not written for,
and nothing else. Gated on the generated SMPL bodies (A pose passes, T
pose does not) and on HSRD's fashion scan when it is on disk."""
from pathlib import Path

import pytest

from body_measure.adapters.mesh_file import MeshFileAdapter
from body_measure.canonicalize import canonicalize
from body_measure.pose_gate import MIN_ARM_LEVEL_FRACTION, PoseVerdict, check_pose

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED = PROJECT_ROOT / "data" / "generated"
HSRD_LOD2 = PROJECT_ROOT / "data" / "external" / "hsrd" / "lod2"

needs_smpl = pytest.mark.skipif(
    not (GENERATED / "smpl_neutral0_apose.obj").exists(), reason="generated SMPL bodies absent")
needs_hsrd = pytest.mark.skipif(not HSRD_LOD2.is_dir(), reason="HSRD absent")


def _smpl(name):
    return canonicalize(MeshFileAdapter().load(GENERATED / f"{name}.obj", unit="m"))


@needs_smpl
def test_an_a_pose_body_passes_at_every_level():
    verdict = check_pose(_smpl("smpl_neutral0_apose"))
    assert verdict.ok, verdict.reasons
    assert verdict.checks["arms"]["fraction"] == 1.0
    assert verdict.checks["facing"]["confidence"] > 0.5


@needs_smpl
def test_a_t_pose_is_refused_for_its_arms_and_says_so():
    """Horizontal arms never slice apart from the torso as loops. The
    verdict names the arms, not the orientation — the feet are fine."""
    verdict = check_pose(_smpl("smpl_neutral0_tpose"))
    assert not verdict.ok
    assert len(verdict.reasons) == 1 and "arms" in verdict.reasons[0]
    assert verdict.checks["arms"]["fraction"] < MIN_ARM_LEVEL_FRACTION


@needs_hsrd
def test_the_hsrd_fashion_scan_is_refused_before_any_number_exists():
    from body_measure.adapters.hsrd import HsrdAdapter

    mesh = canonicalize(HsrdAdapter(HSRD_LOD2.parent).load(HSRD_LOD2))
    verdict = check_pose(mesh)
    assert not verdict.ok
    assert any("arms" in r for r in verdict.reasons)


def test_the_threshold_sits_between_the_refused_and_the_passing_scans():
    """Hanging arms and T poses give at most 0.09; the lowest A-pose body
    on disk (a segmented NOMO mesh) gives 0.29. A threshold anywhere
    between is the same gate. Pinned so that a change is a decision (#45),
    not a drift."""
    assert 0.09 < MIN_ARM_LEVEL_FRACTION < 0.29


def test_a_verdict_serialises_with_its_reasons():
    verdict = PoseVerdict(False, ["x"], {"stature_mm": 1700.0})
    assert verdict.to_dict() == {"ok": False, "reasons": ["x"], "checks": {"stature_mm": 1700.0}}
