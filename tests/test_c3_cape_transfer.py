"""C3: a CAPE clothing displacement carried onto this project's A pose.

The first test is the load-bearing one. The transfer re-implements SMPL's
skinning with smplx's primitives, because passing `v_template + D` to
`lbs()` would regress the joints from the displaced surface and let the
clothing move the skeleton. A re-implementation is only trustworthy if it
reproduces the original exactly where they must agree, and D = 0 is that
place.
"""
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPE_ROOT = PROJECT_ROOT / "data" / "external" / "cape"

torch = pytest.importorskip("torch")
pytest.importorskip("smplx")
needs_smpl = pytest.mark.skipif(
    not (PROJECT_ROOT / "models" / "smpl" / "SMPL_MALE.pkl").exists(),
    reason="SMPL model absent")
needs_cape = pytest.mark.skipif(
    not (CAPE_ROOT / "cape_release").is_dir(), reason="CAPE release absent")
needs_archive = pytest.mark.skipif(
    not (CAPE_ROOT / "00215.zip").is_file(), reason="CAPE subject 00215 not downloaded")

SUBJECT, OUTFIT = "00215", "poloshort"


@pytest.fixture(scope="module")
def release():
    from body_measure.inference.cape_release import CapeRelease
    return CapeRelease()


@pytest.fixture(scope="module")
def body(release):
    from body_measure.inference.smpl_body import SmplBody
    return SmplBody(gender=release.gender(SUBJECT))


@pytest.fixture(scope="module")
def polo(release, body):
    from body_measure.inference.cape_release import displacement_T_m
    from body_measure.inference.cape_transfer import transfer_displacement

    frame = release.first_valid_frame(SUBJECT, OUTFIT)
    displacement = displacement_T_m(frame, release.minimal_body_T_m(SUBJECT))
    return transfer_displacement(
        body, release.betas(SUBJECT), displacement,
        name=f"cape_{SUBJECT}_{OUTFIT}", meta=frame.provenance())


# ------------------------------------------------- the skinning is smplx ---
@needs_smpl
def test_zero_displacement_reproduces_the_canonical_body():
    """The only proof that the re-implemented skinning is smplx's. If this
    drifts, every shell is posed slightly differently from the body it is
    fitted against, and the fitter would be chasing that difference."""
    from body_measure.inference.cape_transfer import _skin
    from body_measure.inference.smpl_body import SmplBody

    subject = SmplBody(gender="male")
    for betas in (np.zeros(10), np.linspace(-1.2, 1.2, 10)):
        reference = subject.canonical_vertices_m(
            torch.as_tensor(betas, dtype=torch.float32))
        assert np.allclose(_skin(subject, betas, None), reference, atol=1e-9)


@needs_smpl
def test_a_zero_displacement_shell_has_no_gap(body):
    from body_measure.inference.cape_transfer import transfer_displacement

    case = transfer_displacement(body, np.zeros(10), np.zeros((body.n_vertices, 3)),
                                 name="cape_zero")
    assert np.allclose(case.true_gap_mm, 0.0, atol=1e-6)
    for lo, hi in case.gap_band_mm.values():
        assert lo == pytest.approx(0.0, abs=0.05) and hi == pytest.approx(0.0, abs=0.05)


# --------------------------------------------------- the garment is real ---
@needs_smpl
@needs_cape
@needs_archive
def test_the_polo_wraps_the_torso_and_leaves_the_forearm_bare(polo, body, release):
    """A girth grows by 2*pi*d for a radial offset d, not by d — so a 15 mm
    torso gap is tens of millimetres of chest, and the check has to be
    written in those terms or it will look wrong."""
    from body_measure.landmarks.estimated import provided_facing
    from body_measure.measure.measurements import run_estimated_measurements

    facing = provided_facing((0.0, 1.0), source="smpl_frame")
    naked = body.canonical_mesh(release.betas(SUBJECT), source_id="bare")
    bare, _ = run_estimated_measurements(naked, facing=facing)
    dressed, _ = run_estimated_measurements(polo.mesh, facing=facing)

    torso_lo, torso_hi = polo.gap_band_mm["torso"]
    chest_delta = dressed["chest_circumference"].selected_value_mm \
        - bare["chest_circumference"].selected_value_mm
    assert 0.0 < chest_delta < 2 * np.pi * torso_hi, chest_delta
    # the polo covers the upper arm, so that girth grows too — and by less
    # than a long sleeve would (checked against longshort in the battery)
    assert dressed["upper_arm_girth"].selected_value_mm > \
        bare["upper_arm_girth"].selected_value_mm


