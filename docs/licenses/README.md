# LICENSE-G0 — the gate that comes before any clothed-scan code

Gitignoring a dataset is not a licence review. SMPL's licence forbids not
only commercial use of the model but **developing methods, algorithms or
neural networks for commercial purposes** using it; CAPE is research-only
with a separate commercial-contact route; SIZER carries its own terms.
A network trained on CAPE/SIZER-derived data is plausibly a derivative of
them, and that question has to be answered by the licensors, not by us.

**Nothing in the clothed-scan work stream (C0a onwards) starts until every
box below is ticked and the evidence is filed in this directory.**

## Checklist

| # | Item | Status | Evidence file |
|---|---|---|---|
| 1 | SIZER access terms captured verbatim | ☐ | `sizer-terms.txt` |
| 2 | CAPE data **and code** terms captured verbatim | ☐ | `cape-terms.txt` |
| 3 | SMPL model licence captured verbatim | ☐ | `smpl-model-licence.txt` |
| 4 | Research purpose and named user scope documented | ☐ | `scope.md` |
| 5 | Storage location and access control stated | ☐ | `scope.md` |
| 6 | **Written** confirmation of what trained weights may be used and shared for | ☐ | `weights-permission.md` |
| 7 | Confirmed no path connects this work to a commercial product/service | ☐ | `scope.md` |
| 8 | List of data usable in public material (currently: HSRD-100 only) | ☐ | `public-material.md` |
| 9 | Ethics/consent scope checked — CAPE asks users to confirm their own IRB position | ☐ | `ethics.md` |

## Standing rules until item 6 is answered

- Trained weights are treated as **derivatives** of CAPE/SIZER: not
  published, not shared outside the named scope, not used commercially.
- Public material (weekly decks, portfolio, anything leaving the project)
  uses **HSRD-100 (CC BY 4.0) only**. This already holds for the unclothed
  work — see `docs/decisions.md`.
- `data/external/sizer`, `data/external/cape`, `models/` and any checkpoint
  directory stay gitignored. Download procedures are documented in
  `docs/datasets.md`; the data itself is never committed.

## Why this is a gate and not a note

The rest of this project enforces its rules in code — units are refused
rather than guessed, a rejected slice returns null rather than a
substitute, a claim category is derived from its reference rather than
typed by hand. Licensing is the one constraint that cannot be enforced in
code, so it is enforced by sequence instead: it comes first.
