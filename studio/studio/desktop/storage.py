"""Atomic, integrity-checked polo-simulation/1 desktop project files."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

VERSION = "polo-simulation/1"


def _hash(artifact):
    content = {k: v for k, v in artifact.items() if k != "content_hash"}
    encoded = json.dumps(content, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def save(path, artifact):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {**artifact, "schema_version": VERSION}
    value["content_hash"] = _hash(value)
    fd, temporary = tempfile.mkstemp(prefix=path.name+".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return value


def load(path):
    def invalid(value):
        raise ValueError(f"non-finite JSON number: {value}")
    with open(path, encoding="utf-8-sig") as stream:
        value = json.load(stream, parse_constant=invalid)
    if not isinstance(value, dict) or value.get("schema_version") != VERSION:
        raise ValueError("unsupported desktop project version")
    if value.get("content_hash") != _hash(value):
        raise ValueError("desktop project content hash mismatch")
    plan = value.get("plan")
    if not isinstance(plan, dict) or plan.get("schema_version") != "polo-plan/2" or not plan.get("operations"):
        raise ValueError("desktop project has no valid polo plan")
    playback = value.get("playback") or {}
    position = playback.get("position_s")
    if isinstance(position, bool) or not isinstance(position, (int, float)) or not math.isfinite(position):
        raise ValueError("desktop project has an invalid playback position")
    if not 0 <= position <= plan["totals"]["duration_s"]:
        raise ValueError("desktop project playback position is outside the plan")
    return value
