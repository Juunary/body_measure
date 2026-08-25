"""Export the C2 battery's meshes to OBJ so they can be opened and looked at.

The battery itself keeps nothing on disk but numbers: shells are built in
memory and recovered bodies survive only as betas in
`reports/c2_synthetic_battery.json`. That is fine for scoring and useless
for looking, so this script rebuilds them from the recorded betas and
writes them out.

Everything lands in `data/generated/c2_meshes/`, which is gitignored —
these are SMPL derivatives and are not redistributable
(docs/licenses/README.md).

Run (PowerShell):
  $env:PYTHONUTF8=1; .venv\\Scripts\\python scripts\\export_c2_meshes.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from body_measure.inference.shells import build_battery  # noqa: E402
from body_measure.inference.smpl_body import SmplBody  # noqa: E402

REPORT = PROJECT_ROOT / "reports" / "c2_synthetic_battery.json"
OUT = PROJECT_ROOT / "data" / "generated" / "c2_meshes"


def main() -> int:
    if not REPORT.exists():
        print(f"no battery report at {REPORT} — run scripts/c2_synthetic_battery.py first",
              file=sys.stderr)
        return 1

    report = json.loads(REPORT.read_text(encoding="utf-8"))
    body = SmplBody()
    OUT.mkdir(parents=True, exist_ok=True)

    written: list[tuple[str, int]] = []

    def dump(name: str, mesh) -> None:
        path = OUT / f"{name}.obj"
        mesh.export(path)
        written.append((path.name, len(mesh.faces)))

    # the body every shell was built around, and every recovery is scored against
    latent_betas = np.array(report["latent"]["betas"])
    latent = body.canonical_mesh(latent_betas, source_id="latent")
    dump("00_latent_body", latent)

    # the shells: rebuilt with the same seed the battery used
    cases = {c.name: c for c in build_battery(latent, body.part_of_vertex, report["seed"])}
    for entry in report["cases"]:
        case = cases.get(entry["case"])
        if case is not None:
            dump(f"shell_{entry['case']}", case.mesh)
        recovered = body.canonical_mesh(
            np.array(entry["fit"]["params"]["betas"]), source_id=f"recovered/{entry['case']}"
        )
        dump(f"recovered_{entry['case']}", recovered)

    for filename, faces in written:
        print(f"  {filename:44s} {faces:7d} faces")
    print(f"\n{len(written)} files in {OUT.relative_to(PROJECT_ROOT)}")
    print("compare pairs: shell_<case>.obj is the input, recovered_<case>.obj is what")
    print("the fit produced, 00_latent_body.obj is the answer both are scored against.")
    print("All are millimetres, Y-up, floor at y=0, canonical A-pose (shells excepted:")
    print("they follow their latent body's pose by construction).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
