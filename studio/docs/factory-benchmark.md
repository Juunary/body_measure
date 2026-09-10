# Factory phase 1 — measured benchmark and equivalence

Synthetic research simulation; no actual manufactured-product claim.

Environment: Windows-11-10.0.26200-SP0; Intel64 Family 6 Model 189 Stepping 1, GenuineIntel; Python 3.12.10.
Dependencies: simpy 4.1.2, numpy 2.5.3, shapely 2.1.2, pydantic 2.13.5.

The workload is 1,000 identical polos: 2 cutters / 1 cutting worker, 4 Pfaff / 4 sewing workers,
1 transport worker / cart, batches of 5, sewing buffer capacity 10. Geometry is compiled once.
The 1,000 queries select one garment plus the whole-factory summary at random timestamps after 50 warmups.

| Measurement | Observed |
| --- | --- |
| Compute run | 2.933 s |
| Save / load and verify | 1.477 / 0.829 s |
| Domain events / segments including waits | 22401 / 15200 |
| Checkpoints | 88 |
| Artifact | 25.65 MiB |
| Peak process resident memory | 199.66 MiB |
| Query p50 / p95 / max | 0.342 / 0.731 / 3.791 ms |
| Max replayed events after checkpoint | 255 |
| p95 < 50 ms | PASS |

Memory is the OS high-water mark for the entire process, including scientific-library imports and JSON serialization.
This verifies Python state-query latency, not browser rendering, SSE throughput or concurrent web clients.

## One garment, no waiting

Geometry, detailed operation order/times, piece recovery, seams and stitches are tested against the existing engine.
The only accounting change removes Pfaff standby power and equipment occupancy during transport.
Common power still spans the same uninterrupted work interval for this one-garment case.

| Quantity | Legacy | Factory | Actual delta | Expected delta |
| --- | ---: | ---: | ---: | ---: |
| duration_s | 516.192421454 | 516.192421454 | 0 | 0 |
| energy_kwh | 0.145481884648 | 0.145426329093 | -5.55555555556e-05 | -5.55555555556e-05 |
| co2e_g | 55.2831161664 | 55.2620050553 | -0.0211111111111 | -0.0211111111111 |
| cost_eur | 9.749953242 | 9.74855046423 | -0.00140277777778 | -0.00140277777778 |
| labour_time_s | 366.4 | 366.4 | 0 | 0 |
| thread_used_m | 15.254619064 | 15.254619064 | 0 | 0 |

Tolerance: relative 1e-9, absolute 1e-6. Differences are calculations, not fitted corrections.

Source SHA-256: `59dfe6957847bafdd52df84bd25536c37ce14ffe9ced4d483154d09021cfe702`
Deterministic run content hash: `e8a8f807333922b88e82e19065ac11a337efcf9246fa1d3a58cf1211d8fdedb4`

Reproduce from `studio`:

```powershell
python -m pytest factory_tests -q
python -m studio.factory.benchmark --out runs/factory-benchmark.json --report runs/factory-benchmark.md
```
