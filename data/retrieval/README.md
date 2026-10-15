# data/retrieval — retrieval stores

Each subdirectory is one store (`body_measure/retrieval/store.py`):

| file | what |
|---|---|
| `records.jsonl` | one `ScanRecord` per line; authoritative |
| `features.npz` | standardised feature matrix, mask, betas, ids; rebuilt from the records |
| `manifest.json` | feature space, spec and pipeline hashes, counts per licence class and split |
| `calibration.json` | abstention threshold and kernel width, tied to the records' hash |

Nothing here is committed. A store can hold records derived from licensed
scans (`local_only_licensed`: Texel, NOMO, CAPE), and those never leave
this workstation. `python -m body_measure index export` and
`scripts/export_training_set.py` refuse a store that holds even one.

Build and use:

```powershell
$env:PYTHONUTF8=1
.venv\Scripts\python scripts\build_synthetic_db.py --db syn-neutral --n 10000 --workers 6
.venv\Scripts\python -m body_measure index build --db real-local --source real
.venv\Scripts\python -m body_measure index merge --db studio --from syn-neutral real-local
.venv\Scripts\python -m body_measure index calibrate --db studio
.venv\Scripts\python -m body_measure index query --db studio scan.ply --input-unit mm --population men
```
