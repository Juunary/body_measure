"""Find the integrated projects and put them on ``sys.path`` in the
right order, because two of them collide.

The canonical GitHub checkout now has this layout::

    body_measure/
      body_measure/           package ``body_measure``
      polo-line-sim/          package `polo_line`      (the original, with passport.py)
      qr-configurator/backend package `app` ... and a vendored `polo_line` copy
                              WITHOUT passport.py
      studio/                 this program, package `studio`

The earlier ITA workspace kept ``body-measure`` beside the other three
directories.  That layout remains supported so existing local jobs keep
working while the GitHub repository becomes the canonical checkout.

Two name collisions, both settled here:

* `app` is qr-configurator's package name. This program is therefore
  `studio`, never `app`, and it imports only the pure modules —
  `app.codec`, `app.schemas`, `app.validation`, `app.qrfixed`,
  `app.passport`, `app.access`. `app.main`, `app.simbridge` and
  `app.mfgstore` are never imported: they pull in SQLite and the vendored
  `polo_line`.
* `polo_line` exists twice. polo-line-sim goes on the path LAST-inserted,
  i.e. first searched, so the original wins; an assertion below turns a
  wrong resolution into an ImportError with the fix in the message rather
  than a passport with no `passport.py`.

Import this module before anything else from the siblings.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BODY = ROOT if (ROOT / "body_measure").is_dir() else ROOT / "body-measure"
POLO = ROOT / "polo-line-sim"
QRBACK = ROOT / "qr-configurator" / "backend"

STUDIO_ROOT = Path(__file__).resolve().parents[1]
#: uploads and per-job results outlive a container only on a mounted
#: volume; STUDIO_STATE_DIR points there (fly.toml mounts /data)
_STATE = Path(os.environ["STUDIO_STATE_DIR"]) if os.environ.get("STUDIO_STATE_DIR") else STUDIO_ROOT
UPLOADS = _STATE / "uploads"
RUNS = _STATE / "runs"
STATIC = STUDIO_ROOT / "static"

_FORBIDDEN = ("app.main", "app.simbridge", "app.mfgstore")


def bootstrap() -> None:
    """Idempotent. Inserts QRBACK, then BODY, then POLO at index 0 — so the
    search order is POLO, BODY, QRBACK."""
    for project in (QRBACK, BODY, POLO):
        if not project.is_dir():
            raise ImportError(f"sibling project missing: {project}")
        entry = str(project)
        if entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(0, entry)


def verify() -> dict:
    """Import the siblings and check each resolved to the intended tree."""
    import app.codec  # noqa: F401
    import body_measure  # noqa: F401
    import polo_line.passport  # noqa: F401

    resolved = {
        "polo_line": Path(sys.modules["polo_line"].__file__).resolve(),
        "body_measure": Path(sys.modules["body_measure"].__file__).resolve(),
        "app": Path(sys.modules["app"].__file__).resolve(),
    }
    checks = {"polo_line": POLO, "body_measure": BODY, "app": QRBACK}
    for name, expected in checks.items():
        if expected.resolve() not in resolved[name].parents:
            raise ImportError(
                f"{name} resolved to {resolved[name]}, expected a module under "
                f"{expected}. Another copy shadows it on sys.path; the studio must "
                f"be launched from its own directory with `studio.paths` imported first.")
    for name in _FORBIDDEN:
        if name in sys.modules:
            raise ImportError(f"{name} was imported; the studio must never load it")
    return {k: str(v) for k, v in resolved.items()}


bootstrap()
