"""Retrieval-based size estimation: scans as records, records as vectors,
a new scan sized by its nearest reference bodies.

This package is torch-free and stays so (tests/test_inference_isolation.py).
It never produces a measurement — the geometry pipeline does that — it
produces an ESTIMATE with its own pathway, `retrieved_neighbours`, and it
abstains when the query is far from every reference body it knows.
"""
