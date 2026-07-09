"""VRAM reporting must be device-wide, not just this process.

`torch.cuda.mem_get_info()` under-reports on Windows/WDDM, where the OS
virtualizes VRAM and the CUDA runtime can't see other processes' allocations
(measured: driver 6862 MiB used vs mem_get_info 1.18 GiB). NVML is what
nvidia-smi itself queries, so we prefer it and fall back to torch.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import backend.api.system as sysmod  # noqa: E402


class _FakeMem:
    def __init__(self, used, total):
        self.used, self.total = used, total


def _reset_nvml_cache():
    sysmod._NVML_STATE["tried"] = False
    sysmod._NVML_STATE["handle"] = None


def test_vram_prefers_nvml(monkeypatch):
    _reset_nvml_cache()
    monkeypatch.setattr(sysmod, "_nvml_memory", lambda: (7 * 2**30, 12 * 2**30))
    # torch would report a much smaller number; NVML must win.
    monkeypatch.setattr(sysmod, "_torch_memory", lambda: (1 * 2**30, 12 * 2**30))

    v = sysmod._vram()
    assert v is not None
    assert v.used_bytes == 7 * 2**30
    assert v.total_bytes == 12 * 2**30
    assert round(v.percent, 1) == 58.3


def test_vram_falls_back_to_torch_when_nvml_unavailable(monkeypatch):
    _reset_nvml_cache()
    monkeypatch.setattr(sysmod, "_nvml_memory", lambda: None)
    monkeypatch.setattr(sysmod, "_torch_memory", lambda: (2 * 2**30, 8 * 2**30))

    v = sysmod._vram()
    assert v is not None
    assert v.used_bytes == 2 * 2**30
    assert v.percent == 25.0


def test_vram_none_without_any_gpu(monkeypatch):
    _reset_nvml_cache()
    monkeypatch.setattr(sysmod, "_nvml_memory", lambda: None)
    monkeypatch.setattr(sysmod, "_torch_memory", lambda: None)
    assert sysmod._vram() is None


def test_vram_survives_nvml_raising(monkeypatch):
    """A broken NVML must never 500 the status endpoint."""
    _reset_nvml_cache()

    def boom():
        raise RuntimeError("nvml exploded")

    monkeypatch.setattr(sysmod, "_nvml_memory", boom)
    monkeypatch.setattr(sysmod, "_torch_memory", lambda: (1, 4))
    v = sysmod._vram()
    assert v is not None and v.used_bytes == 1


def test_vram_zero_total_does_not_divide_by_zero(monkeypatch):
    _reset_nvml_cache()
    monkeypatch.setattr(sysmod, "_nvml_memory", lambda: (0, 0))
    v = sysmod._vram()
    assert v is not None and v.percent == 0.0
