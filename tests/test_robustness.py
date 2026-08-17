"""Gated numerical-robustness tests on the generated SMPL A-pose body.

Strict invariances only (category: numerical_robustness) — noise and
decimation sensitivities are reported by scripts/robustness_report.py,
not gated, because on real scans they are documented open limitations.

Skipped when data/generated/smpl_neutral0_apose.obj is absent.
"""
from pathlib import Path

import pytest

from body_measure.adapters.mesh_file import MeshFileAdapter
from body_measure.canonicalize import canonicalize
from body_measure.validate.robustness import (
    measure_all,
    permute_and_flip,
    uniform_scale,
    yaw_and_translate,
)

SMPL_OBJ = (
    Path(__file__).resolve().parents[1] / "data" / "generated" / "smpl_neutral0_apose.obj"
)

pytestmark = pytest.mark.skipif(not SMPL_OBJ.exists(), reason="generated SMPL body absent")

CIRCUMFERENCES = ("waist_circumference", "chest_circumference", "neck_circumference")


@pytest.fixture(scope="module")
def mesh():
    return canonicalize(MeshFileAdapter().load(SMPL_OBJ, unit="m"))


@pytest.fixture(scope="module")
def baseline(mesh):
    return measure_all(mesh)


def test_yaw_and_translation_leave_circumferences_unchanged(mesh, baseline):
    moved = measure_all(yaw_and_translate(mesh))
    for name in CIRCUMFERENCES:
        assert moved[name] == pytest.approx(baseline[name], abs=0.5), name


def test_vertex_permutation_and_winding_flip_change_nothing(mesh, baseline):
    permuted = measure_all(permute_and_flip(mesh))
    for name, value in baseline.items():
        if value is not None:
            assert permuted[name] == pytest.approx(value, abs=0.01), name


def test_uniform_scaling_scales_circumferences_linearly(mesh, baseline):
    scaled = measure_all(uniform_scale(mesh, 1.01))
    for name in CIRCUMFERENCES:
        assert scaled[name] == pytest.approx(baseline[name] * 1.01, abs=3.0), name
