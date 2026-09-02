"""Audit what CAPE actually ships, before an adapter assumes anything.

This is the SIZER audit's rule (decision #17) applied to a different
dataset, and it is a separate script rather than a flag on that one for a
reason worth stating: pointing `audit_sizer_manifest.py` at CAPE produces
a WRONG and dangerously strong answer. Its role patterns match against the
whole path, and CAPE's body surfaces live in a directory called
`minimal_body_shape/` — so every one of them matches `(minimal|...)`, is
filed as `raw_minimal_scan`, and the verdict comes out as "same-subject
minimal-scan measurements": the strongest claim the vocabulary has, on a
dataset that ships no scans at all.

CAPE ships **registrations**. `minimal_body_shape` is a minimally-clothed
body in a canonical T pose, fitted to SMPL topology; the sequence frames
are SMPL+D registrations of clothed observations, not the observations.
Decision #34 established this and established what follows from it: the
body is measured by rebuilding it in this project's A pose from the
published betas, never as shipped. So the verdict here is fixed at the
downgraded wording, and a test fails if it ever comes out stronger.

Writes:
  reports/cape-manifest.json        every file, its role and reference kind
  reports/cape-split-manifest.json  subject-disjoint split + its SHA-256

The sequence frames are still inside the per-subject zips (`sequences/` on
disk is empty), so they are inventoried from the zip listings and not
hashed — there are ~148,000 of them and the zip's own digest identifies
them collectively.

Run:
  .venv\\Scripts\\python scripts\\audit_cape_manifest.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "reports"

SUBJECT_RE = re.compile(r"^\d{5}$")

#: surface_role -> reference_kind usable against it (claims.py vocabulary).
#: Nothing here maps to `minimal_scan_surface`: CAPE has no scans to offer.
ROLE_TO_REFERENCE_KIND = {
    "provided_body_registration_tpose": "provided_body_registration",
    "provided_betas": None,        # an input for rebuilding, not a surface
    "clothed_registration_frame": None,   # an observation, not a reference
    "dataset_metadata": None,
    "unclassified": None,
}


def classify(relative: str) -> str:
    """Role from the file's POSITION in the release, not from a substring
    of its path. `minimal_body_shape/` is a directory name, and matching
    text against it is exactly how a registration gets mistaken for a
    scan."""
    parts = relative.split("/")
    name = parts[-1]
    # Prose first, wherever it sits: CAPE drops a REAME.md (its own typo)
    # into minimal_body_shape/, and a release note is not a surface.
    if name.lower().endswith((".md", ".txt")) and "seq_lists" not in parts:
        return "dataset_metadata"
    if "minimal_body_shape" in parts:
        if name.endswith("_param.pkl"):
            return "provided_betas"
        if name.endswith((".ply", ".npy", ".obj")):
            return "provided_body_registration_tpose"
        return "unclassified"
    if "sequences" in parts and name.endswith(".npz"):
        return "clothed_registration_frame"
    if "misc" in parts or "seq_lists" in parts or "overview_imgs" in parts:
        return "dataset_metadata"
    return "unclassified"


def subject_of(relative: str) -> str | None:
    """The five-digit id, taken from a path COMPONENT or from the stem's
    leading id. Never from a substring, so `seq_list_00215.txt` resolves
    and a stray temp file does not."""
    parts = relative.split("/")
    for part in parts[:-1]:
        if SUBJECT_RE.fullmatch(part):
            return part
    match = re.match(r"(\d{5})[_.]", parts[-1]) or re.search(r"_(\d{5})\.", parts[-1])
    return match.group(1) if match else None


def sha256(path: Path, limit_mb: float = 64.0) -> str:
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


def removed_frame_ranges(root: Path) -> dict[str, list[str]]:
    """CAPE removes frames whose registration failed, and lists them. The
    sequences are therefore NOT contiguous — frame index n+1 need not be
    the neighbour of frame n."""
    out: dict[str, list[str]] = {}
    for path in sorted((root / "cape_release" / "seq_lists").glob(
            "seq_with_removed_frames_*.txt")):
        subject = path.stem.replace("seq_with_removed_frames_", "")
        rows = [line.split() for line in
                path.read_text(encoding="utf-8", errors="replace").splitlines()
                if line.strip()]
        out[subject] = [" ".join(r) for r in rows if len(r) >= 2 and "-" in r[-1]]
    return out


def sequences_from_seq_lists(root: Path) -> dict[str, list[str]]:
    """Sequence names per subject, in the order the release lists them —
    the frame rule below depends on that order being the release's and not
    ours."""
    out: dict[str, list[str]] = {}
    for path in sorted((root / "cape_release" / "seq_lists").glob("seq_list_*.txt")):
        subject = path.stem.replace("seq_list_", "")
        names = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            token = line.split()[0] if line.split() else ""
            if "_" in token and not token.startswith("("):
                names.append(token)
        out[subject] = names
    return out


def frames_from_zips(root: Path) -> tuple[dict[str, dict[str, list[str]]], list[dict]]:
    """Inventory the sequence frames without extracting 10 GB.

    Returns (frames[subject][sequence] -> sorted npz names, zip records).
    """
    frames: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    archives = []
    for path in sorted(root.glob("*.zip")):
        if not SUBJECT_RE.fullmatch(path.stem):
            continue          # cape_release.zip / minimal_body_params.zip
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
        n_other = 0
        for name in names:
            parts = name.replace("\\", "/").split("/")
            if not name.endswith(".npz") or len(parts) < 3:
                n_other += 1
                continue
            frames[parts[0]][parts[-2]].append(parts[-1])
        archives.append({
            "archive": path.name,
            "subject_id": path.stem,
            "n_entries": len(names),
            "n_frames": sum(len(v) for v in frames[path.stem].values()),
            "n_non_frame_entries": n_other,
            "size_bytes": path.stat().st_size,
            "sha256_head": sha256(path),
        })
    return ({s: {q: sorted(f) for q, f in seqs.items()} for s, seqs in frames.items()},
            archives)


#: One frame per outfit is the first pass. In CAPE's canonical space the
#: displacement varies little between frames of the same outfit, and the
#: alternative — 148,000 near-duplicates — would inflate every N without
#: adding a body. The rule is recorded and hashed so a later change is
#: visible rather than silent.
FRAME_RULE = ("one frame per (subject, outfit): the first sequence of that "
              "outfit in seq_list order, its lowest-numbered .npz")


def pick_frames(sequences: dict[str, list[str]],
                frames: dict[str, dict[str, list[str]]]) -> dict[str, dict]:
    """Apply FRAME_RULE. Outfit is the first token of a sequence name."""
    picked: dict[str, dict] = {}
    for subject, names in sorted(sequences.items()):
        available = frames.get(subject, {})
        by_outfit: dict[str, str] = {}
        for name in names:                      # seq_list order is the release's
            outfit = name.split("_")[0]
            if outfit not in by_outfit and available.get(name):
                by_outfit[outfit] = name
        if by_outfit:
            # min(), not [0]: the rule says lowest-numbered, so it holds
            # whether or not the caller happened to hand them over sorted
            picked[subject] = {
                outfit: {"sequence": sequence, "npz": min(available[sequence])}
                for outfit, sequence in sorted(by_outfit.items())
            }
    return picked


def build_manifest(root: Path) -> dict:
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() == ".zip":
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        parts = relative.split("/")
        if "cape_utils" in parts or any(part.startswith(".") for part in parts):
            continue   # the parsing scripts are code; dot-directories are not
                       # CAPE's at all — tooling state has landed in here before
        role = classify(relative)
        entries.append({
            "subject_id": subject_of(relative),
            "surface_role": role,
            "reference_kind": ROLE_TO_REFERENCE_KIND.get(role),
            "relative_source_path": relative,
            "source_sha256_head": sha256(path),
            "size_bytes": path.stat().st_size,
        })

    sequences = sequences_from_seq_lists(root)
    frames, archives = frames_from_zips(root)

    # Three independent lists of who is in this release. They disagree, so
    # the manifest takes the intersection and names the difference rather
    # than trusting whichever file it read first (decision #34).
    with_body = {e["subject_id"] for e in entries
                 if e["surface_role"] == "provided_body_registration_tpose"
                 and e["subject_id"]}
    with_betas = {e["subject_id"] for e in entries
                  if e["surface_role"] == "provided_betas" and e["subject_id"]}
    with_seq_list = set(sequences)
    subjects = sorted(with_body & with_betas & with_seq_list)

    genders_path = root / "cape_release" / "misc" / "subj_genders.pkl"
    listed_genders: dict[str, str] = {}
    if genders_path.is_file():
        import pickle
        with open(genders_path, "rb") as handle:
            listed_genders = dict(pickle.load(handle, encoding="latin1"))

    downloaded = sorted(frames)
    return {
        "root": str(root),
        "dataset": "cape",
        "n_files": len(entries),
        "n_subjects": len(subjects),
        "subjects": subjects,
        "role_counts": dict(Counter(e["surface_role"] for e in entries)),
        "subject_sources": {
            "minimal_body_shape": sorted(with_body),
            "minimal_body_params": sorted(with_betas),
            "seq_lists": sorted(with_seq_list),
            "subj_genders_pkl": sorted(listed_genders),
        },
        # named, not silently dropped: subj_genders.pkl lists two subjects
        # that ship nothing at all
        "phantom_subjects": sorted(set(listed_genders) - set(subjects)),
        "genders": {s: listed_genders.get(s) for s in subjects},
        "subjects_downloaded": downloaded,
        "archives": archives,
        "outfits_per_subject": {
            s: sorted({q.split("_")[0] for q in frames.get(s, {})}) for s in downloaded
        },
        "frames_per_subject": {s: sum(len(v) for v in frames.get(s, {}).values())
                               for s in downloaded},
        "removed_frame_ranges": removed_frame_ranges(root),
        "frame_rule": FRAME_RULE,
        "selected_frames": pick_frames(sequences, frames),
        "verdict": {
            "raw_minimal_scan_available": False,
            "claim_wording": "same-subject provided body-reference surface",
            "note": (
                "CAPE ships registrations, not scans. minimal_body_shape is a "
                "minimally-clothed body fitted to SMPL topology in a canonical "
                "T pose, and the sequence frames are SMPL+D registrations of "
                "clothed observations. Results may be described as "
                "fit_reference_agreement against a provided registration, "
                "never as agreement with a minimal scan. The body is measured "
                "by rebuilding it in this project's A pose from the published "
                "betas, never as shipped (decision #34)."
            ),
        },
        "entries": entries,
    }


def build_split(manifest: dict, *, test_fraction: float = 0.25,
                seed: int = 20260817) -> dict:
    """Subject-disjoint, decided here rather than at training time.

    CAPE repeats a subject across outfits and thousands of frames, so a
    frame-level random split would put one body shape on both sides — and
    far more severely than SIZER's per-garment repeats, because consecutive
    frames of one sequence are nearly the same observation."""
    import random

    subjects = list(manifest["subjects"])
    rng = random.Random(seed)
    shuffled = subjects[:]
    rng.shuffle(shuffled)
    n_test = max(1, round(len(shuffled) * test_fraction)) if shuffled else 0
    payload = {
        "dataset": "cape",
        "policy": "subject_disjoint",
        "seed": seed,
        "test_fraction": test_fraction,
        "n_subjects": len(subjects),
        "train_subjects": sorted(shuffled[n_test:]),
        "test_subjects": sorted(shuffled[:n_test]),
        "frame_rule": manifest["frame_rule"],
        "rule": (
            "Train-only statistics feed the C2 priors and the C3 simulator. "
            "Test subjects never contribute to any prior, threshold or "
            "calibration. The frame rule is part of the split: changing how "
            "many frames a subject contributes changes every N computed from "
            "it, so it is hashed here too."
        ),
    }
    payload["sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=PROJECT_ROOT / "data" / "external" / "cape")
    parser.add_argument("--test-fraction", type=float, default=0.25)
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"CAPE not found at {args.root} — see docs/datasets.md; the "
              "release terms are already on file (LICENSE-G0 item 2).",
              file=sys.stderr)
        return 1

    REPORTS.mkdir(exist_ok=True)
    manifest = build_manifest(args.root)
    (REPORTS / "cape-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    split = build_split(manifest, test_fraction=args.test_fraction)
    (REPORTS / "cape-split-manifest.json").write_text(
        json.dumps(split, indent=2), encoding="utf-8")

    print(f"files {manifest['n_files']} | subjects {manifest['n_subjects']} "
          f"| downloaded {len(manifest['subjects_downloaded'])}")
    print("roles:", manifest["role_counts"])
    if manifest["phantom_subjects"]:
        print(f"phantom subjects (a gender and nothing else): "
              f"{manifest['phantom_subjects']}")
    for subject in manifest["subjects_downloaded"]:
        outfits = manifest["outfits_per_subject"][subject]
        print(f"  {subject} ({manifest['genders'].get(subject)}): "
              f"{manifest['frames_per_subject'][subject]} frames, "
              f"outfits {outfits}")
    print("\nraw minimal scan available:",
          manifest["verdict"]["raw_minimal_scan_available"])
    print("claim wording:", manifest["verdict"]["claim_wording"])
    unclassified = manifest["role_counts"].get("unclassified", 0)
    if unclassified:
        print(f"\n{unclassified} file(s) unclassified — inspect and extend "
              "classify() rather than letting an adapter guess:")
        for entry in manifest["entries"]:
            if entry["surface_role"] == "unclassified":
                print(f"  {entry['relative_source_path']}")
    print(f"\nsplit: {len(split['train_subjects'])} train / "
          f"{len(split['test_subjects'])} test, sha256 {split['sha256'][:16]}")
    print(f"frame rule: {manifest['frame_rule']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
