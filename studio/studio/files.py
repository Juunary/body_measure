"""What the file picker offers, and what each entry is allowed to be.

The catalogue is read from body-measure's `data/` tree on every request —
nothing is copied, nothing is cached — plus whatever the user uploaded
into `studio/uploads/`. Every entry carries a licence badge because the
page can be shown to people: only HSRD-100 (CC BY 4.0) may appear in
public material; Texel is CC BY-NC; SMPL bodies, NOMO and CAPE are
internal (body-measure `docs/licenses/public-material.md`).

Units are never guessed. An entry that comes with a verified or declared
unit says so under `fixed`; a plain mesh file (uploads, generated bodies
without a sidecar) leaves `unit` and `up_axis` for the user to state.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from .paths import BODY, UPLOADS

DATA = BODY / "data"
#: Scans placed next to a deployment (a mounted volume), since no dataset
#: is in git and the image is built from git. Each mesh may have a
#: sidecar `<name>.json` with `units`, `up_axis`, `pose`, `population`,
#: `clothed` and `licence` (badge text); without one the unit is asked
#: for, as with an upload.
EXTRA_DATA = Path(os.environ["STUDIO_EXTRA_DATA"]) if os.environ.get("STUDIO_EXTRA_DATA") else None
UPLOAD_SUFFIXES = (".obj", ".ply", ".stl")
UPLOAD_LIMIT_BYTES = 300 * 1024 * 1024

PUBLIC_HSRD = {"badge": "public · CC BY 4.0 · HSRD-100", "public": True,
               "text": "HSRD-100, CC BY 4.0 — attribution required on every figure"}
INTERNAL = {"badge": "internal", "public": False,
            "text": "not cleared for public material"}
INTERNAL_NC = {"badge": "internal · CC BY-NC", "public": False,
               "text": "Texel, CC BY-NC — internal use only, no commercial context"}
UPLOADED = {"badge": "uploaded · user supplied", "public": False,
            "text": "licence unknown — the uploader answers for it"}

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


#: what the file's pose is known to be before it is loaded: "a" (the
#: standing A pose the spec measures), "t", or "other" (a fashion scan, an
#: upload — nothing says). The gate decides on the mesh; this only
#: filters the list.
POSE_A, POSE_T, POSE_OTHER = "a", "t", "other"


def _entry(id_: str, label: str, group: str, kind: str, path: Path, licence: dict,
           *, defaults: dict | None = None, fixed: dict | None = None,
           detail: str = "", pose: str = POSE_OTHER) -> dict:
    return {
        "id": id_, "label": label, "group": group, "kind": kind,
        "path": str(path), "path_display": _display(path),
        "licence": licence, "pose": pose,
        "defaults": {"unit": None, "up_axis": None, "population": None,
                     "clothed": False, **(defaults or {})},
        "fixed": fixed or {},
        "detail": detail,
    }


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(BODY))
    except ValueError:
        try:
            return str(path.relative_to(UPLOADS.parent))
        except ValueError:
            return path.name


def _hsrd() -> list[dict]:
    root = DATA / "external" / "hsrd"
    out = []
    if not root.is_dir():
        return out
    for lod in sorted(p for p in root.iterdir() if p.is_dir() and any(p.glob("*.obj"))):
        obj = next(iter(sorted(lod.glob("*.obj"))))
        person = _json(lod / "person_metadata.json")
        pose = _json(lod / "pose_metadata.json")
        sex = str(person.get("Sex", "")).lower()
        upper = pose.get("Upper Body Clothing")
        clothed = upper not in (None, "None", "")
        detail = ", ".join(x for x in (
            f"{person.get('Height')} cm" if person.get("Height") else "",
            f"{upper}" if clothed else "unclothed",
            pose.get("Lower Body Clothing") or "",
        ) if x)
        out.append(_entry(
            f"hsrd:{lod.name}", f"{obj.stem}  ({lod.name.upper()})", "HSRD-100",
            "hsrd_lod", lod, PUBLIC_HSRD,
            defaults={"population": "women" if sex == "female" else
                      "men" if sex == "male" else None, "clothed": clothed},
            fixed={"unit": "verified against recorded stature", "up_axis": "Z"},
            detail=detail))
    return out


def _texel() -> list[dict]:
    root = DATA / "external" / "texel"
    out = []
    if not root.is_dir():
        return out
    for part in sorted(p for p in root.iterdir() if p.is_dir()):
        for person in sorted(p for p in part.iterdir() if p.is_dir()):
            if not (person / "portal_mx" / "scan.ply").is_file():
                continue
            name = person.name
            population = "men" if name.lower().startswith("man") else \
                "women" if name.lower().startswith("woman") else None
            out.append(_entry(
                f"texel:{part.name}/{name}", f"{part.name} / {name}", "Texel",
                "texel_person", person, INTERNAL_NC,
                defaults={"population": population, "clothed": False},
                fixed={"unit": "mm", "up_axis": "Y"}, detail="portal_mx pipeline",
                pose=POSE_A))
    return out


def _nomo() -> list[dict]:
    root = DATA / "external" / "nomo" / "NOMO-3d-400-scans_and_tc2_measurements" / "extracted"
    out = []
    if not root.is_dir():
        return out
    for gender in ("male", "female"):
        txt_dir = root / f"TC2_{gender.capitalize()}_Txt"
        if not txt_dir.is_dir():
            continue
        for txt in sorted(txt_dir.glob(f"{gender}_*.txt")):
            out.append(_entry(
                f"nomo:{txt.stem}", txt.stem, "NOMO", "nomo", root, INTERNAL,
                defaults={"population": "men" if gender == "male" else "women",
                          "clothed": False},
                fixed={"unit": "verified against TC2 stature", "up_axis": "Y"},
                detail="segmented scan — sleeve_length refuses by design (decision #35)",
                pose=POSE_A))
    return out


def _generated() -> list[dict]:
    root = DATA / "generated"
    out = []
    if not root.is_dir():
        return out
    for obj in sorted(root.glob("*.obj")):
        sidecar = _json(obj.with_suffix(".json"))
        defaults = {"clothed": False}
        detail = "synthetic SMPL body"
        pose = POSE_OTHER
        if sidecar:
            defaults["unit"] = sidecar.get("units")
            defaults["up_axis"] = sidecar.get("up_axis")
            pose = {"a": POSE_A, "t": POSE_T}.get(str(sidecar.get("pose", "")).lower(), POSE_OTHER)
            detail = f"SMPL {sidecar.get('gender', '')} · pose {sidecar.get('pose', '?')} · sidecar declares {sidecar.get('units')}/{sidecar.get('up_axis')}-up"
        out.append(_entry(f"generated:{obj.stem}", obj.stem, "Synthetic SMPL",
                          "mesh_file", obj, INTERNAL, defaults=defaults, detail=detail, pose=pose))
    return out


def _uploads() -> list[dict]:
    out = []
    if not UPLOADS.is_dir():
        return out
    for folder in sorted(p for p in UPLOADS.iterdir() if p.is_dir()):
        for mesh in sorted(folder.iterdir()):
            if mesh.suffix.lower() in UPLOAD_SUFFIXES:
                out.append(_entry(f"upload:{folder.name}/{mesh.name}", mesh.name,
                                  "Uploaded", "mesh_file", mesh, UPLOADED,
                                  detail=f"{mesh.stat().st_size / 1e6:.1f} MB"))
    return out


def _extra() -> list[dict]:
    if EXTRA_DATA is None or not EXTRA_DATA.is_dir():
        return []
    out = []
    for mesh in sorted(p for p in EXTRA_DATA.rglob("*") if p.suffix.lower() in UPLOAD_SUFFIXES):
        sidecar = _json(mesh.with_suffix(".json"))
        licence = INTERNAL if not sidecar.get("licence") else {
            "badge": str(sidecar["licence"]), "public": bool(sidecar.get("public", False)),
            "text": str(sidecar.get("licence_text", ""))}
        pose = {"a": POSE_A, "t": POSE_T}.get(str(sidecar.get("pose", "")).lower(), POSE_OTHER)
        out.append(_entry(
            f"deployed:{mesh.relative_to(EXTRA_DATA).as_posix()}", mesh.stem, "Deployed",
            "mesh_file", mesh, licence,
            defaults={"unit": sidecar.get("units"), "up_axis": sidecar.get("up_axis"),
                      "population": sidecar.get("population"), "clothed": bool(sidecar.get("clothed"))},
            detail=str(sidecar.get("detail", f"{mesh.stat().st_size / 1e6:.1f} MB")), pose=pose))
    return out


def catalogue() -> list[dict]:
    return _hsrd() + _generated() + _texel() + _nomo() + _extra() + _uploads()


def find(file_id: str) -> dict | None:
    for entry in catalogue():
        if entry["id"] == file_id:
            return entry
    return None


def store_upload(filename: str, data: bytes) -> dict:
    suffix = Path(filename).suffix.lower()
    if suffix not in UPLOAD_SUFFIXES:
        raise ValueError(f"unsupported file type {suffix or '(none)'}; "
                         f"expected one of {', '.join(UPLOAD_SUFFIXES)}")
    if len(data) > UPLOAD_LIMIT_BYTES:
        raise ValueError(f"file is {len(data) / 1e6:.0f} MB, limit is "
                         f"{UPLOAD_LIMIT_BYTES / 1e6:.0f} MB")
    safe = _SAFE.sub("_", Path(filename).name) or f"mesh{suffix}"
    folder = UPLOADS / uuid.uuid4().hex[:10]
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / safe
    target.write_bytes(data)
    return find(f"upload:{folder.name}/{safe}")


def _json(path: Path) -> dict:
    """A sidecar written on Windows often starts with a UTF-8 BOM, which
    strict UTF-8 rejects and utf-8-sig strips; a sidecar that is not JSON
    is treated as absent, not as an error."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    except (json.JSONDecodeError, OSError):
        return {}
