"""Locate the public measurement package without loading QR or web dependencies."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BODY = ROOT if (ROOT / 'body_measure').is_dir() else ROOT / 'body-measure'


def bootstrap():
    if not (BODY / 'body_measure').is_dir():
        raise ImportError(f'Measurement package missing under {BODY}')
    entry = str(BODY)
    if entry not in sys.path:
        sys.path.insert(0, entry)


bootstrap()
