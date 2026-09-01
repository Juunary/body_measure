"""Can a pattern be drafted from this body, and if not, what is missing?

A size label tolerates a wrong measurement: EN 13402's bands are 80 mm
wide, so a chest can be tens of millimetres out and still land on the same
letter. A pattern draws a line at the number. Moving from size labels to
made-to-measure therefore does not need a new algorithm first — it needs
measurements the pipeline can vouch for, and a list of which ones a draft
actually consumes.

This gate answers the second question and is honest about the first. Its
best possible verdict is `complete_unverified`: every dimension present
and internally clean. `ready` is unreachable here for the same reason
`measurement_accuracy` is unreachable in claims.py — no value has ever
been compared against a trained measurer's tape, so no value can be
called accurate to a pattern's tolerance. The gate says so rather than
implying a readiness it cannot support.

The requirement list is itself a claim. Twelve entries come from
polo-line-sim's measurement list, which records that the Maß-DPP plan
plan lists no body measurements at all and that its own list is derived
from garment pattern practice and ISO 8559-1. Three more were identified
while reading that list against what a draft needs, and are marked
`unsourced` because they have not been checked against a named drafting
system (M. Müller & Sohn, or Aldrich's menswear block). A gate that hid
the provenance of its own requirements would be the thing it exists to
prevent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Quality buckets a drafted line may rest on. `arm_clipped` is in because
#: it is a documented systematic approximation with a known direction;
#: manual_review and rejected are not, and neither is a null.
DRAFTABLE_BUCKETS = ("clean", "arm_clipped")

#: Verdicts, worst first. `ready` is deliberately absent — see the module
#: docstring. Adding it needs an accuracy claim, not more code here.
NOT_READY = "not_ready"
COMPLETE_UNVERIFIED = "complete_unverified"


@dataclass(frozen=True)
class Requirement:
    key: str
    drafts: str
    #: "spec" (validated pipeline) | "prototype" (computed, unvalidated)
    #: | "unimplemented" (no code produces it)
    provision: str
    #: where the requirement itself comes from
    source: str


#: What a polo draft consumes. Order follows the garment: body, then arm.
POLO_REQUIREMENTS = (
    Requirement("chest_circumference", "body width — the critical one",
                "spec", "polo-line-sim measurement list"),
    Requirement("waist_circumference", "side seam silhouette",
                "spec", "polo-line-sim measurement list"),
    Requirement("neck_circumference", "rib collar length, neckline",
                "spec", "polo-line-sim measurement list"),
    Requirement("across_back_shoulder_width", "yoke and shoulder seam",
                "spec", "polo-line-sim measurement list"),
    Requirement("back_length", "body length, drop tail",
                "spec", "polo-line-sim measurement list"),
    Requirement("upper_arm_girth", "sleeve width",
                "spec", "polo-line-sim measurement list"),
    # `sleeve_length` is deliberately NOT here. The spec defines it as
    # back neck point to WRIST and marks it `priority: deferred`; a short
    # sleeve stops part-way down the upper arm, and where it stops is a
    # design choice (garment_prototypes.SLEEVE_END_FRACTION), not a body
    # dimension. Listing it made the gate demand a long-sleeve measurement
    # to draft a short sleeve — see decision #35.
    Requirement("hem_girth", "hem width",
                "prototype", "polo-line-sim measurement list"),
    Requirement("sleeve_opening_girth", "rib cuff length",
                "prototype", "polo-line-sim measurement list"),
    Requirement("armhole_depth", "armhole curve, sleeve cap",
                "prototype", "polo-line-sim measurement list"),
    Requirement("shoulder_slope", "shoulder seam angle",
                "prototype", "polo-line-sim measurement list"),
    Requirement("front_back_width", "front / back balance",
                "prototype", "polo-line-sim measurement list"),
    Requirement("centre_front_length", "front length; the drop tail is the "
                                       "difference from back length",
                "unimplemented", "unsourced — identified from the list, not "
                                 "checked against a drafting system"),
    Requirement("armhole_girth", "sleeve cap length; armhole_depth gives the "
                                 "depth, not the girth",
                "unimplemented", "unsourced — identified from the list, not "
                                 "checked against a drafting system"),
    Requirement("across_front", "front width; front_back_width gives the "
                                "difference, not the width",
                "unimplemented", "unsourced — identified from the list, not "
                                 "checked against a drafting system"),
)


@dataclass
class RequirementStatus:
    requirement: Requirement
    value: float | None
    unit: str
    bucket: str
    draftable: bool
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.requirement.key,
            "drafts": self.requirement.drafts,
            "provision": self.requirement.provision,
            "requirement_source": self.requirement.source,
            "value": self.value,
            "unit": self.unit,
            "bucket": self.bucket,
            "draftable": self.draftable,
            "note": self.note,
        }


@dataclass
class Readiness:
    garment: str
    verdict: str
    statuses: list[RequirementStatus] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def draftable(self) -> list[RequirementStatus]:
        return [s for s in self.statuses if s.draftable]

    @property
    def blocking(self) -> list[RequirementStatus]:
        return [s for s in self.statuses if not s.draftable]

    def to_dict(self) -> dict:
        return {
            "garment": self.garment,
            "verdict": self.verdict,
            "n_required": len(self.statuses),
            "n_draftable": len(self.draftable),
            "n_blocking": len(self.blocking),
            "requirements": [s.to_dict() for s in self.statuses],
            "notes": self.notes,
        }


def assess(measurements, prototypes=None, *, garment: str = "polo",
           requirements=POLO_REQUIREMENTS) -> Readiness:
    """Check a measured body against what a draft consumes.

    `measurements` is what run_estimated_measurements returned;
    `prototypes` is what garment_prototypes.run_prototypes returned, or
    None if they were not computed.
    """
    from .validate.stats import quality_bucket

    prototypes = prototypes or {}
    statuses: list[RequirementStatus] = []

    for requirement in requirements:
        if requirement.provision == "spec":
            value = measurements.get(requirement.key)
            if value is None or value.selected_value_mm is None:
                statuses.append(RequirementStatus(
                    requirement, None, "mm", "rejected", False,
                    "no value on this scan"))
                continue
            bucket = quality_bucket(value)
            statuses.append(RequirementStatus(
                requirement, float(value.selected_value_mm), "mm", bucket,
                bucket in DRAFTABLE_BUCKETS,
                "" if bucket in DRAFTABLE_BUCKETS
                else f"{bucket} — a drafted line may not rest on it"))

        elif requirement.provision == "prototype":
            value = prototypes.get(requirement.key)
            if value is None or value.value is None:
                statuses.append(RequirementStatus(
                    requirement, None, "mm", "rejected", False,
                    "no value on this scan" if value is not None
                    else "prototypes were not computed"))
                continue
            # A prototype has no definition audit and no reference, so it
            # can be present without being draftable. Presence is what this
            # gate reports; it does not upgrade an unvalidated number.
            statuses.append(RequirementStatus(
                requirement, float(value.value), value.unit, "prototype", False,
                "prototype: no ISO definition audit, no reference comparison"))

        else:
            statuses.append(RequirementStatus(
                requirement, None, "mm", "unimplemented", False,
                "nothing computes this yet"))

    verdict = COMPLETE_UNVERIFIED if not [s for s in statuses if not s.draftable] \
        else NOT_READY
    notes = [
        "`ready` is not among the verdicts. No value here has been compared "
        "against a trained measurer's tape, so none can be called accurate to "
        "a pattern's tolerance — measurement_accuracy is unreachable in code "
        "until the scanner and ISO 20685-1 validation exist (decision #1).",
        "A size band is 80 mm wide and a drafted line is a line, so the "
        "accuracy a pattern needs is roughly four times tighter than the one "
        "a size label needs. That gap, not the drafting maths, is what stands "
        "between this pipeline and made-to-measure.",
        "A short sleeve's length is not on this list because it is not a body "
        "dimension: the sleeve stops part-way down the upper arm and where it "
        "stops is chosen, not measured. The arm is drafted from upper_arm_girth "
        "and sleeve_opening_girth instead. The spec's `sleeve_length` runs to "
        "the wrist and is `priority: deferred` for this garment.",
    ]
    unsourced = [s for s in statuses if "unsourced" in s.requirement.source]
    if unsourced:
        notes.append(
            f"{len(unsourced)} of the {len(statuses)} requirements are unsourced: "
            "identified while reading the measurement list against what a draft "
            "needs, not checked against a named drafting system. The list is a "
            "claim like any other.")
    return Readiness(garment, verdict, statuses, notes)
