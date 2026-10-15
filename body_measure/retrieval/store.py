"""A store is a directory: `records.jsonl` (authoritative), `features.npz`
(the standardised matrix, rebuilt from the records), `manifest.json`
(what built it) and, once calibrated, `calibration.json`.

The licence gate lives here. A record's class says where it may go, and
`export` writes a copy only when every record in the store may go there.
There is no command-line flag to widen that, because widening it is a
licence decision (docs/licenses/scope.md), not a command-line one. It is
the same enforcement style as `claims.REFERENCE_KINDS[...].available`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .features import FEATURE_KEYS, FEATURE_SPACE_VERSION, FeatureSpace, fit_standardiser, raw_vector
from .record import EXPORTABLE, RECORD_SCHEMA_VERSION, LicenceClass, ScanRecord
from .versioning import PROJECT_ROOT, pipeline_hash, spec_sha256

DEFAULT_ROOT = PROJECT_ROOT / "data" / "retrieval"
RECORDS, FEATURES, MANIFEST, CALIBRATION = (
    "records.jsonl", "features.npz", "manifest.json", "calibration.json")


class StoreError(RuntimeError):
    pass


class LicenceExportError(PermissionError):
    """A record whose licence keeps it on this machine was about to leave it."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve(name_or_path: str | Path, root: Path = DEFAULT_ROOT) -> Path:
    """`--db NAME` is a directory under data/retrieval/; a path is itself."""
    p = Path(name_or_path)
    if p.is_absolute() or len(p.parts) > 1:
        return p
    return root / p.name


