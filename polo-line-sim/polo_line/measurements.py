# -*- coding: utf-8 -*-
"""1. The 3D body measurements needed to draft a polo shirt pattern.

On Seite 38 the production line starts from the end customer's individual
requirements, and the pattern is generated from those requirements. What is
needed upstream of that is this list of measurements.

The plan, however, only writes the requirements as "e.g., size, color, cut,
fabric selection" and never breaks size down into individual measurements. A
full-text search of the German original turns up no Körpermaß or Brustumfang
style entries either (checked 2026-08-26).

The list below is therefore not a quotation from the plan but a derivation from
garment pattern practice and ISO 8559-1, cross-checked against
body-measure/measurement-spec.v1.yaml (spec_version 4) to separate what is
already defined from what is newly needed.
"""
from __future__ import annotations

from . import term
from .spec import MEASUREMENTS, Measurement

POLO_CONSTRAINTS = (
    "Pique knit stretches, so a polo is drafted with less ease than a woven shirt.",
    "Rib collar and cuff stretch replaces the cuff and collar-band measurements of a dress shirt.",
    "The back runs longer than the front, so back length and centre-front length are kept apart.",
)


def covered(m: Measurement) -> bool:
    """Is this dimension already defined in the body-measure spec?"""
    return m.spec_status != "—"


def report(verbose: bool = False) -> None:
    term.section("1", "Body measurements to take from the 3D scan")
    print()
    term.note("Plan, Seite 38: the line starts from the customer's own specification "
              "(size, colour, cut, fabric), and the pattern is drawn from that data.")
    term.note("The plan never breaks size down into measurements — this list comes from "
              "pattern practice and ISO 8559-1, not from the plan.")
    term.note("Checked against body-measure/measurement-spec.v1.yaml (spec_version 4, 2026-08-25)")
    print()

    rows = []
    for m in MEASUREMENTS:
        mark = term.c("●", "green") if covered(m) else term.c("○", "yellow")
        status = m.spec_status if covered(m) else term.c("not in the spec", "yellow")
        rows.append([mark, m.name, m.pattern_use, m.method, status])
    term.table(["", "Measurement", "Drives", "How it is taken", "measurement-spec v4"], rows)

    defined = sum(1 for m in MEASUREMENTS if covered(m))
    gaps = len(MEASUREMENTS) - defined
    print()
    term.kv("Measurements needed", f"{len(MEASUREMENTS)}")
    term.kv("Already defined", term.c(f"● {defined}", "green") + "  covered by the existing spec")
    term.kv("Still to define", term.c(f"○ {gaps}", "yellow") + "  new for the polo")

    print()
    print(term.c("   What the polo adds", "bold"))
    for m in MEASUREMENTS:
        if covered(m):
            continue
        print(f"     {term.c('○', 'yellow')} {m.name} " + term.c(f"({m.key})", "grey"))
        term.note(m.polo_note)

    if verbose:
        print()
        print(term.c("   Polo-specific constraints", "bold"))
        for line in POLO_CONSTRAINTS:
            term.note(line)
        for m in MEASUREMENTS:
            if m.polo_note and covered(m):
                print()
                print(f"     {m.name} " + term.c(f"({m.key})", "grey"))
                term.note(m.polo_note)
