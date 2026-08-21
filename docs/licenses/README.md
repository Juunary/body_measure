# LICENSE-G0 — the gate that comes before any clothed-scan code

Gitignoring a dataset is not a licence review. SMPL and CAPE grant a
**personal, single-user, non-transferable** right to non-commercial
research use. They permit training methods, algorithms and neural
networks — but prohibit doing so "for commercial use of any kind", and
prohibit making the result available to any third party without prior
written permission. SIZER carries its own terms from a different
institute. Those questions are answered by the licensors, not by us.

**Nothing in the clothed-scan work stream (C0a onwards) starts until every
box below is ticked and the evidence is filed in this directory.**

## Checklist

| # | Item | Status | Evidence file |
|---|---|---|---|
| 1 | SIZER access terms captured verbatim | ☐ | `sizer-terms.txt` |
| 2 | CAPE data **and code** terms captured verbatim | ☑ | `cape-terms.txt` |
| 3 | SMPL model licence captured verbatim | ☑ | `smpl-model-licence.txt` |
| 4 | Research purpose and named user scope documented | ☑ | `scope.md` |
| 5 | Storage location and access control stated | ☑ | `scope.md` |
| 6 | **Written** confirmation of what trained weights may be used and shared for | ◐ | `weights-permission.md` |
| 7 | Commercial path documented and disclosed to the licensors | ☑ | `scope.md` |
| 8 | List of data usable in public material (currently: HSRD-100 only) | ☑ | `public-material.md` |
| 9 | Ethics/consent scope checked — CAPE asks users to confirm their own IRB position | ☐ | `ethics.md` |

Captured 2026-08-21. Items 2 and 3 are the live licence pages as fetched
on that date, not a capture from the registration flow; if registration
presents different terms, replace them.

### Item 7 was reworded on 2026-08-21

It previously read "confirmed no path connects this work to a commercial
product/service". A project with industry partners cannot tick that
honestly, and a checklist that cannot be completed protects nobody. What
protects the project is **disclosure**: a permission obtained by omission
fails at the moment it is needed. See `scope.md`.

## What is open

- **Item 1 and SIZER as a whole.** SIZER is MPI-INF; SMPL and CAPE are
  MPI-IS. The 2026-08-21 research permission does not extend to it.
  **C0a remains blocked.**
- **Item 6.** The licence text settles more than expected: training for
  non-commercial research is inside the grant. What is *not* settled is
  whether Maß-DPP's industry-partner structure counts as "commercial use
  of any kind", whether CAPE grants a derivative-works right at all (it is
  silent where SMPL is explicit), and permission for weights to reach
  anyone outside this installation. Requests go to
  `ps-license@tue.mpg.de` (CAPE) and `smpl@max-planck-innovation.de`
  (SMPL), with Waldemar Lang as sender or in copy.
- **Item 9.** Requires ITA's own position on secondary use of human scan
  data, and a separate procedure for the future scanner subjects.

Items 6 and 9 bind at C4 and at the scanner respectively. They do not
block C1–C3 on already-permitted data.

## Standing rules — now licence-backed, not precautionary

- Trained weights are **not** copied, shared, distributed, transferred or
  sub-licensed outside this installation; not uploaded to a model hub; not
  attached to a paper or public demo. This is the No Distribution clause,
  not extra caution.
- The grant is **single-user**. Each person registers in their own name.
- Public material (weekly decks, portfolio, anything leaving the project)
  uses **HSRD-100 (CC BY 4.0) only** — see `public-material.md` for the
  aggregate-statistics carve-out.
- `data/external/sizer`, `data/external/cape`, `models/` and any checkpoint
  directory stay gitignored. Download procedures live in
  `docs/datasets.md`; the data itself is never committed.
- Licence texts and licensor correspondence stay in this directory,
  untracked. Our own policy files (`scope.md`, `public-material.md`,
  `ethics.md`) are tracked, because the policy should be versioned.

## Why this is a gate and not a note

The rest of this project enforces its rules in code — units are refused
rather than guessed, a rejected slice returns null rather than a
substitute, a claim category is derived from its reference rather than
typed by hand. Licensing is the one constraint that cannot be enforced in
code, so it is enforced by sequence instead: it comes first.