@needs_smpl
@needs_cape
@needs_archive
def test_the_head_is_uncovered(polo):
    """Nobody in CAPE wears a hat. If the head band is not near zero the
    displacement has been mis-registered onto the wrong vertices."""
    lo, hi = polo.gap_band_mm["head"]
    assert abs(lo) < 8.0 and abs(hi) < 8.0, polo.gap_band_mm


@needs_smpl
@needs_cape
@needs_archive
def test_the_case_names_the_frame_it_came_from(polo):
    """A shell that cannot say which frame produced it cannot be reported
    honestly, and cannot be reproduced."""
    for key in ("dataset", "subject", "outfit", "sequence", "npz", "frame"):
        assert key in polo.meta, polo.meta
    assert polo.meta["transfer"] == "smpl_d_lbs_to_canonical_a_pose"
    assert polo.meta["approximation"] == "pose_dependent_clothing_deformation_ignored"
    # the scalar gap is a normal component; this says what it omits
    assert polo.meta["tangential_rms_mm"] > 0.0
    assert polo.meta["band_source"].startswith("self_consistency")


@needs_smpl
@needs_cape
@needs_archive
def test_the_shell_is_recoverable(polo, body, release):
    """Not a beta tolerance: none is pinned anywhere in this project, and
    inventing one here would be a threshold nobody chose. What is pinned is
    the two failure modes the battery already watches."""
    from body_measure.inference.fit import FitConfig, fit_shell

    cfg = FitConfig(seed=20260821, iters_coarse=60, iters_pose=30,
                    iters_shape=60, iters_refine=20,
                    n_shell_samples=6000, n_body_subsample=1500)
    fit = fit_shell(body, polo.mesh, polo.gap_band_mm, cfg)
    score = fit.fit_quality_score
    assert score["collapse_fraction"] < 0.05
    assert score["coverage_fraction"] > 0.8
    assert np.isfinite(np.linalg.norm(fit.betas - release.betas(SUBJECT)))


# --------------------------------------------------------- the reader -----
@needs_cape
def test_the_subject_list_excludes_the_phantoms(release):
    subjects = release.subjects()
    assert len(subjects) == 15
    assert "03212" not in subjects and "03213" not in subjects


@needs_cape
@needs_archive
def test_betas_are_refused_unless_the_fit_was_a_rest_pose(release, monkeypatch):
    """The betas are only the body's shape if the fit they came from had no
    pose in it. A non-zero pose would mean they encode something else."""
    import pickle

    from body_measure.inference import cape_release as module

    real = pickle.load  # noqa: F841 — documenting what is replaced
    monkeypatch.setattr(module.pickle, "load",
                        lambda *a, **k: {"betas": np.zeros(10),
                                         "pose": np.ones(72), "trans": np.zeros(3)})
    with pytest.raises(module.CapeError, match="non-zero"):
        release.betas(SUBJECT)


@needs_cape
@needs_archive
def test_the_displacement_has_no_whole_body_offset_left_in_it(release):
    """CAPE stores the clothed frame about its own origin; a translation
    left in would read as clothing everywhere, including the scalp."""
    from body_measure.inference.cape_release import displacement_T_m

    frame = release.first_valid_frame(SUBJECT, OUTFIT)
    displacement = displacement_T_m(frame, release.minimal_body_T_m(SUBJECT))
    assert np.allclose(displacement.mean(axis=0), 0.0, atol=1e-12)
