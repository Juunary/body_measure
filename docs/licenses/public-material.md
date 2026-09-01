# Public material — LICENSE-G0 item 8

What may leave the project, and in what form.
Last updated: 2026-08-21

"Public material" means anything seen outside the named users in
`scope.md`: weekly status decks, the project review, publications, a
portfolio, a conference slide, a screenshot in a chat with a partner.

---

## Cleared for public use

| Source | Licence | Conditions |
|---|---|---|
| **HSRD-100** | CC BY 4.0 | **Attribution required** on every figure. This is the only source cleared for renderings, meshes and screenshots in public material. |

Nothing else is cleared. This already holds for the unclothed work stream
and is recorded in `docs/decisions.md`.

## Not cleared — figures and geometry

No mesh, rendering, screenshot, cross-section, or derived image from
**SMPL, CAPE, SIZER, Texel or NOMO** appears in public material. This
holds even where the licence permits research use: research use is not
publication, and a rendering of a scan is a redistribution of it.

## Narrower than public — AI-Hub is not viewable by ITA at all

**AI-Hub datasets sit outside this document's usual axis.** The approval
obtained on 2026-09-01 covers **one named individual's personal use for
this project**. Third-party viewing was explicitly **not** granted, and
the AI-Hub policy forbids it: "승인을 받지 않은 다른 법인, 단체 또는 개인에게
열람하게 하거나 제공, 양도, 대여, 판매하여서는 안됩니다."

Every other restricted source here can at least be shown to the named
users in `scope.md`. This one cannot. Waldemar cannot look at it. A
reviewer cannot look at it. A colleague cannot re-run a script on it.

**Therefore no result derived from AI-Hub may serve as project evidence.**
Not in `reports/validation-results.json`, not in a report, not in a
decision's evidence table, not in an internal review — because evidence
that no second person may audit is not evidence, whatever its licence
says. This is a stricter rule than the aggregate-numbers case below, and
it comes from the reviewability the project rests on rather than from the
licence text.

What it may do is **steer**. A private check against AI-Hub can tell the
one permitted user *where to look* — say, that a girth reads
systematically high against a real tape. That direction is then pursued,
and demonstrated, on data a second person can open. The dataset points;
it never testifies.

Practically: AI-Hub-derived numbers stay out of `reports/`, and any
finding it prompts is written up citing the data that confirmed it, not
the data that suggested it.

## The subtle case — aggregate numbers

Statistics computed from a restricted dataset are not the dataset. A line
such as "mean deviation 4.2 mm over 10 subjects" carries no recoverable
geometry and is normal scientific reporting.

- **Internal reports and project reviews:** aggregate statistics from
  Texel and NOMO may be quoted, with the dataset named and its licence
  stated. The existing KW32–KW34 decks do this.
- **Anything commercial in nature** — a portfolio used for job
  applications, a company presentation: Texel is **CC BY-NC**. Treat a
  commercial-context reuse as not cleared, and substitute HSRD or
  synthetic results.
- **Per-subject values are not aggregate.** A table with one row per
  scanned individual is closer to the data than to a statistic; keep it
  internal.

## Trained weights

Not public material at all. Treated as derivatives of CAPE/SIZER: not
published, not uploaded to a model hub, not attached to a paper, until
`weights-permission.md` says otherwise.

## Before publishing anything, check

1. Is every figure from HSRD-100, with attribution present?
2. Are restricted-source numbers aggregate, with the source named?
3. Is the audience commercial in nature? If so, no NC material.
4. Are any weights, checkpoints or ONNX files attached? They must not be.
