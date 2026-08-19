"""Audit what SIZER actually ships, before an adapter assumes anything.

The published description says ~100 subjects and ~2000 scans with garment
segmentation and SMPL-family registrations. It does NOT establish that
every clothed scan has an independent raw minimal-clothing scan in 1:1
correspondence. "Body under clothing" and "a provided registration" are
different references licensing different claims
(see body_measure/validate/claims.py), so the difference has to be
measured, not assumed.

This script inventories the download and writes:

  reports/sizer-manifest.json   every surface, its role and reference kind
  reports/split-manifest.json   subject-disjoint split + its SHA-256

Run after the SIZER download:
  .venv\\Scripts\\python scripts\\audit_sizer_manifest.py --root data/external/sizer
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "reports"

MESH_SUFFIXES = {".obj", ".ply"}
REGISTRATION_SUFFIXES = {".pkl", ".npz", ".npy"}

#: Filename hints -> surface_role. Deliberately conservative: anything that
#: does not match becomes "unclassified" and is reported, never guessed
#: into a role. Extend only after looking at real filenames.
ROLE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(minimal|underwear|naked|nude|body_under|scan_body)", "raw_minimal_scan"),
    (r"(smpld|smpl\+d|smpl_d)", "provided_smpld_registration"),
    (r"(registration|smpl|betas|fit)", "provided_smpl_registration"),
    (r"(body|shape)", "provided_body_surface"),
    (r"(shirt|tshirt|t-shirt|pants|short|hoodie|coat|jacket|skirt|dress|garment|clothed)",
     "clothed_scan"),
)

#: surface_role -> reference_kind usable against it (claims.py vocabulary).
ROLE_TO_REFERENCE_KIND = {
    "raw_minimal_scan": "minimal_scan_surface",
    "provided_body_surface": "provided_body_registration",
    "provided_smpl_registration": "provided_body_registration",
    "provided_smpld_registration": "provided_body_registration",
    "clothed_scan": None,          # an observation, not a reference
    "unclassified": None,
}

SMPL_VARIANTS = ("neutral", "male", "female")


def sha256(path: Path, limit_mb: float = 64.0) -> str:
    """Hash the first `limit_mb` — enough to identify a file without
    re-reading gigabytes of meshes."""
    digest = hashlib.sha256()
    remaining = int(limit_mb * 1e6)
    with open(path, "rb") as handle:
        while remaining > 0:
            chunk = handle.read(min(1 << 20, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def classify_role(path: Path) -> str:
    text = str(path).lower().replace("\\", "/")
    for pattern, role in ROLE_PATTERNS:
        if re.search(pattern, text):
            return role
    return "unclassified"


def guess_subject(path: Path, root: Path) -> str:
    """First path component under the root that looks like an id."""
    parts = path.relative_to(root).parts
    for part in parts:
        if re.fullmatch(r"[A-Za-z]*\d{2,}[A-Za-z0-9_-]*", part):
            return part
    return parts[0] if parts else "unknown"


def guess_garment(path: Path) -> str | None:
    text = str(path).lower()
    for name in ("tshirt", "t-shirt", "shirt", "pants", "shorts", "hoodie",
                 "coat", "jacket", "skirt", "dress"):
        if name in text:
            return name.replace("-", "")
    return None


def guess_size(path: Path) -> str | None:
    match = re.search(r"[_/-](XS|S|M|L|XL|XXL)[_/.-]", str(path), re.IGNORECASE)
    return match.group(1).upper() if match else None


def guess_variant(path: Path) -> str | None:
    text = str(path).lower()
    return next((v for v in SMPL_VARIANTS if v in text), None)


def build_manifest(root: Path) -> dict:
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in MESH_SUFFIXES | REGISTRATION_SUFFIXES:
            continue
        role = classify_role(path)
        entries.append({
            "subject_id": guess_subject(path, root),
            "observation_id": path.stem,
            "surface_role": role,
            "reference_kind": ROLE_TO_REFERENCE_KIND.get(role),
            "is_registration": suffix in REGISTRATION_SUFFIXES,
            "garment_class_raw": guess_garment(path),
            "garment_size": guess_size(path),
            "smpl_variant": guess_variant(path),
            "relative_source_path": str(path.relative_to(root)).replace("\\", "/"),
            "source_sha256_head": sha256(path),
            "size_bytes": path.stat().st_size,
        })

    by_subject: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        by_subject[entry["subject_id"]].append(entry)

    # The question the adapter must not assume the answer to:
    with_minimal = sorted(
        s for s, rows in by_subject.items()
        if any(r["surface_role"] == "raw_minimal_scan" for r in rows)
    )
    with_registration = sorted(
        s for s, rows in by_subject.items()
        if any(r["surface_role"].startswith("provided_") for r in rows)
    )
    return {
        "root": str(root),
        "n_files": len(entries),
        "n_subjects": len(by_subject),
        "role_counts": dict(Counter(e["surface_role"] for e in entries)),
        "garment_counts": dict(Counter(
            e["garment_class_raw"] for e in entries if e["garment_class_raw"]
        )),
        "size_counts": dict(Counter(
            e["garment_size"] for e in entries if e["garment_size"]
        )),
        "variant_counts": dict(Counter(
            e["smpl_variant"] for e in entries if e["smpl_variant"]
        )),
        "subjects_with_raw_minimal_scan": with_minimal,
        "subjects_with_provided_registration": with_registration,
        "verdict": {
            "raw_minimal_scan_available": bool(with_minimal),
            "claim_wording": (
                "same-subject minimal-scan measurements"
                if with_minimal
                else "same-subject provided body-reference surface"
            ),
            "note": (
                "Until raw_minimal_scan_available is true, results may only be "
                "described as fit_reference_agreement against a provided "
                "registration — not as agreement with a minimal scan."
            ),
        },
        "observations_per_subject": {
            subject: sum(1 for r in rows if r["surface_role"] == "clothed_scan")
            for subject, rows in sorted(by_subject.items())
        },
        "entries": entries,
    }


def build_split(manifest: dict, *, test_fraction: float = 0.25, seed: int = 20260817) -> dict:
    """Subject-disjoint split, locked here rather than at training time.

    SIZER repeats a subject across garments and sizes, so a scan-level
    random split would put one body shape in both train and test."""
    import random

    subjects = sorted(manifest["observations_per_subject"])
    rng = random.Random(seed)
    shuffled = subjects[:]
    rng.shuffle(shuffled)
    n_test = max(1, round(len(shuffled) * test_fraction)) if shuffled else 0
    test = sorted(shuffled[:n_test])
    train = sorted(shuffled[n_test:])
    payload = {
        "policy": "subject_disjoint",
        "seed": seed,
        "test_fraction": test_fraction,
        "n_subjects": len(subjects),
        "train_subjects": train,
        "test_subjects": test,
        "rule": (
            "Train-only statistics feed the C1b gap atlas, the C2 priors and "
            "the C3 simulator calibration. Test subjects never contribute to "
            "any prior, threshold or calibration."
        ),
    }
    payload["sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=PROJECT_ROOT / "data" / "external" / "sizer")
    parser.add_argument("--test-fraction", type=float, default=0.25)
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"SIZER not found at {args.root} — register and download first "
              "(docs/datasets.md), and complete LICENSE-G0.", file=sys.stderr)
        return 1

    REPORTS.mkdir(exist_ok=True)
    manifest = build_manifest(args.root)
    (REPORTS / "sizer-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    split = build_split(manifest, test_fraction=args.test_fraction)
    (REPORTS / "split-manifest.json").write_text(
        json.dumps(split, indent=2), encoding="utf-8")

    print(f"files {manifest['n_files']} | subjects {manifest['n_subjects']}")
    print("roles:", manifest["role_counts"])
    print("garments:", manifest["garment_counts"])
    print("raw minimal scan available:",
          manifest["verdict"]["raw_minimal_scan_available"])
    print("claim wording:", manifest["verdict"]["claim_wording"])
    unclassified = manifest["role_counts"].get("unclassified", 0)
    if unclassified:
        print(f"\n{unclassified} file(s) unclassified — inspect and extend "
              "ROLE_PATTERNS rather than letting the adapter guess.")
    print(f"\nsplit: {len(split['train_subjects'])} train / "
          f"{len(split['test_subjects'])} test, sha256 {split['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
