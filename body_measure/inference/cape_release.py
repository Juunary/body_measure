"""Reading CAPE, deliberately not as an adapter.

An `Adapter.load()` returns a surface the measurement core will measure.
CAPE has nothing that may be measured as shipped: `minimal_body_shape` is
a canonical **T pose**, and this pipeline's core assumes hanging arms — a
T-posed body gives a chest circumference of 3808 mm because the loop goes
round the torso and both outstretched arms (decision #34). Writing a CAPE
adapter would create the path by which that mesh reaches the core, and
somebody would eventually take it.

So this reader hands back arrays and parameters, never a
`NormalizedBodySurface`. The body is rebuilt in this project's A pose from
the betas CAPE publishes; `cape_transfer.py` does that and returns a
shell the core CAN measure.

Everything here is numpy and pickle — no torch — but it lives under
`inference/` because that is where CAPE belongs, not because it needs a
GPU.
"""
from __future__ import annotations

import io
import pickle
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAPE_ROOT = PROJECT_ROOT / "data" / "external" / "cape"

#: SMPL topology. A displacement is only meaningful against this count.
N_VERTICES = 6890
#: The two subjects downloaded on 2026-09-01 (docs/plan.md §1a). 00215 is
#: the only one with a polo; 00096 has the most short-sleeve outfits.
DOWNLOADED = ("00215", "00096")


class CapeError(RuntimeError):
    """CAPE is not what this reader was told to expect."""


@dataclass(frozen=True)
class CapeFrame:
    subject: str
    outfit: str
    sequence: str
    npz_name: str
    #: clothed surface in CAPE's canonical T pose, metres, (6890, 3)
    v_cano_m: np.ndarray

    @property
    def frame_index(self) -> int:
        match = re.search(r"\.(\d+)\.npz$", self.npz_name)
        return int(match.group(1)) if match else -1

    def provenance(self) -> dict:
        return {"dataset": "cape", "subject": self.subject, "outfit": self.outfit,
                "sequence": self.sequence, "npz": self.npz_name,
                "frame": self.frame_index}


