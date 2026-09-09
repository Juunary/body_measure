"""Studio — one page from a 3D scan to a passport.

The three Maß-DPP pieces stay where they are: body-measure measures, the
polo line replays, qr-configurator encodes. This package only calls them
in order and streams what they say. It is deliberately thin; anything
that sounds like a measurement, a size rule or a QR detail lives in the
project that owns it (see `paths.py` for how they are found).
"""
__version__ = "0.1.0"
