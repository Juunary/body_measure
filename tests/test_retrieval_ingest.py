"""A mesh through the whole retrieval path: measured, recorded, stored,
queried back, and queried through the CLI. Uses the generated SMPL body
that the other data tests use; skips when it is absent."""
from pathlib import Path

import pytest

from body_measure.adapters.mesh_file import MeshFileAdapter
from body_measure.canonicalize import canonicalize
from body_measure.retrieval.calibration import Calibration
from body_measure.retrieval.estimator import estimate, query_from_measurements
from body_measure.retrieval.ingest import measure_mesh, record_from_measured
from body_measure.retrieval.record import LicenceClass, ScanRecord
from body_measure.retrieval.store import RecordStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BODY = PROJECT_ROOT / "data" / "generated" / "smpl_neutral0_apose.obj"
pytestmark = pytest.mark.skipif(not BODY.is_file(), reason="generated SMPL body absent")


@pytest.fixture(scope="module")
def measured():
    mesh = canonicalize(MeshFileAdapter().load(BODY, unit="m"))
    m = measure_mesh(mesh)
    assert m is not None, "the generated A-pose body passes the pose gate"
    return m


def test_a_measured_body_becomes_a_record_with_every_chart(measured):
    rec = record_from_measured(measured, record_id="n0", source_type="synthetic_smpl",
                               source_id="n0", licence_class=LicenceClass.SYNTHETIC,
                               population=None, spec_version=8, pipeline_hash="t")
    assert rec.usable("chest_circumference") and rec.usable("stature_mm")
    assert set(rec.size_labels) >= {"en13402", "en13402-women", "lacoste", "ita_he_26"}
    assert rec.size_labels["en13402"] == "M"
    assert rec.size_labels["ita_he_26"] == "50"
    assert ScanRecord.from_json(rec.to_json()) == rec


def test_a_body_finds_its_own_record_at_distance_zero(measured, tmp_path):
    store = RecordStore.create(tmp_path / "s")
    for i, f in enumerate((0.96, 0.98, 1.0, 1.02, 1.04)):
        rec = record_from_measured(measured, record_id=f"r{i}", source_type="synthetic_smpl",
                                   source_id=f"r{i}", licence_class=LicenceClass.SYNTHETIC,
                                   population=None, spec_version=8, pipeline_hash="t")
        data = rec.to_dict()
        data["values"] = {k: (None if v is None else v * f) for k, v in data["values"].items()}
        data["stature_mm"] *= f
        store.append(ScanRecord.from_dict(data))
    store.save()
    values, usable = query_from_measurements(measured.measurements, measured.prototypes,
                                             measured.stature_mm)
    cal = Calibration(threshold=1.0, sigma=0.5, k=3, coverage=0.95, n=5,
                      records_sha256="", split_used="train", per_key_spread={})
    est = estimate(store, store.index(), cal, values, usable, k=3)
    assert est.neighbours[0].record_id == "r2"
    assert est.nearest_distance == pytest.approx(0.0, abs=1e-6)


def test_the_cli_builds_and_queries_a_store(tmp_path, capsys):
    from body_measure.cli import main

    mesh_dir = tmp_path / "meshes"
    mesh_dir.mkdir()
    (mesh_dir / BODY.name).write_bytes(BODY.read_bytes())
    db = tmp_path / "db"
    assert main(["index", "build", "--db", str(db), "--source", "meshes", "--mesh-dir",
                 str(mesh_dir), "--input-unit", "m", "--licence", "synthetic_smpl"]) == 0
    store = RecordStore.open(db)
    assert len(store) == 1 and store.records[0].licence_class is LicenceClass.SYNTHETIC
    # a one-record store cannot calibrate; the query says so instead of crashing
    capsys.readouterr()
    assert main(["index", "query", "--db", str(db), str(BODY), "--input-unit", "m"]) == 1
    assert "calibration records" in capsys.readouterr().err
    assert main(["index", "export", "--db", str(db), "--dest", str(tmp_path / "copy")]) == 0
