"""The retrieval second opinion beside the chest-girth size, and the
pinned copy of the ITA_HE_26 chart in body_measure.

Pinned: the copy equals the desktop chart; the second opinion sits beside
the size and never replaces it or reaches the passport; a clothed scan
gets no retrieval because its girths are the garment's; a missing store
is said, not hidden; licence-restricted neighbours are counted, not named."""
import copy

import pytest

from body_measure.charts import ita_he_26
from body_measure.retrieval.record import LicenceClass, ScanRecord
from body_measure.retrieval.store import RecordStore
from studio import sizing_map
from studio.desktop import size_chart
from studio.simulation.config import Design


def test_the_body_measure_copy_of_the_chart_matches_the_desktop_chart():
    for key, values in ita_he_26.ROWS.items():
        assert tuple(float(v) for v in values) == size_chart.DIMS[key], key
    assert ita_he_26.SIZES == size_chart.SIZES


@pytest.mark.parametrize("size", size_chart.SIZES)
def test_body_targets_equal_the_drafter_inputs(size):
    design = Design()
    manual = size_chart.manual_measurements(size, design)
    targets = ita_he_26.body_targets(size, ita_he_26.Ease(
        chest_mm=design.chest_ease_mm, waist_mm=design.waist_ease_mm,
        hip_mm=design.hip_ease_mm, arm_mm=design.arm_ease_mm))
    for key, value in targets.items():
        assert value == pytest.approx(manual[key]["value"], abs=1e-3), (size, key)


def _store_around(job, path, licence):
    """A small store of bodies near the measured one: the job's own record
    scaled by a few percent, labelled as the pipeline would."""
    from body_measure.retrieval.estimator import query_from_measurements
    from body_measure.retrieval.record import stature_of

    values, usable = query_from_measurements(job.measurements, job.prototypes,
                                             stature_of(job.mesh))
    stature = values.pop("stature_mm")
    store = RecordStore.create(path)
    for i, f in enumerate((0.97, 0.98, 0.99, 1.0, 1.01, 1.02, 1.03, 1.04)):
        vals = {k: (None if v is None else v * f) for k, v in values.items()}
        q = {k: ("clean" if usable.get(k) else "rejected") for k in vals}
        store.append(ScanRecord(
            record_id=f"near{i}", source_type="synthetic_smpl", source_id=f"near{i}",
            licence_class=licence, population=None, pose="standing_a_pose", clothed=False,
            split="train", values=vals, quality=q, stature_mm=stature * f,
            size_labels={"en13402": job.sizing.label or "M"}, spec_version=8,
            pipeline_hash="test"))
    store.save()
    return store


def test_the_second_opinion_sits_beside_the_size(measured_job, tmp_path):
    job = copy.copy(measured_job)
    job.params = {**measured_job.params, "retrieval_db": str(tmp_path / "s")}
    _store_around(job, tmp_path / "s", LicenceClass.SYNTHETIC)
    second = sizing_map.second_opinion(job, "en13402", "men", clothed=False)
    assert second["status"] == "ok", second
    assert second["pathway"] == "retrieved_neighbours"
    assert second["size"] == (job.sizing.label or "M")
    assert second["ita_he_26"]["chart"] == "ITA_HE_26"
    assert second["neighbours_local_only"] == 0 and second["neighbours_named"]


def test_licensed_neighbours_are_counted_not_named(measured_job, tmp_path):
    job = copy.copy(measured_job)
    job.params = {**measured_job.params, "retrieval_db": str(tmp_path / "l")}
    _store_around(job, tmp_path / "l", LicenceClass.LOCAL_ONLY)
    second = sizing_map.second_opinion(job, "en13402", "men", clothed=False)
    assert second["neighbours_named"] == []
    assert second["neighbours_local_only"] > 0


def test_a_clothed_scan_gets_no_retrieval(measured_job):
    second = sizing_map.second_opinion(measured_job, "en13402", "men", clothed=True)
    assert second["status"] == "unavailable"
    assert "garment" in second["reason"]


def test_a_missing_store_is_said(measured_job, tmp_path, monkeypatch):
    job = copy.copy(measured_job)
    job.params = {**measured_job.params, "retrieval_db": str(tmp_path / "absent")}
    second = sizing_map.second_opinion(job, "en13402", "men", clothed=False)
    assert second["status"] == "no_store"
    assert "ita_he_26" in second  # the chart mapping needs no store


def test_the_second_opinion_never_reaches_the_passport_block(measured_job):
    block = sizing_map.customer_spec(measured_job, "regular")
    assert "second_opinion" not in block
    assert not any("_mm" in key for key in block)
