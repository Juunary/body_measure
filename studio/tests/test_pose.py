"""The pose gate refuses what the spec was not written for, and nothing
else: a fashion scan with boots and hanging arms, and a T pose, are out;
an A-pose body is in."""
import pytest

from studio import files, meshio, pose


def _mesh(file_id):
    entry = files.find(file_id)
    if entry is None:
        pytest.skip(f"{file_id} absent")
    _, mesh, _ = meshio.load_surface(entry, entry["defaults"]["unit"], entry["defaults"]["up_axis"])
    return mesh


def test_an_a_pose_body_passes():
    verdict = pose.check_pose(_mesh("generated:smpl_neutral0_apose"))
    assert verdict.ok, verdict.reasons
    assert verdict.checks["arms"]["fraction"] == 1.0


def test_a_t_pose_is_refused_for_its_arms():
    verdict = pose.check_pose(_mesh("generated:smpl_neutral0_tpose"))
    assert not verdict.ok
    assert any("arms" in r for r in verdict.reasons)


def test_the_hsrd_fashion_scan_is_refused_before_measuring():
    verdict = pose.check_pose(_mesh("hsrd:lod2"))
    assert not verdict.ok
    assert any("front and back" in r for r in verdict.reasons)


def test_the_measure_stage_stops_on_a_rejected_pose():
    from studio import pipeline
    from studio.jobs import REGISTRY
    entry = files.find("hsrd:lod2")
    if entry is None:
        pytest.skip("hsrd absent")
    job = REGISTRY.create({"unit": None, "up_axis": None, "clothed": True, "population": "women",
                           "chart": "en13402", "replay": {"delay": 0.0}}, entry)
    pipeline.run_load(job)
    pipeline.run_measure(job)
    assert job.state == "pose_rejected"
    assert not job.measurements and job.document_path is None
    stages = [e["name"] for e in job.events if e["type"] == "stage" and e["status"] == "start"]
    assert stages[-1] == "pose"