class RecordStore:
    def __init__(self, path: Path, db_name: str, records: list[ScanRecord] | None = None,
                 space: FeatureSpace | None = None, manifest: dict | None = None):
        self.path = Path(path)
        self.db_name = db_name
        self.records: list[ScanRecord] = list(records or [])
        self.space = space
        self.manifest: dict = dict(manifest or {})
        self._check_unique()

    # ------------------------------------------------------------ create ---
    @classmethod
    def create(cls, name_or_path: str | Path, *, note: str = "",
               overwrite: bool = False) -> "RecordStore":
        path = resolve(name_or_path)
        if (path / RECORDS).exists() and not overwrite:
            raise StoreError(f"store already exists at {path}; open it, or pass overwrite")
        store = cls(path, path.name)
        store.manifest = {"db_name": store.db_name, "note": note, "created_utc": _now()}
        return store

    @classmethod
    def open(cls, name_or_path: str | Path) -> "RecordStore":
        path = resolve(name_or_path)
        if not (path / RECORDS).exists():
            raise StoreError(f"no store at {path} ({RECORDS} missing)")
        manifest = json.loads((path / MANIFEST).read_text(encoding="utf-8"))
        if int(manifest.get("record_schema_version", 0)) != RECORD_SCHEMA_VERSION:
            raise StoreError(
                f"store {path.name} has record schema {manifest.get('record_schema_version')}, "
                f"this code reads {RECORD_SCHEMA_VERSION}; rebuild it")
        records = [ScanRecord.from_json(line)
                   for line in (path / RECORDS).read_text(encoding="utf-8").splitlines()
                   if line.strip()]
        space = (FeatureSpace.from_dict(manifest["feature_space"])
                 if manifest.get("feature_space") else None)
        return cls(path, manifest.get("db_name", path.name), records, space, manifest)

    @classmethod
    def merged(cls, name_or_path: str | Path, stores: list["RecordStore"], *,
               note: str = "", overwrite: bool = False) -> "RecordStore":
        """A new store holding every record of `stores`. Licence classes
        travel with the records, so a merge of a synthetic and a local-only
        store is itself unexportable."""
        out = cls.create(name_or_path, note=note, overwrite=overwrite)
        out.manifest["merged_from"] = [s.db_name for s in stores]
        for s in stores:
            out.append(s.records)
        return out

    # ----------------------------------------------------------- records ---
    def __len__(self) -> int:
        return len(self.records)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(r.record_id for r in self.records)

    def by_id(self, record_id: str) -> ScanRecord:
        for r in self.records:
            if r.record_id == record_id:
                return r
        raise KeyError(record_id)

    def _check_unique(self) -> None:
        seen: set[str] = set()
        for r in self.records:
            if r.record_id in seen:
                raise StoreError(f"duplicate record_id {r.record_id!r}")
            seen.add(r.record_id)

    def append(self, records) -> int:
        new = [records] if isinstance(records, ScanRecord) else list(records)
        existing = set(self.ids)
        for r in new:
            if r.record_id in existing:
                raise StoreError(f"record_id {r.record_id!r} is already in the store")
            existing.add(r.record_id)
        self.records.extend(new)
        return len(new)

    def filter(self, *, licence_class: LicenceClass | None = None, split: str | None = None,
               source_type: str | None = None, population: str | None = None) -> list[ScanRecord]:
        out = self.records
        if licence_class is not None:
            out = [r for r in out if r.licence_class == licence_class]
        if split is not None:
            out = [r for r in out if r.split == split]
        if source_type is not None:
            out = [r for r in out if r.source_type == source_type]
        if population is not None:
            out = [r for r in out if r.population == population]
        return list(out)

    # ---------------------------------------------------------- features ---
    def rows(self) -> list[tuple[np.ndarray, np.ndarray]]:
        return [raw_vector(r.feature_values(), r.feature_usable()) for r in self.records]

    def fit_space(self, *, version: str = FEATURE_SPACE_VERSION) -> FeatureSpace:
        """Refit the standardiser on every record. `save` calls it, so a
        store's space always describes the records it holds."""
        self.space = fit_standardiser(self.rows(), keys=FEATURE_KEYS, version=version)
        return self.space

    def matrix(self) -> tuple[np.ndarray, np.ndarray]:
        """(Z, mask): standardised feature matrix and availability mask."""
        if self.space is None:
            raise StoreError("the store has no feature space yet; call fit_space()")
        rows = self.rows()
        if not rows:
            return np.zeros((0, self.space.dim)), np.zeros((0, self.space.dim), dtype=bool)
        Z = np.stack([self.space.standardise(r, m) for r, m in rows])
        mask = np.stack([m for _, m in rows])
        return Z, mask

    def index(self, **kwargs):
        from .index import BruteForceIndex

        Z, mask = self.matrix()
        # the distance reads the space's index keys only; the other keys
        # stay in the store and are estimated from the neighbours
        return BruteForceIndex(Z, mask & self.space.index_mask()[None, :], self.ids, **kwargs)

    # ------------------------------------------------------------ persist --
    def records_sha256(self) -> str:
        h = hashlib.sha256()
        for r in self.records:
            h.update(r.to_json().encode("utf-8"))
            h.update(b"\n")
        return h.hexdigest()

    def counts(self) -> dict:
        def by(f):
            keys = sorted({str(f(r)) for r in self.records})
            return {k: sum(1 for r in self.records if str(f(r)) == k) for k in keys}
        return {
            "n_records": len(self.records),
            "n_by_licence_class": by(lambda r: r.licence_class.value),
            "n_by_split": by(lambda r: r.split),
            "n_by_source_type": by(lambda r: r.source_type),
            "n_by_population": by(lambda r: r.population),
        }

    def save(self, *, refit: bool = True) -> Path:
        if not self.records:
            raise StoreError("refusing to save an empty store")
        if refit or self.space is None:
            self.fit_space()
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / RECORDS).write_text(
            "".join(r.to_json() + "\n" for r in self.records), encoding="utf-8")
        Z, mask = self.matrix()
        betas = np.array([r.betas if r.betas is not None else [np.nan] * 10
                          for r in self.records], dtype=np.float32)
        np.savez(self.path / FEATURES, Z=Z.astype(np.float32), mask=mask, betas=betas,
                 ids=np.array(self.ids, dtype=str))
        self.manifest.update({
            "db_name": self.db_name,
            "record_schema_version": RECORD_SCHEMA_VERSION,
            "feature_space": self.space.to_dict(),
            "spec_sha256": spec_sha256(),
            "pipeline_hash": pipeline_hash(feature_space_version=self.space.version,
                                           record_schema_version=RECORD_SCHEMA_VERSION),
            "pipeline_hashes_in_records": sorted({r.pipeline_hash for r in self.records}),
            "records_sha256": self.records_sha256(),
            "updated_utc": _now(),
            **self.counts(),
        })
        self.manifest.setdefault("created_utc", self.manifest["updated_utc"])
        (self.path / MANIFEST).write_text(
            json.dumps(self.manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.path

    # -------------------------------------------------------- calibration --
    def save_calibration(self, data: dict) -> Path:
        self.path.mkdir(parents=True, exist_ok=True)
        out = self.path / CALIBRATION
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return out

    def load_calibration(self) -> dict | None:
        p = self.path / CALIBRATION
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    # ---------------------------------------------------------- staleness --
    def check_against_current(self) -> list[str]:
        """Flags for a store the current code did not build. A spec change
        is a hard mismatch, because the keys may no longer mean the same
        thing; a code change is reported, not refused."""
        flags = []
        if self.manifest.get("spec_sha256") and self.manifest["spec_sha256"] != spec_sha256():
            raise StoreError("the store was built on a different measurement-spec; rebuild it")
        version = self.space.version if self.space else FEATURE_SPACE_VERSION
        current = pipeline_hash(feature_space_version=version,
                                record_schema_version=RECORD_SCHEMA_VERSION)
        if self.manifest.get("pipeline_hash") and self.manifest["pipeline_hash"] != current:
            flags.append("db_pipeline_hash_stale")
        return flags

    # ------------------------------------------------------------- export --
    def assert_exportable(self, allow: frozenset = EXPORTABLE) -> None:
        """Raise unless every record may leave this machine. Anything that
        derives data from the store for use elsewhere (a copy, a training
        set for the GPU server) calls this first."""
        held = [r for r in self.records if r.licence_class not in allow]
        if held:
            classes = sorted({r.licence_class.value for r in held})
            raise LicenceExportError(
                f"{len(held)} of {len(self.records)} records are {classes}, which may not "
                "leave this machine (docs/licenses/scope.md item 5); nothing was written")

    def export(self, dest: Path, *, allow: frozenset = EXPORTABLE) -> Path:
        """Write a copy of this store at `dest`. Refuses, writing nothing,
        if any record's licence class is outside `allow`. The default is
        what the licences permit; a caller passing a wider set is making
        a licence decision and records it in docs/licenses/scope.md first."""
        self.assert_exportable(allow)
        dest = Path(dest)
        copy = RecordStore(dest, dest.name, list(self.records), self.space,
                           {**self.manifest, "db_name": dest.name,
                            "exported_from": str(self.path), "exported_utc": _now()})
        copy.save(refit=False)
        cal = self.load_calibration()
        if cal is not None:
            copy.save_calibration(cal)
        return dest
