"""Public tests live outside tests/, whose fixtures intentionally load QR."""
from pathlib import Path
import sys

STUDIO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STUDIO))
