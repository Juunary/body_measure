"""What produced a record, as a short hash: the spec, the code, the record
schema and the feature space. A store built by one pipeline and queried
by another says so instead of silently comparing different numbers."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from ..spec import default_spec_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def spec_sha256(path: Path | None = None) -> str:
    return hashlib.sha256((path or default_spec_path()).read_bytes()).hexdigest()


def git_head(root: Path = PROJECT_ROOT) -> str:
    """Short HEAD, with `-dirty` when body_measure/ has uncommitted changes."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root,
                             capture_output=True, text=True, timeout=10)
        head = out.stdout.strip()
        if out.returncode == 0 and head:
            dirty = subprocess.run(["git", "status", "--porcelain", "--", "body_measure"],
                                   cwd=root, capture_output=True, text=True, timeout=10)
            return head + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def pipeline_hash(*, feature_space_version: str, record_schema_version: int,
                  spec_digest: str | None = None, head: str | None = None) -> str:
    """16 hex characters over (git head, spec digest, record schema,
    feature space version). Two stores with the same hash were built by
    the same measuring code on the same spec and may be compared."""
    text = "|".join([
        head or git_head(), spec_digest or spec_sha256(),
        str(record_schema_version), feature_space_version,
    ])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
