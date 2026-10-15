"""Retrieval store, index, estimator and licence gate.

The rules pinned here: a record round-trips and refuses a foreign schema;
untrusted values never enter a distance; the index compares only keys
both sides have; the estimator abstains outside what the store knows and
refuses a split vote; and a licensed record cannot leave the machine.
All of it runs on hand-made records, no mesh and no dataset needed."""
import json

import numpy as np
import pytest

from body_measure import sizing
from body_measure.garment_prototypes import POLO_SET
from body_measure.retrieval.calibration import Calibration, fit_calibration
from body_measure.retrieval.estimator import UNLABELLED, estimate, weighted_median
from body_measure.retrieval.evaluate import run_track
from body_measure.retrieval.features import (
    FEATURE_KEYS, INDEX_KEYS, PROTOTYPE_KEYS, SPEC_KEYS, STATURE_KEY, fit_standardiser,
    raw_vector, vectorise,
)
from body_measure.retrieval.index import BruteForceIndex
from body_measure.retrieval.record import LicenceClass, ScanRecord
from body_measure.retrieval.store import LicenceExportError, RecordStore, StoreError
from body_measure.spec import load_spec


def body(chest, *, rid, licence=LicenceClass.SYNTHETIC, split="train", population=None,
         quality=None, label=..., scale=1.0):
    """A plausible body whose every key scales with the chest."""
    f = chest / 1000.0
    values = {
        "chest_circumference": chest, "waist_circumference": 850 * f,
        "neck_circumference": 380 * f, "upper_arm_girth": 300 * f,
        "across_back_shoulder_width": 400 * f, "sleeve_length": 600 * f,
        "back_length": 420 * f, "hip_girth": 1000 * f, "sleeve_opening_girth": 260 * f,
        "armhole_depth": 150 * f, "shoulder_slope": 14.0, "front_back_width": None,
    }
    q = {k: "clean" for k in values}
    q["front_back_width"] = "rejected"
    q.update(quality or {})
    if label is ...:
        band = next((b for b in sizing.EN_13402_3.bands
                     if b.chest_min_cm * 10 <= chest < b.chest_max_cm * 10), None)
        label = None if band is None else band.label
    return ScanRecord(
        record_id=rid, source_type="synthetic_smpl", source_id=rid, licence_class=licence,
        population=population, pose="standing_a_pose", clothed=False, split=split,
        values=values, quality=q, stature_mm=1750 * scale, size_labels={"en13402": label},
        spec_version=8, pipeline_hash="test")


@pytest.fixture
def store(tmp_path):
    s = RecordStore.create(tmp_path / "s")
    for i, chest in enumerate(np.linspace(880, 1200, 81)):
        s.append(body(float(chest), rid=f"b{i:03d}"))
    s.save()
    return s


# ----------------------------------------------------------------- record --
def test_prototype_keys_are_the_polo_set():
    assert PROTOTYPE_KEYS == POLO_SET


def test_spec_keys_are_the_spec():
    assert SPEC_KEYS == load_spec().names


def test_a_record_round_trips_through_json():
    r = body(1000.0, rid="a")
    back = ScanRecord.from_json(r.to_json())
    assert back == r
    assert back.licence_class is LicenceClass.SYNTHETIC


def test_a_record_of_another_schema_is_refused():
    data = body(1000.0, rid="a").to_dict()
    data["record_schema_version"] = 99
    with pytest.raises(ValueError, match="schema"):
        ScanRecord.from_dict(data)


def test_a_record_refuses_keys_outside_the_feature_space():
    data = body(1000.0, rid="a").to_dict()
    data["values"]["shoe_size"] = 44.0
    with pytest.raises(ValueError, match="FEATURE_KEYS"):
        ScanRecord.from_dict(data)


def test_untrusted_values_are_not_usable():
    r = body(1000.0, rid="a", quality={"waist_circumference": "manual_review",
                                       "neck_circumference": "rejected"})
    assert not r.usable("waist_circumference")
    assert not r.usable("neck_circumference")
    assert not r.usable("front_back_width")
    assert r.usable("chest_circumference")  # arm_clipped-like flags stay usable


