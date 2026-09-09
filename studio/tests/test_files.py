"""Licence badges are the one thing the file list must get right: the
page can be shown to people, and only HSRD-100 may appear in public."""
import pytest

from studio import files


def test_hsrd_is_public_and_everything_else_is_not():
    entries = files.catalogue()
    assert entries, "the catalogue is empty — body-measure/data is absent?"
    for entry in entries:
        if entry["group"] == "HSRD-100":
            assert entry["licence"]["public"] is True
            assert "CC BY 4.0" in entry["licence"]["badge"]
            assert entry["fixed"]["up_axis"] == "Z"
        else:
            assert entry["licence"]["public"] is False, entry["id"]


def test_texel_is_marked_non_commercial():
    for entry in files.catalogue():
        if entry["group"] == "Texel":
            assert "NC" in entry["licence"]["badge"]
            assert entry["fixed"] == {"unit": "mm", "up_axis": "Y"}


def test_a_generated_body_prefills_its_sidecar_unit_but_fixes_nothing():
    entry = files.find("generated:smpl_neutral0_apose")
    if entry is None:
        pytest.skip("generated body absent")
    assert entry["kind"] == "mesh_file"
    assert entry["defaults"]["unit"] == "m" and entry["defaults"]["up_axis"] == "Y"
    assert entry["fixed"] == {}


def test_upload_rejects_other_file_types(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "UPLOADS", tmp_path)
    with pytest.raises(ValueError):
        files.store_upload("model.stp", b"x")
    entry = files.store_upload("my body.obj", b"v 0 0 0\n")
    assert entry["kind"] == "mesh_file" and entry["licence"]["public"] is False
    assert entry["defaults"]["unit"] is None       # never guessed