class CapeRelease:
    """The parts of a CAPE download this project uses."""

    def __init__(self, root: Path = CAPE_ROOT):
        self.root = Path(root)
        self.release = self.root / "cape_release"
        if not self.release.is_dir():
            raise CapeError(f"no cape_release under {self.root}")

    # ------------------------------------------------------- subjects ---
    def _ids_from(self, directory: Path) -> set[str]:
        return {p.name for p in directory.iterdir()
                if p.is_dir() and re.fullmatch(r"\d{5}", p.name)} \
            if directory.is_dir() else set()

    def subjects(self) -> tuple[str, ...]:
        """The intersection of the three places that list subjects.

        `misc/subj_genders.pkl` is NOT one of them: it names 17 while the
        release ships 15, and reading the file most obviously meant for the
        job invents two subjects (decision #34)."""
        bodies = self._ids_from(self.release / "minimal_body_shape")
        params = self._ids_from(self.root / "minimal_body_params" / "minimal_body_shape")
        listed = {p.stem.replace("seq_list_", "")
                  for p in (self.release / "seq_lists").glob("seq_list_*.txt")}
        return tuple(sorted(bodies & params & listed))

    def gender(self, subject: str) -> str:
        """From the release's own table. SMPL's shape space is gendered, so
        rebuilding a body with the wrong one is not a rounding error."""
        path = self.release / "misc" / "subj_genders.pkl"
        with open(path, "rb") as handle:
            table = pickle.load(handle, encoding="latin1")
        if subject not in table:
            raise CapeError(f"{subject} has no gender in {path.name}")
        return str(table[subject])

    # ----------------------------------------------------------- body ---
    def _params_dir(self, subject: str) -> Path:
        return self.root / "minimal_body_params" / "minimal_body_shape" / subject

    def betas(self, subject: str) -> np.ndarray:
        """The published shape parameters (2023-07 addition).

        Refuses unless the accompanying pose and translation are zero: the
        betas are only the body's shape if the fit they came from was a
        rest pose, and a non-zero pose here would mean they encode
        something else."""
        path = self._params_dir(subject) / f"{subject}_param.pkl"
        with open(path, "rb") as handle:
            param = pickle.load(handle, encoding="latin1")
        for key in ("pose", "trans"):
            value = np.asarray(param.get(key, 0.0), dtype=np.float64)
            if np.any(np.abs(value) > 1e-6):
                raise CapeError(
                    f"{subject}: {path.name} has a non-zero '{key}', so its betas "
                    "are not a rest-pose shape fit")
        betas = np.asarray(param["betas"], dtype=np.float64).reshape(-1)
        if betas.size < 10:
            raise CapeError(f"{subject}: expected >= 10 betas, got {betas.size}")
        return betas[:10]

    def minimal_body_T_m(self, subject: str) -> np.ndarray:
        """The minimally-clothed body in CAPE's canonical T pose, metres.

        This is the surface a displacement is measured against. It is NOT
        a surface to measure: see the module docstring."""
        import trimesh

        path = self.release / "minimal_body_shape" / subject / f"{subject}_minimal.ply"
        mesh = trimesh.load(path, process=False)
        vertices = np.asarray(mesh.vertices, dtype=np.float64)
        if vertices.shape != (N_VERTICES, 3):
            raise CapeError(f"{subject}: expected {N_VERTICES} vertices, got "
                            f"{vertices.shape}")
        return vertices

    # ------------------------------------------------------- sequences ---
    def sequence_names(self, subject: str) -> tuple[str, ...]:
        """In the release's own order — the frame rule depends on it."""
        path = self.release / "seq_lists" / f"seq_list_{subject}.txt"
        names = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            token = line.split()[0] if line.split() else ""
            if "_" in token and not token.startswith("("):
                names.append(token)
        return tuple(names)

    def _archive(self, subject: str) -> Path:
        path = self.root / f"{subject}.zip"
        if not path.is_file():
            raise CapeError(f"{subject}.zip not downloaded under {self.root}")
        return path

    def _frames_in_archive(self, subject: str) -> dict[str, list[str]]:
        frames: dict[str, list[str]] = {}
        with zipfile.ZipFile(self._archive(subject)) as archive:
            for name in archive.namelist():
                parts = name.replace("\\", "/").split("/")
                if name.endswith(".npz") and len(parts) >= 3:
                    frames.setdefault(parts[-2], []).append(parts[-1])
        return {sequence: sorted(names) for sequence, names in frames.items()}

    def outfits(self, subject: str) -> dict[str, list[str]]:
        """outfit -> its sequences, in release order. The outfit is the
        first token of a sequence name, and it names the GARMENT, not the
        sleeve length: `jerseyshort` is long-sleeved (decision #34)."""
        available = self._frames_in_archive(subject)
        out: dict[str, list[str]] = {}
        for name in self.sequence_names(subject):
            if name in available:
                out.setdefault(name.split("_")[0], []).append(name)
        return out

    def first_valid_frame(self, subject: str, outfit: str) -> CapeFrame:
        """The frame rule, matching scripts/audit_cape_manifest.py: the
        first sequence of this outfit in release order, its lowest-numbered
        frame. One frame per outfit — consecutive frames of a sequence are
        nearly the same observation and would inflate N without adding a
        body."""
        sequences = self.outfits(subject).get(outfit)
        if not sequences:
            raise CapeError(f"{subject} has no outfit {outfit!r}")
        sequence = sequences[0]
        available = self._frames_in_archive(subject)[sequence]
        npz_name = min(available)
        with zipfile.ZipFile(self._archive(subject)) as archive:
            member = next(n for n in archive.namelist() if n.endswith(npz_name))
            with archive.open(member) as handle:
                payload = np.load(io.BytesIO(handle.read()), allow_pickle=True)
                v_cano = np.asarray(payload["v_cano"], dtype=np.float64)
        if v_cano.shape != (N_VERTICES, 3):
            raise CapeError(f"{subject}/{sequence}/{npz_name}: v_cano is "
                            f"{v_cano.shape}, expected ({N_VERTICES}, 3)")
        return CapeFrame(subject=subject, outfit=outfit, sequence=sequence,
                         npz_name=npz_name, v_cano_m=v_cano)


def displacement_T_m(frame: CapeFrame, body_T_m: np.ndarray) -> np.ndarray:
    """Clothing displacement in CAPE's canonical T pose, metres, (6890, 3).

    Both surfaces are SMPL topology, so they correspond per vertex and the
    difference is a per-vertex offset. The common translation is removed:
    CAPE stores the clothed frame about its own origin, and leaving that
    in would read as a whole-body offset rather than clothing."""
    if body_T_m.shape != frame.v_cano_m.shape:
        raise CapeError(f"shape mismatch: body {body_T_m.shape} vs frame "
                        f"{frame.v_cano_m.shape}")
    offset = frame.v_cano_m - body_T_m
    return offset - offset.mean(axis=0)
