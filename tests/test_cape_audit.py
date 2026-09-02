"""The CAPE audit decides what we are allowed to say about CAPE.

The single most important thing it must do is come out WEAK. Pointing the
SIZER audit at CAPE produces the strongest claim in the vocabulary —
`minimal_body_shape/` matches its `(minimal|...)` pattern and every
registration is filed as a raw scan — on a dataset that ships no scans at
all. So the first test here is the one that would have caught that, and it
is written to fail loudly rather than quietly downgrade.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_cape_manifest.py"
spec = importlib.util.spec_from_file_location("audit_cape_manifest", SCRIPT)
audit = importlib.util.module_from_spec(spec)
sys.modules["audit_cape_manifest"] = audit
spec.loader.exec_module(audit)


def make_release(root: Path, subjects=("00215", "00096"), *, with_betas=True):
    """A miniature CAPE with the real directory shapes."""
    release = root / "cape_release"
    (release / "misc").mkdir(parents=True)
    (release / "seq_lists").mkdir(parents=True)
    (release / "misc" / "smpl_tris.npy").write_bytes(b"0")
    for subject in subjects:
        body = release / "minimal_body_shape" / subject
        body.mkdir(parents=True)
        (body / f"{subject}_minimal.ply").write_bytes(b"0")
        (body / f"{subject}_minimal.npy").write_bytes(b"0")
        params = root / "minimal_body_params" / "minimal_body_shape" / subject
        params.mkdir(parents=True)
        if with_betas:
            (params / f"{subject}_param.pkl").write_bytes(b"0")
        (params / f"{subject}_optimized.obj").write_bytes(b"0")
        (release / "seq_lists" / f"seq_list_{subject}.txt").write_text(
            f"{subject} (male)\nsequence name\t#valid frames\n\n"
            "poloshort_hips\t100\t\nposhortless_x\t10\t\n"
            "poloshort_squats\t120\t\nlongshort_hips\t90\t\n",
            encoding="utf-8")
    return root


# ------------------------------------------------ the verdict must be weak ---
def test_the_verdict_never_claims_a_minimal_scan(tmp_path):
    """CAPE ships registrations. If this ever reads True, an adapter built
    on it would license `minimal_scan_surface` — the strongest reference
    kind — against a fitted T-pose body (decision #34)."""
    manifest = audit.build_manifest(make_release(tmp_path))
    assert manifest["verdict"]["raw_minimal_scan_available"] is False
    assert manifest["verdict"]["claim_wording"] == (
        "same-subject provided body-reference surface")


def test_the_body_files_are_registrations_not_scans(tmp_path):
    manifest = audit.build_manifest(make_release(tmp_path))
    roles = {e["relative_source_path"]: e["surface_role"] for e in manifest["entries"]}
    body = "cape_release/minimal_body_shape/00215/00215_minimal.ply"
    assert roles[body] == "provided_body_registration_tpose"
    kinds = {e["surface_role"]: e["reference_kind"] for e in manifest["entries"]}
    assert kinds["provided_body_registration_tpose"] == "provided_body_registration"
    assert "minimal_scan_surface" not in set(kinds.values())


def test_a_directory_name_cannot_promote_a_role(tmp_path):
    """The SIZER audit matched patterns against the whole path, so the
    directory `minimal_body_shape` decided the role. Classification here is
    by position, and this pins that a file merely LIVING under a
    suggestively named directory gets nothing from it."""
    root = make_release(tmp_path)
    stray = root / "cape_release" / "minimal_body_shape" / "00215" / "something.bin"
    stray.write_bytes(b"0")
    manifest = audit.build_manifest(root)
    roles = {e["relative_source_path"]: e["surface_role"] for e in manifest["entries"]}
    assert roles[
        "cape_release/minimal_body_shape/00215/something.bin"] == "unclassified"


# --------------------------------------------------------- the subjects ---
def test_the_subject_list_is_the_intersection_not_one_file(tmp_path):
    """subj_genders.pkl lists 17; three other places list 15. Reading the
    file most obviously meant for it invents two subjects."""
    import pickle

    root = make_release(tmp_path)
    with open(root / "cape_release" / "misc" / "subj_genders.pkl", "wb") as handle:
        pickle.dump({"00215": "male", "00096": "male",
                     "03212": "male", "03213": "male"}, handle)
    manifest = audit.build_manifest(root)
    assert manifest["subjects"] == ["00096", "00215"]
    assert manifest["phantom_subjects"] == ["03212", "03213"]


def test_a_subject_without_betas_is_not_a_subject(tmp_path):
    """The body has to be rebuilt from betas to be measurable at all, so a
    subject missing them is not usable however many surfaces it ships."""
    manifest = audit.build_manifest(make_release(tmp_path, with_betas=False))
    assert manifest["subjects"] == []


# ------------------------------------------------------- the frame rule ---
def test_the_frame_rule_takes_one_frame_per_outfit_in_release_order(tmp_path):
    root = make_release(tmp_path, subjects=("00215",))
    sequences = audit.sequences_from_seq_lists(root)
    frames = {"00215": {"poloshort_hips": ["a.000002.npz", "a.000001.npz"],
                        "poloshort_squats": ["b.000001.npz"],
                        "longshort_hips": ["c.000005.npz"]}}
    picked = audit.pick_frames(sequences, frames)
    assert set(picked["00215"]) == {"poloshort", "longshort"}
    # first sequence of the outfit in seq_list order, lowest-numbered frame
    assert picked["00215"]["poloshort"] == {
        "sequence": "poloshort_hips", "npz": "a.000001.npz"}


def test_the_frame_rule_is_hashed_into_the_split(tmp_path):
    """How many frames a subject contributes changes every N computed from
    it, so the rule is part of the split, not a detail beside it."""
    manifest = audit.build_manifest(make_release(tmp_path))
    split = audit.build_split(manifest)
    assert split["frame_rule"] == manifest["frame_rule"]
    other = dict(manifest, frame_rule="every frame")
    assert audit.build_split(other)["sha256"] != split["sha256"]


def test_the_split_is_subject_disjoint_and_deterministic(tmp_path):
    manifest = audit.build_manifest(make_release(tmp_path))
    split = audit.build_split(manifest)
    assert not set(split["train_subjects"]) & set(split["test_subjects"])
    assert sorted(split["train_subjects"] + split["test_subjects"]) == manifest["subjects"]
    assert audit.build_split(manifest)["sha256"] == split["sha256"]
    assert audit.build_split(manifest, seed=1)["sha256"] != split["sha256"]


# ------------------------------------------------------- what it ignores ---
def test_dot_directories_and_parsing_code_are_not_dataset_files(tmp_path):
    """A dot-directory inside the release did not come from CAPE — editor
    and tool state has been written into working directories before — and
    cape_utils is the parsing code, not data."""
    root = make_release(tmp_path)
    (root / "cape_release" / ".local_state" / "cache").mkdir(parents=True)
    (root / "cape_release" / ".local_state" / "cache" / "s.json").write_text("{}")
    (root / "cape_release" / "cape_utils").mkdir()
    (root / "cape_release" / "cape_utils" / "dataset_utils.py").write_text("x = 1")
    paths = {e["relative_source_path"] for e in audit.build_manifest(root)["entries"]}
    assert not any(".local_state" in p or "cape_utils" in p for p in paths)


def test_every_reference_kind_is_in_the_claims_vocabulary(tmp_path):
    from body_measure.validate.claims import REFERENCE_KINDS

    for entry in audit.build_manifest(make_release(tmp_path))["entries"]:
        if entry["reference_kind"] is not None:
            assert entry["reference_kind"] in REFERENCE_KINDS


# ------------------------------------------------- against the real thing ---
CAPE_ROOT = Path(__file__).resolve().parents[1] / "data" / "external" / "cape"
needs_cape = pytest.mark.skipif(not (CAPE_ROOT / "cape_release").is_dir(),
                                reason="CAPE release absent")


@needs_cape
def test_the_real_release_audits_to_the_weak_verdict():
    report = Path(__file__).resolve().parents[1] / "reports" / "cape-manifest.json"
    if not report.is_file():
        pytest.skip("run scripts/audit_cape_manifest.py first")
    manifest = json.loads(report.read_text(encoding="utf-8"))
    assert manifest["verdict"]["raw_minimal_scan_available"] is False
    assert manifest["role_counts"].get("unclassified", 0) == 0
    assert len(manifest["subjects"]) == 15
    assert manifest["phantom_subjects"] == ["03212", "03213"]
    # the polo is why 00215 was downloaded
    assert "poloshort" in manifest["outfits_per_subject"]["00215"]
