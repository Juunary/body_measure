"""The real unclothed scans on this workstation, as (subject, population,
canonical mesh). The same subjects and the same population rule as
scripts/size_report.py. Every record built from these is
`local_only_licensed`: Texel is CC BY-NC and NOMO forbids redistribution."""
from __future__ import annotations

from collections.abc import Iterator

from ..canonicalize import canonicalize
from .versioning import PROJECT_ROOT

TEXEL_ROOT = PROJECT_ROOT / "data" / "external" / "texel"
NOMO_ROOT = (PROJECT_ROOT / "data" / "external" / "nomo"
             / "NOMO-3d-400-scans_and_tc2_measurements" / "extracted")


def texel_subjects() -> Iterator[tuple[str, str, object]]:
    from ..adapters.texel import TexelAdapter

    if not TEXEL_ROOT.is_dir():
        return
    adapter = TexelAdapter()
    for path in sorted(adapter.persons(TEXEL_ROOT)):
        population = "women" if path.name.lower().startswith("woman") else "men"
        yield f"texel/{path.name}", population, canonicalize(adapter.load(path))


def nomo_subjects(limit: int) -> Iterator[tuple[str, str, object]]:
    from ..adapters.nomo import NomoAdapter

    if not NOMO_ROOT.is_dir() or limit <= 0:
        return
    adapter = NomoAdapter(NOMO_ROOT)
    for subject in adapter.subjects()[:limit]:
        # the extracted NOMO set is the male half (docs/datasets.md)
        yield f"nomo/{subject}", "men", canonicalize(adapter.load(subject))


def real_subjects(nomo_limit: int = 30) -> Iterator[tuple[str, str, object]]:
    yield from texel_subjects()
    yield from nomo_subjects(nomo_limit)
