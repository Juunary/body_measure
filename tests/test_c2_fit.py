"""C2 fitting — gated on torch and the SMPL model being present.

These are gate tests, not benchmarks: they run a shortened fit and check
the invariants the design promises — measurement happens in the canonical
pose, the quality score is raw residuals (never named confidence), the
battery covers every documented break, and the identity shell does not
collapse."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMPL_PRESENT = (PROJECT_ROOT / "models" / "smpl" / "SMPL_NEUTRAL.pkl").exists()


def _torch_loads() -> bool:
    if importlib.util.find_spec("torch") is None:
        return False
    try:
        import torch  # noqa: F401
        return True
    except Exception:  # DLL failures on some shells
        return False


needs_inference = pytest.mark.skipif(
    not (SMPL_PRESENT and _torch_loads()), reason="torch or SMPL model unavailable"
)


@pytest.fixture(scope="module")
def body():
    from body_measure.inference.smpl_body import SmplBody
    return SmplBody()


@needs_inference
def test_canonical_mesh_is_in_the_measure_frame(body):
    mesh = body.canonical_mesh(np.zeros(10), source_id="t")
    extent = mesh.bounds[1] - mesh.bounds[0]
    assert abs(mesh.bounds[0][1]) < 1e-6            # floor at y = 0
    assert extent[1] == max(extent)                  # Y is the long axis
    assert 1500.0 < extent[1] < 1900.0               # millimetres, not metres
    assert mesh.metadata["weld"]["applied"] is False


@needs_inference
def test_canonical_mesh_keeps_the_smpl_vertex_order(body):
    """SMPL's vertex order IS the correspondence — a CAPE displacement is
    indexed against it 0..6889. Welding merges nothing on this body today,
    but the guarantee has to be the construction, not the luck: canonicalize
    itself says to pass weld=False when the caller depends on the incoming
    indexing."""
    import torch

    betas = np.linspace(-1.5, 1.5, 10)
    mesh = body.canonical_mesh(betas, source_id="order")
    assert len(mesh.vertices) == body.n_vertices == 6890
    assert mesh.metadata["weld"]["merged"] == 0

    raw_mm = body.canonical_vertices_m(
        torch.as_tensor(betas, dtype=torch.float32)) * 1000.0
    shift = raw_mm[:, 1].min()
    assert np.allclose(mesh.vertices[:, 1], raw_mm[:, 1] - shift, atol=1e-6)
    assert np.allclose(mesh.vertices[:, [0, 2]], raw_mm[:, [0, 2]], atol=1e-6)


@needs_inference
def test_canonical_pose_is_the_generators_a_pose(body):
    from body_measure.inference.smpl_body import ABDUCTION_DEG, canonical_body_pose
    pose = canonical_body_pose()
    assert ABDUCTION_DEG == 50.0  # scripts/generate_smpl_bodies.py
    nonzero = pose.nonzero()
    assert len(nonzero) == 2      # only the two shoulders move


@needs_inference
def test_battery_covers_every_documented_break(body):
    from body_measure.inference.shells import build_battery
    latent = body.canonical_mesh(np.zeros(10), source_id="t")
    cases = build_battery(latent, body.part_of_vertex, seed=1)
    names = {c.name for c in cases}
    assert {"identity", "uniform_15mm", "partwise_jacket_jeans", "front_back_asymmetric",
            "uniform_with_holes", "uniform_decimated", "uniform_normals_flipped",
            "uniform_hair_shoes"} <= names
    for c in cases:
        assert c.breaks                                   # every case says what it tests
        assert set(c.gap_band_mm) == {"torso", "head", "arm", "leg"}
        assert len(c.true_gap_mm) == body.n_vertices


@needs_inference
def test_identity_shell_does_not_collapse_and_measures_in_canonical_pose(body):
    from body_measure.inference.fit import FitConfig, fit_shell
    from body_measure.inference.shells import identity_shell
    from body_measure.measure.measurements import run_estimated_measurements

    rng = np.random.default_rng(7)
    betas = rng.normal(0.0, 0.8, 10)
    latent = body.canonical_mesh(betas, source_id="latent")
    case = identity_shell(latent, body.part_of_vertex)
    cfg = FitConfig(seed=7, iters_coarse=40, iters_pose=15, iters_shape=40, iters_refine=10,
                    n_shell_samples=4000, n_body_subsample=1200)
    fit = fit_shell(body, case.mesh, case.gap_band_mm, cfg)

    score = fit.fit_quality_score
    assert "fit_confidence" not in score          # the name is reserved
    assert score["collapse_fraction"] < 0.05
    assert "possible_collapse" not in fit.flags

    recovered = body.canonical_mesh(fit.betas, source_id="recovered")
    from body_measure.landmarks.estimated import provided_facing
    facing = provided_facing((0.0, 1.0), source="smpl_frame")
    truth, _ = run_estimated_measurements(latent, facing=facing)
    got, _ = run_estimated_measurements(recovered, facing=facing)
    neck_t, neck_g = truth["neck_circumference"].selected_value_mm, got["neck_circumference"].selected_value_mm
    assert neck_t is not None and neck_g is not None
    # a short fit must still land in the right neighbourhood; precision is
    # the battery's job, not this gate's
    assert abs(neck_g - neck_t) < 60.0


@needs_inference
def test_fit_result_carries_its_method_and_no_confidence(body):
    from body_measure.inference.fit import FitConfig, fit_shell
    from body_measure.inference.shells import uniform_shell
    latent = body.canonical_mesh(np.zeros(10), source_id="latent")
    case = uniform_shell(latent, body.part_of_vertex)
    cfg = FitConfig(seed=1, iters_coarse=5, iters_pose=3, iters_shape=5, iters_refine=2,
                    n_shell_samples=1500, n_body_subsample=600)
    d = fit_shell(body, case.mesh, case.gap_band_mm, cfg).to_dict()
    assert d["inference_method"] == "c2_staged_optimisation"
    assert [s["stage"] for s in d["stages"]] == ["coarse_shape", "coarse_pose", "shape_band", "refine"]
    assert "confidence" not in " ".join(d["fit_quality_score"].keys())
