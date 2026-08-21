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