# --------------------------------------------------------------- features --
def test_a_masked_key_contributes_zero_even_unmasked_by_mistake():
    rows = [raw_vector({"chest_circumference": c, STATURE_KEY: 1700.0}) for c in (900, 1000, 1100)]
    space = fit_standardiser(rows)
    z, mask = vectorise(space, {"chest_circumference": 1000.0})
    assert mask.sum() == 1
    assert np.count_nonzero(z) == 0  # 1000 is the mean, everything else masked to 0


def test_a_key_nobody_has_keeps_the_space_width_and_is_listed_thin():
    rows = [raw_vector({"chest_circumference": c}) for c in (900, 1000, 1100)]
    space = fit_standardiser(rows)
    assert space.dim == len(FEATURE_KEYS)
    assert "sleeve_length" in space.thin_keys


def test_the_space_round_trips_its_index_keys():
    space = fit_standardiser([raw_vector({k: 100.0 + i for k in FEATURE_KEYS}) for i in range(6)])
    assert space.index_keys == INDEX_KEYS
    assert type(space).from_dict(space.to_dict()) == space


def test_a_space_saved_before_index_keys_read_every_key():
    space = fit_standardiser([raw_vector({k: 100.0 + i for k in FEATURE_KEYS}) for i in range(6)])
    old = space.to_dict()
    del old["index_keys"]
    assert type(space).from_dict(old).index_keys == FEATURE_KEYS


def test_a_key_outside_the_index_never_chooses_the_neighbours(store):
    """armhole_depth is estimated and reported, but a query with an absurd
    armhole finds the same neighbours as one with a plausible one."""
    cal = fit_calibration(store, k=5)
    q = body(1000.0, rid="q")
    a = estimate(store, store.index(), cal, q.feature_values(), q.feature_usable(), k=5)
    odd = {**q.feature_values(), "armhole_depth": 900.0, "shoulder_slope": 80.0}
    b = estimate(store, store.index(), cal, odd, q.feature_usable(), k=5)
    assert a.neighbour_ids == b.neighbour_ids
    assert b.values["armhole_depth"] is not None


def test_a_calibration_from_another_space_is_refitted(store):
    from body_measure.retrieval.calibration import load_or_fit

    cal = fit_calibration(store, k=5)
    store.save_calibration({**cal.to_dict(), "space_key": "meas-v1:everything"})
    _, flags = load_or_fit(store)
    assert flags == ["calibration_stale_refitted"]
    store.save_calibration(cal.to_dict())
    assert load_or_fit(store)[1] == []


# ------------------------------------------------------------------ index --
def test_distance_uses_only_shared_keys():
    Z = np.array([[0.0, 0.0, 0.0, 0.0, 5.0],
                  [1.0, 1.0, 1.0, 1.0, 0.0]])
    mask = np.array([[True, True, True, True, True],
                     [True, True, True, True, False]])
    idx = BruteForceIndex(Z, mask, ["a", "b"])
    q = np.zeros(5)
    qmask = np.array([True, True, True, True, False])  # query lacks key 4
    d, n = idx.distances(q, qmask)
    assert d[0] == 0.0  # key 4's 5.0 never counted
    assert d[1] == pytest.approx(1.0)
    assert list(n) == [4, 4]


def test_too_few_shared_keys_is_not_comparable():
    Z = np.zeros((1, 5))
    mask = np.array([[True, True, True, False, False]])
    idx = BruteForceIndex(Z, mask, ["a"])
    d, _ = idx.distances(np.zeros(5), np.ones(5, dtype=bool))
    assert np.isinf(d[0])
    pos, _, _ = idx.query(np.zeros(5), np.ones(5, dtype=bool), k=3)
    assert pos.size == 0


