"""The claim taxonomy is a contract: a comparison may only be called what
its reference licenses. These tests exist so the rule survives edits."""
import pytest

from body_measure.result import empty_result
from body_measure.spec import load_spec
from body_measure.validate.claims import (
    CLAIM_BY_COMBINATION,
    INFERENCE_CATEGORIES,
    PATHWAYS,
    REFERENCE_KINDS,
    ClaimError,
    Comparison,
    claim_category_for,
    validate_claim,
)


def test_the_same_reference_licenses_different_claims_per_pathway():
    # a clothed scan against a body reference characterises the GARMENT
    assert claim_category_for("measured_clothed", "minimal_scan_surface") == "clothing_offset"
    # an inferred body against the same reference characterises the INFERENCE
    assert (
        claim_category_for("inferred_smpl_under_clothing", "minimal_scan_surface")
        == "reference_surface_agreement"
    )


def test_a_registration_never_licenses_a_minimal_scan_claim():
    # SIZER ships registrations; until a raw minimal scan is confirmed the
    # weaker wording is the only honest one
    assert (
        claim_category_for("inferred_smpl_under_clothing", "provided_body_registration")
        == "fit_reference_agreement"
    )


def test_measurement_accuracy_is_unreachable_until_a_tape_exists():
    assert REFERENCE_KINDS["manual_reference"].available is False
    with pytest.raises(ClaimError, match="not obtainable yet"):
        claim_category_for("estimated", "manual_reference")


def test_no_inference_pathway_can_reach_measurement_accuracy_by_another_route():
    for pathway, ref in CLAIM_BY_COMBINATION:
        if CLAIM_BY_COMBINATION[(pathway, ref)] == "measurement_accuracy":
            assert ref == "manual_reference", (pathway, ref)


def test_inference_categories_are_never_named_accuracy():
    assert "measurement_accuracy" not in INFERENCE_CATEGORIES


def test_an_undefined_combination_is_refused_not_guessed():
    # a clothed scan has no business being compared to closed-form shapes
    with pytest.raises(ClaimError, match="no claim is defined"):
        claim_category_for("measured_clothed", "analytic_expected")


def test_unknown_names_are_rejected():
    with pytest.raises(ClaimError, match="unknown pathway"):
        claim_category_for("vibes", "analytic_expected")
    with pytest.raises(ClaimError, match="unknown reference_kind"):
        claim_category_for("estimated", "vibes")


def test_comparison_carries_the_mandatory_provenance_fields():
    c = Comparison(
        pathway="inferred_smpl_under_clothing",
        reference_kind="provided_body_registration",
        reference_method="body_measure_pipeline",
        reference_model_id="sizer_smpl_neutral",
    )
    payload = c.to_dict()
    assert payload["claim_category"] == "fit_reference_agreement"
    assert set(payload) == {
        "claim_category", "pathway", "reference_kind",
        "reference_method", "reference_model_id",
    }


def test_mislabelling_a_comparison_raises():
    c = Comparison(
        pathway="measured_clothed",
        reference_kind="minimal_scan_surface",
        reference_method="body_measure_pipeline",
    )
    validate_claim(c, "clothing_offset")           # the licensed one
    with pytest.raises(ClaimError):
        validate_claim(c, "measurement_accuracy")  # the tempting one


def test_existing_unclothed_claims_are_unchanged():
    assert claim_category_for("estimated", "dataset_reference") == "dataset_agreement"
    assert claim_category_for("estimated", "analytic_expected") == "analytic_correctness"
    assert claim_category_for("estimated", "synthetic_reference") == "synthetic_agreement"


def test_every_pathway_declares_whether_it_infers_a_body():
    inferring = {n for n, p in PATHWAYS.items() if p.infers_body}
    assert inferring == {
        "inferred_smpl_under_clothing",
        "inferred_smpld_under_clothing",
    }


def test_result_accepts_the_new_pathways():
    spec = load_spec()
    for pathway in ("measured_clothed", "inferred_smpl_under_clothing"):
        result = empty_result(
            spec, source_type="dataset_scan", source_id="x", pathway=pathway
        )
        assert result.pathway in PATHWAYS
