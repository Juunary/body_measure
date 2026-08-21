# Scope — LICENSE-G0 items 4, 5 and 7

Project: **Maß-DPP**, Institut für Textiltechnik (ITA), RWTH Aachen University
Supervisor: Waldemar Lang
Last updated: 2026-08-21

---

## Item 4 — Research purpose and named user scope

### Purpose
Estimate body measurements from 3D body scans in order to (a) drive
made-to-measure shirt production and (b) populate a Digital Product
Passport under the EU Ecodesign Regulation (ESPR).

The licensed material is used for two things only:

1. **Validation before the scanner arrives.** Public 3D body datasets stand
   in for scanner output so the measurement pipeline can be built and
   checked against references ahead of hardware procurement.
2. **Body-under-clothing research.** Recovering an unclothed body surface
   from a scan of a dressed subject, so that a customer need not undress
   to be measured.

No licensed material is used to produce, market, or demonstrate a product
or service. See item 7.

### Named users

The SMPL and CAPE grants are **personal, single-user and
non-transferable** (verbatim wording, captured 2026-08-21). A licence is
held by a person, not by ITA, and it cannot be lent.

| Name | Role | Basis |
|---|---|---|
| June woo Kang | Intern, ITA | Registered licensee; sole operator of this installation |
| Waldemar Lang | Supervisor, ITA | Oversight only. **Not covered by this licence** — using the data himself requires his own registration |

Access is not delegated and cannot be. Any additional person registers in
their own name and is added here first.

### Licensed material in scope
| Source | Licence basis | Status |
|---|---|---|
| SMPL | Research licence | Granted 2026-08-21, weights sharing included (see `weights-permission.md`) |
| CAPE | Research licence | Granted 2026-08-21; registration approved, download imminent |
| SIZER | Research licence | Registration approved 2026-08-21, download imminent |
| HSRD-100 | CC BY 4.0 | In use; still the only source cleared for public material |
| Texel BodyScan | CC BY-NC 4.0 | In use; permission confirmed 2026-08-21 (non-commercial terms unchanged) |
| NOMO-3D-400 | Archive terms, redistribution forbidden | In use; permission confirmed 2026-08-21, copy never moved |

Permission scope note (2026-08-21): the grant covers research use and
**weights sharing**. It does **not** extend public-material use — figures
leaving the project remain HSRD-only per `public-material.md`.

---

## Item 5 — Storage location and access control

- **Location:** local workstation only —
  `C:\Users\harry\Documents\ITA\body-measure\data\external\`
  and `models\` for SMPL.
- **Version control:** excluded. `.gitignore` blocks `data/external/`,
  `models/`, `checkpoints/`, and every weight extension. Licence texts in
  this directory are likewise excluded; only policy files and the
  checklist README are tracked.
- **No cloud sync, no shared drive, no backup service** holds a copy.
- **Redistribution:** none. NOMO explicitly forbids it; no dataset copy
  leaves this machine.

### Open issue — external GPU training

The project plan trains on an **external GPU** with inference run locally.
Moving CAPE- or SIZER-derived data (including synthetically generated data
that carries their displacements) to a third-party compute provider is a
**transfer to a third party**, not an internal move, and this file does not
yet authorise one.

Before any such transfer:
- name the provider and jurisdiction here,
- confirm the licence permits processing on third-party infrastructure,
- prefer transferring *derived* training tensors over raw dataset files,
- and delete the remote copy at the end of the run.

Until that entry exists, training data stays on the local machine.

---

## Item 7 — Commercial path, disclosed rather than denied

**This item was reworded on 2026-08-21.** It previously read "confirmed no
path connects this work to a commercial product/service". That wording
cannot be ticked honestly by a project with industry partners, and a
checklist that cannot be completed protects nobody.

What matters to a licensor is not that a commercial interest is absent —
it is that the commercial interest was **disclosed** before the research
licence was granted. A permission obtained by omission fails at exactly
the moment it is needed.

### Current state, as disclosed

- Maß-DPP is a **publicly funded research project carried out with
  industry partners**.
- **No commercial product or service currently derives from this work.**
  No licensed material appears in anything sold, marketed, or offered.
- A future commercial path is **not excluded**, and is therefore declared
  to the licensors in the request filed under item 6.

### Standing rule

Until the item 6 reply is on file, trained weights are treated as
derivatives of CAPE/SIZER: not published, not shared outside the named
users above, not used commercially. Should the project move toward
commercial deployment, work stops until a commercial licence is in place —
it does not continue while permission is sought.
