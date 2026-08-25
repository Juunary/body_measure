"""The measurement core must never import torch. This is the rule that
lets the core stay validated independently of whatever the inference
stack does, and it is cheap to check: import the core in a fresh
interpreter and look at sys.modules."""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CORE_MODULES = (
    "body_measure.spec",
    "body_measure.canonicalize",
    "body_measure.adapters.base",
    "body_measure.adapters.hsrd",
    "body_measure.measure.measurements",
    "body_measure.landmarks.estimated",
    "body_measure.validate.claims",
    "body_measure.validate.stats",
    "body_measure.cli",
)


def test_core_imports_do_not_load_torch():
    code = (
        "import importlib, sys\n"
        + "".join(f"importlib.import_module({m!r})\n" for m in CORE_MODULES)
        + "leaked = sorted(m for m in sys.modules if m.split('.')[0] in ('torch', 'smplx'))\n"
        "print('LEAK' if leaked else 'CLEAN', leaked[:5])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT_ROOT,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("CLEAN"), result.stdout


def test_core_source_never_names_the_inference_package():
    # a static guard alongside the runtime one: no core module may import
    # from body_measure.inference, whatever torch happens to be installed
    offenders = []
    for sub in ("adapters", "measure", "landmarks", "validate"):
        for path in (PROJECT_ROOT / "body_measure" / sub).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "body_measure.inference" in text or "from ..inference" in text or "from .inference" in text:
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
    for name in ("canonicalize.py", "spec.py", "result.py", "cli.py"):
        text = (PROJECT_ROOT / "body_measure" / name).read_text(encoding="utf-8")
        if "inference" in text and "import" in text.split("inference")[0][-40:]:
            offenders.append(name)
    assert offenders == []
