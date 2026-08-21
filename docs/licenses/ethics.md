# Ethics and consent scope — LICENSE-G0 item 9

Last updated: 2026-08-21
Status: **OPEN — requires Waldemar Lang.** This file records what is known
and what must be confirmed; it is not itself a clearance.

---

## Why this item exists

CAPE does not certify a user's ethics position for them. It asks users to
**confirm their own institutional position** on working with human subject
scan data, and to send a signed consent form for raw scan data. The
question is therefore ITA's to answer, not the licensor's, and not an
intern's.

## What this work stream actually does

Two distinct situations, with different obligations:

### 1. Now — secondary use of existing datasets
We process scans that were collected by others, from subjects who
consented at collection time, and released under a research licence. No
new human data is collected. No attempt is made to identify a subject, and
no subject-level output leaves the project (`public-material.md`).

Body geometry of an identifiable person is nevertheless personal data.
Handling follows `scope.md`: local storage, named users, no redistribution.

### 2. Later — scanning real people at ITA
When the 3D scanner arrives, **ISO 20685-1 validation requires real
subjects measured by a trained measurer.** That is primary collection of
human subject data and is categorically different from what is happening
now. It will require its own consent procedure, retention policy and
ethics review, obtained *before* the first subject is scanned.

This is flagged early on purpose: it is the kind of requirement that is
cheap to arrange in advance and expensive to discover afterwards.

## Design decision already in force

Body measurements are **excluded from the Digital Product Passport by
design.** The passport carries garment data; it does not carry the
customer's body. This was decided during DPP data-model work and is the
main privacy boundary of the system — it means the passport cannot leak
body dimensions regardless of who reads it.

## To be confirmed by ITA

- [ ] Does ITA require ethics-committee review for **secondary use** of
      licensed human scan datasets, or is that covered by the dataset's
      own consent?
- [ ] Is a signed CAPE consent form needed for the parts we use? (Required
      for **raw scan data**; we may only need registrations and
      displacements — confirm which.)
- [ ] Who owns the consent and retention procedure for the **future
      scanner subjects**, and when must it be in place?
- [ ] Retention: how long may dataset copies remain on the workstation
      after the internship ends?

Until these are answered this item stays unticked.
