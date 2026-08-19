"""What a comparison is allowed to CLAIM.

stats.py computes numbers; this module decides what those numbers may be
called. The two are deliberately separate — a mislabelled claim is worse
than a wrong number, because a wrong number invites checking and a
mislabelled claim invites trust.

Two orthogonal axes decide a claim:

  pathway        how the measured value was produced
  reference_kind what it was compared against

The claim category follows from the PAIR, not from either alone. Measuring
a clothed scan against a body reference yields a *clothing offset*;
measuring an inferred body against the same reference yields an
*agreement*. Same reference, different claim, because the thing being
characterised differs.

Combinations not listed are refused rather than guessed — the same
no-substitution rule the measurement core follows for a rejected slice.
"""
from __future__ import annotations

from dataclasses import dataclass


class ClaimError(ValueError):
    """A comparison was labelled with a claim its reference cannot license."""


# --------------------------------------------------------------- pathways --
@dataclass(frozen=True)
class Pathway:
    name: str
    description: str
    #: True when the body being measured was inferred rather than scanned.
    #: Inferred bodies carry per-measurement uncertainty and may abstain.
    infers_body: bool


PATHWAYS: dict[str, Pathway] = {
    p.name: p
    for p in (
        Pathway("estimated", "landmarks estimated from the surface itself", False),
        Pathway("fitted_vertices", "landmarks taken from a fitted model's vertices", False),
        Pathway("measured_clothed", "the pipeline run unchanged on a clothed scan", False),
        Pathway(
            "inferred_smpl_under_clothing",
            "base SMPL recovered from a clothed scan, measured in canonical pose",
            True,
        ),
        Pathway(
            "inferred_smpld_under_clothing",
            "SMPL+D (base shape plus per-vertex offsets) recovered from a clothed scan",
            True,
        ),
    )
}


# ------------------------------------------------------- reference tiers ---
@dataclass(frozen=True)
class ReferenceKind:
    name: str
    description: str
    #: False while the project cannot yet obtain this reference. Using an
    #: unavailable reference raises — the rule is enforced, not remembered.
    available: bool = True


REFERENCE_KINDS: dict[str, ReferenceKind] = {
    r.name: r
    for r in (
        ReferenceKind(
            "analytic_expected",
            "closed-form values of synthetic shapes (2*pi*r, Ramanujan). True ground truth.",
        ),
        ReferenceKind(
            "synthetic_reference",
            "another implementation measuring identical synthetic bodies.",
        ),
        ReferenceKind(
            "dataset_reference",
            "the dataset's own automatic values (Texel BodyFit, NOMO TC2).",
        ),
        ReferenceKind(
            "minimal_scan_surface",
            "the same subject's minimal-clothing scan, measured by THIS pipeline.",
        ),
        ReferenceKind(
            "provided_body_registration",
            "a body registration shipped with a dataset (SIZER SMPL / SMPL+D).",
        ),
        ReferenceKind(
            "synthetic_latent",
            "the ground-truth betas/body used to generate a synthetic sample.",
        ),
        ReferenceKind(
            "manual_reference",
            "a trained measurer with a tape. The only tier that licenses accuracy.",
            available=False,  # needs the scanner and real subjects
        ),
    )
}


# --------------------------------------------------- allowed combinations --
#: (pathway, reference_kind) -> claim_category. Anything absent is refused.
CLAIM_BY_COMBINATION: dict[tuple[str, str], str] = {
    # --- pre-existing, unclothed work -------------------------------------
    ("estimated", "analytic_expected"): "analytic_correctness",
    ("fitted_vertices", "analytic_expected"): "analytic_correctness",
    ("estimated", "synthetic_reference"): "synthetic_agreement",
    ("fitted_vertices", "synthetic_reference"): "synthetic_agreement",
    ("estimated", "dataset_reference"): "dataset_agreement",
    ("fitted_vertices", "dataset_reference"): "dataset_agreement",
    # --- clothed scan measured directly: characterises the GARMENT --------
    ("measured_clothed", "minimal_scan_surface"): "clothing_offset",
    ("measured_clothed", "provided_body_registration"): "clothing_offset",
    # --- inferred body: characterises the INFERENCE -----------------------
    ("inferred_smpl_under_clothing", "minimal_scan_surface"): "reference_surface_agreement",
    ("inferred_smpl_under_clothing", "provided_body_registration"): "fit_reference_agreement",
    ("inferred_smpl_under_clothing", "synthetic_latent"): "synthetic_recovery",
    ("inferred_smpld_under_clothing", "minimal_scan_surface"): "reference_surface_agreement",
    ("inferred_smpld_under_clothing", "provided_body_registration"): "fit_reference_agreement",
    ("inferred_smpld_under_clothing", "synthetic_latent"): "synthetic_recovery",
    # --- accuracy: every pathway, but only against a manual reference -----
    **{(p, "manual_reference"): "measurement_accuracy" for p in PATHWAYS},
}

#: Categories that describe how well an INFERRED body was recovered. These
#: may never be presented as measurement accuracy.
INFERENCE_CATEGORIES = frozenset(
    {"reference_surface_agreement", "fit_reference_agreement", "synthetic_recovery"}
)


def claim_category_for(pathway: str, reference_kind: str) -> str:
    """The one claim this (pathway, reference) pair licenses."""
    if pathway not in PATHWAYS:
        raise ClaimError(f"unknown pathway {pathway!r}; known: {sorted(PATHWAYS)}")
    if reference_kind not in REFERENCE_KINDS:
        raise ClaimError(
            f"unknown reference_kind {reference_kind!r}; known: {sorted(REFERENCE_KINDS)}"
        )
    if not REFERENCE_KINDS[reference_kind].available:
        raise ClaimError(
            f"reference_kind {reference_kind!r} is not obtainable yet — "
            "the claim it licenses stays empty by design"
        )
    try:
        return CLAIM_BY_COMBINATION[(pathway, reference_kind)]
    except KeyError:
        raise ClaimError(
            f"no claim is defined for pathway {pathway!r} against "
            f"{reference_kind!r}; add it deliberately rather than assuming one"
        ) from None


@dataclass(frozen=True)
class Comparison:
    """The mandatory provenance of every reported agreement number.

    Carrying reference_kind next to the category is what stops
    'agreement with a registration' from later being read as
    'accuracy against a tape'."""

    pathway: str
    reference_kind: str
    #: how the reference value itself was produced
    reference_method: str
    #: model/pipeline identifier when the reference is a fitted body
    reference_model_id: str | None = None

    @property
    def claim_category(self) -> str:
        return claim_category_for(self.pathway, self.reference_kind)

    def to_dict(self) -> dict:
        return {
            "claim_category": self.claim_category,
            "pathway": self.pathway,
            "reference_kind": self.reference_kind,
            "reference_method": self.reference_method,
            "reference_model_id": self.reference_model_id,
        }


def validate_claim(comparison: Comparison, claimed_category: str) -> None:
    """Raise unless `claimed_category` is the one the pair licenses."""
    licensed = comparison.claim_category
    if claimed_category != licensed:
        raise ClaimError(
            f"{comparison.pathway!r} against {comparison.reference_kind!r} "
            f"licenses {licensed!r}, not {claimed_category!r}"
        )
