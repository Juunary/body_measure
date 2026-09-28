"""Locate the public measurement package without loading QR or web dependencies."""
from importlib.util import find_spec
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BODY = ROOT if (ROOT / 'body_measure').is_dir() else ROOT / 'body-measure'


def bootstrap():
    if (BODY / 'body_measure').is_dir():
        entry = str(BODY)
        if entry not in sys.path:
            sys.path.insert(0, entry)
        return
    # PyInstaller keeps pure Python modules in its embedded PYZ archive, so
    # the import is available even though there is no package directory next
    # to the installed executable.
    if find_spec('body_measure') is not None:
        return
    raise ImportError(f'Measurement package missing under {BODY}')


bootstrap()
