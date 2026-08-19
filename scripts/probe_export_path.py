"""Prove the inference EXPORT path works before any architecture is chosen.

torch 2.13 deprecates TorchScript in favour of torch.export, and
torch.export needs a whole tensor graph — dynamic kNN and Python control
flow (exactly what point-cloud encoders like DGCNN are built from) can
fail to export. Finding that out after training would be expensive, so
this probe runs first with a throwaway model.

What it reports per point count: export success, ONNX Runtime CPU output
parity against eager, dynamic-batch handling, p50/p95 latency, peak RSS.

Run:  .venv\\Scripts\\python scripts\\probe_export_path.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT = PROJECT_ROOT / "reports" / "export_probe.json"

POINT_COUNTS = (4096, 8192)
LATENCY_RUNS = 20
NUM_BETAS = 10
SEED = 20260817


class DynamicKnnEncoder(nn.Module):
    """A deliberately export-HOSTILE stand-in: it does the runtime kNN
    graph construction that DGCNN-class encoders rely on. If this exports,
    a real encoder almost certainly will; if it does not, we learn the
    constraint now rather than after a GPU training run."""

    def __init__(self, k: int = 16, width: int = 64, num_betas: int = NUM_BETAS):
        super().__init__()
        self.k = k
        self.edge = nn.Sequential(
            nn.Linear(6, width), nn.ReLU(), nn.Linear(width, width), nn.ReLU()
        )
        self.head = nn.Sequential(
            nn.Linear(width, width), nn.ReLU(), nn.Linear(width, num_betas)
        )

    def forward(self, points: torch.Tensor) -> torch.Tensor:  # (B, N, 3)
        dist = torch.cdist(points, points)                     # (B, N, N)
        idx = dist.topk(self.k, dim=-1, largest=False).indices  # (B, N, k)
        neighbours = torch.gather(
            points.unsqueeze(2).expand(-1, -1, points.shape[1], -1),
            2,
            idx.unsqueeze(-1).expand(-1, -1, -1, 3),
        )                                                       # (B, N, k, 3)
        centre = points.unsqueeze(2).expand_as(neighbours)
        feat = self.edge(torch.cat([centre, neighbours - centre], dim=-1))
        return self.head(feat.amax(dim=2).amax(dim=1))          # (B, num_betas)


def peak_rss_mb() -> float | None:
    try:  # Windows
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        ):
            return None
        return round(counters.PeakWorkingSetSize / 1e6, 1)
    except Exception:
        return None


def probe(n_points: int) -> dict:
    torch.manual_seed(SEED)
    model = DynamicKnnEncoder().eval()
    # Export with batch=2, not 1: torch.export specialises a dynamic dim it
    # only ever sees as 1, and then refuses the constraint. Learned here so
    # the real exporter never trips on it.
    sample = torch.randn(2, n_points, 3)
    result: dict = {"n_points": n_points, "example_batch": int(sample.shape[0])}

    with torch.no_grad():
        t0 = time.perf_counter()
        eager = model(sample)
        result["eager_first_call_s"] = round(time.perf_counter() - t0, 3)

        times = []
        for _ in range(LATENCY_RUNS):
            t = time.perf_counter()
            model(sample)
            times.append(time.perf_counter() - t)
    result["eager_p50_s"] = round(statistics.median(times), 3)
    result["eager_p95_s"] = round(sorted(times)[int(0.95 * (len(times) - 1))], 3)

    # --- torch.export (primary path) --------------------------------------
    onnx_path = PROJECT_ROOT / "reports" / f"export_probe_{n_points}.onnx"
    try:
        batch = torch.export.Dim("batch", min=1, max=8)
        exported = torch.export.export(
            model, (sample,), dynamic_shapes={"points": {0: batch}}
        )
        result["torch_export"] = "ok"
    except Exception as exc:
        exported = None
        result["torch_export"] = f"FAILED: {type(exc).__name__}: {str(exc)[:180]}"

    # --- ONNX + CPU runtime parity ---------------------------------------
    try:
        torch.onnx.export(
            model, (sample,), str(onnx_path),
            input_names=["points"], output_names=["betas"],
            dynamic_axes={"points": {0: "batch"}, "betas": {0: "batch"}},
            opset_version=17,
        )
        result["onnx_export"] = "ok"
    except Exception as exc:
        result["onnx_export"] = f"FAILED: {type(exc).__name__}: {str(exc)[:180]}"
        onnx_path = None

    if onnx_path is not None and onnx_path.exists():
        try:
            import onnxruntime as ort

            session = ort.InferenceSession(
                str(onnx_path), providers=["CPUExecutionProvider"]
            )
            got = session.run(["betas"], {"points": sample.numpy()})[0]
            result["onnx_cpu_parity_max_abs_diff"] = float(
                np.abs(got - eager.numpy()).max()
            )
            # dynamic batch: the exported graph must accept a batch size it
            # was never traced with (here 3, having been exported at 2)
            other = torch.randn(3, n_points, 3).numpy()
            result["onnx_dynamic_batch"] = (
                "ok" if session.run(["betas"], {"points": other})[0].shape[0] == 3
                else "wrong shape"
            )
            rt = []
            for _ in range(LATENCY_RUNS):
                t = time.perf_counter()
                session.run(["betas"], {"points": sample.numpy()})
                rt.append(time.perf_counter() - t)
            result["onnx_p50_s"] = round(statistics.median(rt), 3)
            result["onnx_p95_s"] = round(sorted(rt)[int(0.95 * (len(rt) - 1))], 3)
        except ImportError:
            result["onnx_runtime"] = "onnxruntime not installed — parity unverified"
        except Exception as exc:
            result["onnx_runtime"] = f"FAILED: {type(exc).__name__}: {str(exc)[:180]}"

    result["peak_rss_mb"] = peak_rss_mb()
    return result


def main() -> int:
    OUT.parent.mkdir(exist_ok=True)
    results = {
        "torch_version": torch.__version__,
        "note": (
            "Throwaway dynamic-kNN model. Purpose is to prove the export path, "
            "not to propose an architecture. peak_rss_mb is dominated by this "
            "probe's O(N^2) cdist and is NOT a budget for a real encoder — it "
            "is the cost of the pattern a real encoder must avoid."
        ),
        "environment_requirements": [
            "export with batch >= 2: torch.export specialises a dim it only "
            "sees as 1 and then refuses the dynamic constraint",
            "onnxscript must be installed for torch.onnx.export",
            "PYTHONUTF8=1 on a cp949 console: the exporter's progress output "
            "contains non-cp949 characters and crashes the run otherwise",
        ],
        "probes": [probe(n) for n in POINT_COUNTS],
    }
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
