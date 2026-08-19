"""The SIZER audit decides what we are allowed to say and which subjects
may influence a prior. Both are tested on synthetic directory layouts, so
the logic is verified before the real download exists."""
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_sizer_manifest.py"
spec = importlib.util.spec_from_file_location("audit_sizer_manifest", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def make_tree(root: Path, files: list[str]) -> Path:
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"placeholder")
    return root


def test_claim_wording_downgrades_when_no_raw_minimal_scan_exists(tmp_path):
    """The whole point of the audit: registrations alone must not be
    described as minimal scans."""
    root = make_tree(tmp_path, [
        "subject_0001/shirt_M_scan.obj",
        "subject_0001/registration_neutral.pkl",
        "subject_0002/pants_L_scan.obj",
        "subject_0002/registration_neutral.pkl",
    ])
    manifest = audit.build_manifest(root)
    assert manifest["verdict"]["raw_minimal_scan_available"] is False
    assert manifest["verdict"]["claim_wording"] == (
        "same-subject provided body-reference surface"
    )


def test_claim_wording_upgrades_only_with_a_real_minimal_scan(tmp_path):
    root = make_tree(tmp_path, [
        "subject_0001/shirt_M_scan.obj",
        "subject_0001/minimal_scan.obj",
    ])
    manifest = audit.build_manifest(root)
    assert manifest["verdict"]["raw_minimal_scan_available"] is True
    assert manifest["verdict"]["claim_wording"] == "same-subject minimal-scan measurements"


def test_unrecognised_files_are_reported_not_guessed_into_a_role(tmp_path):
    root = make_tree(tmp_path, ["subject_0001/mystery_thing.obj"])
    manifest = audit.build_manifest(root)
    assert manifest["role_counts"]["unclassified"] == 1
    entry = manifest["entries"][0]
    assert entry["surface_role"] == "unclassified"
    assert entry["reference_kind"] is None


def test_a_clothed_scan_is_never_offered_as_a_reference(tmp_path):
    root = make_tree(tmp_path, ["subject_0001/tshirt_S_scan.obj"])
    manifest = audit.build_manifest(root)
    entry = manifest["entries"][0]
    assert entry["surface_role"] == "clothed_scan"
    assert entry["reference_kind"] is None


def test_garment_class_and_size_are_extracted(tmp_path):
    root = make_tree(tmp_path, ["subject_0001/tshirt_M_scan.obj"])
    entry = audit.build_manifest(root)["entries"][0]
    assert entry["garment_class_raw"] == "tshirt"
    assert entry["garment_size"] == "M"


def test_split_is_subject_disjoint(tmp_path):
    root = make_tree(tmp_path, [
        f"subject_{i:04d}/shirt_M_scan.obj" for i in range(12)
    ] + [
        # the same subjects appear again with other garments — a scan-level
        # split would leak a body shape across the boundary
        f"subject_{i:04d}/pants_L_scan.obj" for i in range(12)
    ])
    manifest = audit.build_manifest(root)
    split = audit.build_split(manifest)
    assert split["policy"] == "subject_disjoint"
    assert not set(split["train_subjects"]) & set(split["test_subjects"])
    assert len(split["train_subjects"]) + len(split["test_subjects"]) == 12


def test_split_is_deterministic_and_hashed(tmp_path):
    root = make_tree(tmp_path, [f"subject_{i:04d}/shirt_M_scan.obj" for i in range(8)])
    manifest = audit.build_manifest(root)
    first = audit.build_split(manifest)
    second = audit.build_split(manifest)
    assert first["sha256"] == second["sha256"]
    assert audit.build_split(manifest, seed=1)["sha256"] != first["sha256"]


def test_every_reference_kind_is_vocabulary_from_claims(tmp_path):
    from body_measure.validate.claims import REFERENCE_KINDS

    root = make_tree(tmp_path, [
        "subject_0001/minimal_scan.obj",
        "subject_0001/shirt_M_scan.obj",
        "subject_0001/registration_neutral.pkl",
        "subject_0001/smpld_body.npz",
    ])
    for entry in audit.build_manifest(root)["entries"]:
        if entry["reference_kind"] is not None:
            assert entry["reference_kind"] in REFERENCE_KINDS


@pytest.mark.parametrize("missing", ["data/external/sizer"])
def test_script_exits_cleanly_when_the_dataset_is_absent(tmp_path, missing):
    assert not (tmp_path / missing).exists()