def test_query_excludes_and_caps_k():
    Z = np.arange(5, dtype=float)[:, None].repeat(4, axis=1)
    idx = BruteForceIndex(Z, np.ones_like(Z, dtype=bool), list("abcde"))
    pos, d, _ = idx.query(np.zeros(4), np.ones(4, dtype=bool), k=10, exclude=["a"])
    assert [idx.ids[p] for p in pos] == ["b", "c", "d", "e"]
    assert list(d) == sorted(d)


def test_weighted_median():
    assert weighted_median(np.array([1.0, 2.0, 100.0]), np.array([1.0, 1.0, 0.1])) == 2.0


# ------------------------------------------------------------------ store --
def test_store_round_trips_and_hashes(store):
    again = RecordStore.open(store.path)
    assert again.ids == store.ids
    assert again.records_sha256() == store.records_sha256()
    manifest = json.loads((store.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["n_records"] == 81
    assert manifest["n_by_licence_class"] == {"synthetic_smpl": 81}


def test_store_refuses_duplicate_ids(store):
    with pytest.raises(StoreError, match="already"):
        store.append(body(1000.0, rid="b000"))


def test_store_refuses_to_be_created_over_an_existing_one(store):
    with pytest.raises(StoreError, match="exists"):
        RecordStore.create(store.path)


def test_export_of_synthetic_records_works(store, tmp_path):
    dest = store.export(tmp_path / "out")
    assert RecordStore.open(dest).ids == store.ids


def test_export_refuses_a_single_licensed_record_and_writes_nothing(store, tmp_path):
    store.append(body(1000.0, rid="texel/Man0", licence=LicenceClass.LOCAL_ONLY))
    store.save()
    dest = tmp_path / "out"
    with pytest.raises(LicenceExportError, match="local_only_licensed"):
        store.export(dest)
    assert not dest.exists()


def test_a_merge_carries_the_licence_with_it(store, tmp_path):
    local = RecordStore.create(tmp_path / "local")
    local.append(body(1000.0, rid="nomo/x", licence=LicenceClass.LOCAL_ONLY))
    local.save()
    merged = RecordStore.merged(tmp_path / "m", [store, local])
    merged.save()
    with pytest.raises(LicenceExportError):
        merged.export(tmp_path / "out")


# ------------------------------------------------------------ calibration --
def test_calibration_uses_the_train_split_only(tmp_path):
    s = RecordStore.create(tmp_path / "s")
    for i, chest in enumerate(np.linspace(900, 1100, 30)):
        s.append(body(float(chest), rid=f"t{i}", split="train"))
    s.append(body(2000.0, rid="far", split="holdout"))
    s.save()
    cal = fit_calibration(s, k=5)
    assert cal.split_used == "train"
    assert cal.n == 30
    assert cal.threshold < 1.0  # the far holdout body did not widen it


# -------------------------------------------------------------- estimator --
def test_an_in_distribution_body_gets_its_size(store):
    cal = fit_calibration(store, k=7)
    q = body(985.0, rid="q")
    est = estimate(store, store.index(), cal, q.feature_values(), q.feature_usable(), k=7)
    assert not est.abstained
    assert est.values["chest_circumference"] == pytest.approx(985.0, abs=15.0)
    out = est.to_size_assignment(sizing.EN_13402_3)
    assert out.label == "M"
    assert "retrieval_pathway" in out.flags
    assert sum(out.probabilities.values()) == pytest.approx(1.0, abs=1e-3)


def test_a_body_outside_the_store_abstains(store):
    cal = fit_calibration(store, k=7)
    q = body(1600.0, rid="q")
    est = estimate(store, store.index(), cal, q.feature_values(), q.feature_usable())
    assert est.abstained
    assert "out_of_reference_manifold" in est.flags
    out = est.to_size_assignment(sizing.EN_13402_3)
    assert out.label is None and "retrieval_abstained" in out.flags


def test_no_usable_chest_abstains(store):
    cal = fit_calibration(store, k=7)
    q = body(1000.0, rid="q", quality={"chest_circumference": "rejected"})
    est = estimate(store, store.index(), cal, q.feature_values(), q.feature_usable())
    assert est.abstained and "chest" in est.abstain_reason


def test_exclude_ids_keeps_a_body_from_finding_itself(store):
    cal = fit_calibration(store, k=3)
    rec = store.records[40]
    est = estimate(store, store.index(), cal, rec.feature_values(), rec.feature_usable(),
                   k=3, exclude_ids=[rec.record_id])
    assert rec.record_id not in est.neighbour_ids
    assert est.nearest_distance > 0


def test_population_excludes_the_other_population(tmp_path):
    s = RecordStore.create(tmp_path / "s")
    for i, chest in enumerate(np.linspace(900, 1100, 20)):
        s.append(body(float(chest), rid=f"w{i}", population="women"))
        s.append(body(float(chest) + 1, rid=f"m{i}", population="men"))
    s.save()
    cal = fit_calibration(s, k=5)
    q = body(1000.0, rid="q")
    est = estimate(s, s.index(), cal, q.feature_values(), q.feature_usable(), population="men")
    assert all(n.population == "men" for n in est.neighbours)


def test_a_neighbour_the_chart_refused_keeps_its_weight(tmp_path):
    s = RecordStore.create(tmp_path / "s")
    for i in range(6):
        s.append(body(1000.0 + i, rid=f"ok{i}"))
        s.append(body(1000.5 + i, rid=f"refused{i}", label=None))
    s.save()
    cal = Calibration(threshold=10.0, sigma=1.0, k=12, coverage=0.95, n=12,
                      records_sha256="", split_used="train", per_key_spread={})
    q = body(1003.0, rid="q")
    est = estimate(s, s.index(), cal, q.feature_values(), q.feature_usable(), k=12)
    votes = est.size_votes["en13402"]
    assert votes[UNLABELLED] == pytest.approx(0.5, abs=0.05)
    assert sum(votes.values()) == pytest.approx(1.0, abs=1e-3)
    # half the neighbourhood refused: no label clears the 50 % bar alone
    out = est.to_size_assignment(sizing.EN_13402_3)
    assert out.probabilities[sizing.NEIGHBOUR_REFUSED] == pytest.approx(0.5, abs=0.05)


# ----------------------------------------------------------------- votes ---
def test_a_split_vote_is_refused_not_resolved_by_plurality():
    out = sizing.assign_from_votes(sizing.EN_13402_3, {"M": 0.45, "L": 0.40, "S": 0.15}, k=10)
    assert out.label is None
    assert "ambiguous_size" in out.flags
    assert out.probabilities["M"] == pytest.approx(0.45)


def test_a_clear_vote_names_its_runner_up():
    out = sizing.assign_from_votes(sizing.EN_13402_3, {"M": 0.7, "L": 0.3}, k=10)
    assert out.label == "M" and out.alternative == "L"
    assert "near_size_boundary" in out.flags


def test_refused_neighbours_stay_visible_in_the_probabilities():
    out = sizing.assign_from_votes(
        sizing.EN_13402_3, {"XXL": 0.6, sizing.NEIGHBOUR_REFUSED: 0.4}, k=10)
    assert out.label == "XXL"
    assert out.probabilities[sizing.NEIGHBOUR_REFUSED] == pytest.approx(0.4)


def test_votes_with_labels_from_another_chart_raise():
    with pytest.raises(ValueError, match="not on"):
        sizing.assign_from_votes(sizing.EN_13402_3, {"4 (M)": 1.0}, k=1)


# ------------------------------------------------------------------- eval --
def test_the_real_track_is_labelled_an_agreement_not_accuracy(store):
    cal = fit_calibration(store, k=5)
    result = run_track(store, cal, "real", store.records[10:20], k=5)
    assert result["claim_category"] == "reference_surface_agreement"
    assert result["n_queries"] == 10
    assert result["label_agreement"]["en13402"]["n"] > 0


def test_the_synthetic_track_is_synthetic_recovery(store):
    cal = fit_calibration(store, k=5)
    result = run_track(store, cal, "synthetic", store.records[:5], k=5)
    assert result["claim_category"] == "synthetic_recovery"
