"""Is the BODY measured well enough to start a draft from?

Not "can a pattern be drafted" — that was this gate's first framing and it
overstated what a body can settle. A draft is cut to finished-garment
measurements, the points ISO 18890 defines and a factory checks: half
chest across the flat garment, centre-back length, sleeve length from the
shoulder point. Those are not body dimensions. They are body dimensions
plus ease, and ease is a design decision no standard fixes — it depends on
fit, fabric, stretch, shrinkage and intended use
(`docs/reference-garment-sizing-and-pom.md`).

    ISO 8559-1 body dimension
        -> size band                       (EN ISO 8559-2, EN 13402-3)
        -> ease                            DESIGN — no standard fixes it
        -> finished-garment POM            (ISO 18890 + factory agreement)
        -> pattern, seam allowance, shrinkage
        -> sample, tolerance inspection

**This gate covers the first link only.** Everything in it is measured on
a body; not one entry is a finished-garment point, and none can be — there
is no garment to measure. So its verdict is about the input to a draft,
never about the draft.

The distinction is easy to lose because the requirements used to be
described by the garment part they feed. `hem_girth` "drafts hem width"
reads as though the hem's width had been measured; what was measured is
the hip the hem falls over, and the hem's width is that plus ease. It has
been renamed `hip_girth`, and every entry now says what the body
measurement is, not what the pattern piece is called (decision #42).

`Requirement.location` records the other half of it: for most entries the
place to measure is fixed by anatomy or by the standard, but
`sleeve_opening_girth` is taken wherever the sleeve happens to end, so it
moves when `garment_prototypes.SLEEVE_END_FRACTION` moves. A requirement
like that is not a property of the body alone and cannot be "complete"
independently of the design.

Its best possible verdict is `complete_unverified`: every dimension
present and internally clean. `ready` is unreachable here for the same
reason `measurement_accuracy` is unreachable in claims.py — no value has
ever been compared against a trained measurer's tape, so no value can be
called accurate to a pattern's tolerance.

The requirement list is itself a claim. Most entries come from
polo-line-sim's measurement list, which records that the Maß-DPP plan
lists no body measurements at all and that its own list is derived from
garment pattern practice and ISO 8559-1. Three more were identified while
reading that list against what a draft needs, and were marked `unsourced`
on the reasoning that only the manufacturers' POM sheets named them — and
a finished-garment point cannot source a body requirement without the
ease term that separates them.

That reasoning was wrong, and reading the standard's own table of
contents settled it (decision #52): ISO 8559-1:2017 defines all three as
BODY measurements — 5.4.7 across front width, 5.4.8 front neck point to
waist, 5.3.15 armscye girth. No drafting textbook was needed. Every
entry here now carries the clause that names it, and only
`sleeve_opening_girth` has none, because where a short sleeve ends is a
design choice and the standard does not measure garments.

A clause number is not a definition. It says the standard has an item by
that name, read off its contents; what the item MEANS is clause 5's text,
which is behind the paywall the `definition_verified` task is about. So
this changes provenance, not validation: the prototypes stay prototypes
until each is audited, and two entries name two candidate clauses each
because the titles alone cannot separate them.
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
#: The complete set, stated rather than inferred. A test asserts `ready` is
#: not in it; scanning the module's uppercase names for that was fragile —
#: it broke the moment an unrelated constant was added.
VERDICTS = (NOT_READY, COMPLETE_UNVERIFIED)


#: Where the place to measure comes from.
BY_ANATOMY = "anatomy"          # a landmark or the standard fixes it
BY_DESIGN = "design_parameter"  # a garment decision fixes it, and moves it


@dataclass(frozen=True)
class Requirement:
    key: str
    #: the BODY measurement, not the pattern piece it feeds. See the module
    #: docstring: a finished-garment point is this plus ease.
    measures: str
    #: what a draft uses it for — kept separate from `measures` so the two
    #: can never be confused again
    feeds: str
    #: "spec" (validated pipeline) | "prototype" (computed, unvalidated)
    #: | "unimplemented" (no code produces it)
    provision: str
    #: BY_ANATOMY | BY_DESIGN — a design-located requirement moves when the
    #: design does, so it is not a property of the body alone
    location: str
    #: where the requirement itself comes from
    source: str
    #: the ISO 8559-1:2017 clause that names this measurement, when one
    #: does. Read off the standard's table of contents (decision #52), so
    #: it identifies the item, not its definition text — `measurement-
    #: audit.md` still rates every mapping, and `definition_verified` in
    #: the spec is still false for all of them.
    iso_clause: str | None = None


#: The body measurements a polo draft starts from. Every one is measured
#: on a body; none is a finished-garment point. Order follows the garment:
#: torso, then arm.
LIST = "polo-line-sim measurement list"
#: The standard names them. Until 2026-09-07 these three were `unsourced`,
#: on the reasoning that only the manufacturers' POM sheets named them and
#: a finished-garment point cannot source a body requirement. That was
#: wrong: ISO 8559-1:2017 defines all three as body measurements, in
#: clause 5. The clause number is the source (decision #52).
ISO = "ISO 8559-1:2017"

POLO_REQUIREMENTS = (
    Requirement("chest_circumference", "chest girth", "body width — the "
                "critical one", "spec", BY_ANATOMY, LIST,
                "5.3.4 or 5.3.6 — unresolved, see measurement-audit.md"),
    Requirement("waist_circumference", "waist girth", "side seam silhouette",
                "spec", BY_ANATOMY, LIST, "5.3.10 Waist girth"),
    Requirement("neck_circumference", "neck base girth",
                "rib collar length, neckline", "spec", BY_ANATOMY, LIST,
                "5.3.3 Neck base girth"),
    Requirement("across_back_shoulder_width", "acromion to acromion across "
                "the back", "yoke and shoulder seam", "spec", BY_ANATOMY, LIST,
                "5.4.3 Across back shoulder width (through the back neck point)"),
    Requirement("back_length", "back neck point to waist", "body length, "
                "drop tail", "spec", BY_ANATOMY, LIST,
                "5.4.5 or 5.4.13 — unresolved, see measurement-audit.md"),
    Requirement("upper_arm_girth", "upper arm girth", "sleeve width",
                "spec", BY_ANATOMY, LIST, "5.3.16 Upper-arm girth"),
    # `sleeve_length` is deliberately NOT here. The spec defines it as
    # back neck point to WRIST and marks it `priority: deferred`; a short
    # sleeve stops part-way down the upper arm, and where it stops is a
    # design choice (garment_prototypes.SLEEVE_END_FRACTION), not a body
    # dimension. Listing it made the gate demand a long-sleeve measurement
    # to draft a short sleeve — see decision #35.
    Requirement("hip_girth", "widest torso girth below the waist",
                "hem width, once ease is added", "prototype", BY_ANATOMY, LIST,
                "5.3.14 Maximum hip girth (seat measure girth)"),
    Requirement("sleeve_opening_girth", "arm girth where the sleeve ends",
                "rib cuff length, once ease is added", "prototype",
                BY_DESIGN, LIST, None),  # no clause: the level is a design choice
    Requirement("armhole_depth", "shoulder to armpit vertical drop",
                "armhole curve, sleeve cap", "prototype", BY_ANATOMY, LIST,
                "5.4.6 Scye depth length"),
    Requirement("shoulder_slope", "degrees below horizontal, neck to "
                "shoulder tip", "shoulder seam angle", "prototype",
                BY_ANATOMY, LIST, "5.6.2 Shoulder slope"),
    Requirement("front_back_width", "how the chest girth divides front to "
                "back", "front / back balance", "prototype", BY_ANATOMY, LIST,
                "5.2.4 Armscye front to back width — likely, unconfirmed"),
    Requirement("centre_front_length", "neck to waist down the front",
                "front length; the drop tail is the difference from back "
                "length", "unimplemented", BY_ANATOMY, ISO,
                "5.4.8 Front neck point to waist"),
    Requirement("armhole_girth", "the armscye loop on the body",
                "sleeve cap length; armhole_depth gives the depth, not the "
                "girth", "unimplemented", BY_ANATOMY, ISO,
                "5.3.15 Armscye girth"),
    Requirement("across_front", "shoulder to shoulder across the front",
                "front width; front_back_width gives the difference, not the "
                "width", "unimplemented", BY_ANATOMY, ISO,
                "5.4.7 Across front width"),
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
            # what was measured on the body, and separately what a draft
            # uses it for — a reader who sees only the second takes the
            # body measurement for the pattern piece (decision #42)
            "measures_on_the_body": self.requirement.measures,
            "feeds": self.requirement.feeds,
            "measured_at": self.requirement.location,
            "provision": self.requirement.provision,
            "requirement_source": self.requirement.source,
            "iso_clause": self.requirement.iso_clause,
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
        "Every requirement here is measured ON A BODY. None is a "
        "finished-garment measurement, and none can be: a draft is cut to "
        "the points ISO 18890 defines, which are these dimensions plus ease "
        "— and ease is a design decision no standard fixes. So this gate "
        "verifies the INPUT to a draft, never the draft (decision #42).",
        "`ready` is not among the verdicts. No value here has been compared "
        "against a trained measurer's tape, so none can be called accurate to "
        "a pattern's tolerance — measurement_accuracy is unreachable in code "
        "until the scanner and ISO 20685-1 validation exist (decision #1).",
        "A size band is 80 mm wide and a drafted line is a line, so the "
        "accuracy a pattern needs is roughly four times tighter than the one "
        "a size label needs. Factories hold a finished chest and body length "
        "to about ±10 mm and smaller points to ±5 mm; that is the order the "
        "body input has to reach before ease is even added.",
        "A short sleeve's length is not on this list because it is not a body "
        "dimension: the sleeve stops part-way down the upper arm and where it "
        "stops is chosen, not measured. The arm is drafted from upper_arm_girth "
        "and sleeve_opening_girth instead. The spec's `sleeve_length` runs to "
        "the wrist and is `priority: deferred` for this garment.",
    ]
    design_located = [s for s in statuses if s.requirement.location == BY_DESIGN]
    if design_located:
        notes.append(
            f"{len(design_located)} requirement(s) are measured where a design "
            "parameter puts them, not where anatomy does: "
            + ", ".join(s.requirement.key for s in design_located)
            + ". They move when the garment does, so they cannot be complete "
            "independently of it.")
    unsourced = [s for s in statuses if "unsourced" in s.requirement.source]
    if unsourced:
        notes.append(
            f"{len(unsourced)} of the {len(statuses)} requirements are unsourced: "
            + ", ".join(s.requirement.key for s in unsourced)
            + ". The list is a claim like any other.")
    unnamed = [s for s in statuses if s.requirement.iso_clause is None]
    if unnamed:
        notes.append(
            f"{len(unnamed)} requirement(s) have no clause in ISO 8559-1: "
            + ", ".join(s.requirement.key for s in unnamed)
            + ". The standard measures bodies, and where a short sleeve ends "
            "is not a property of one.")
    unresolved = [s for s in statuses
                  if s.requirement.iso_clause and "unresolved" in s.requirement.iso_clause]
    if unresolved:
        notes.append(
            f"{len(unresolved)} requirement(s) match more than one clause and the "
            "standard's text has not been read to choose: "
            + ", ".join(s.requirement.key for s in unresolved)
            + ". A clause number identifies the item, not its definition.")
    return Readiness(garment, verdict, statuses, notes)
