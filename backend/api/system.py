"""GET /api/system/stats — live hardware + cache metrics for the status bar.

Read on each request (no background thread, no server-side cache): a 2s
single-user poll is cheap. Each metric is isolated so one failure (e.g. a
CUDA hiccup) never 500s the whole response.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import psutil
from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..services.synth_cache import SynthCache
from .deps import get_synth_cache
from .schemas import MemStat, SystemStatsResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])

# Warm up psutil's per-CPU delta so the first real reading isn't 0.0.
psutil.cpu_percent(interval=None)


def _existing_volume(path: Path) -> Path:
    """Nearest existing ancestor of `path` (its drive/mount always exists).

    `models_dir` may not be created yet on a fresh checkout, but disk_usage
    needs an existing path — walk up to the first parent that exists.
    """
    p = Path(path)
    for candidate in (p, *p.parents):
        if candidate.exists():
            return candidate
    return p.anchor and Path(p.anchor) or p


#: Lazily-initialized NVML handle. nvmlInit() is not free, and this endpoint is
#: polled every 2s, so initialize once and remember the failure too.
_NVML_STATE: dict[str, object] = {"tried": False, "handle": None}


def _nvml_memory() -> tuple[int, int] | None:
    """Device-wide (used, total) VRAM via NVML, or None if unavailable.

    NVML is the library nvidia-smi itself queries, so it sees every process on
    the GPU. `torch.cuda.mem_get_info()` does NOT on Windows/WDDM, where the OS
    virtualizes VRAM: measured 6862 MiB used per the driver against 1.18 GiB
    per mem_get_info on the same idle machine.
    """
    if not _NVML_STATE["tried"]:
        _NVML_STATE["tried"] = True
        try:
            import pynvml

            pynvml.nvmlInit()
            index = 0
            try:
                import torch

                if torch.cuda.is_available():
                    index = torch.cuda.current_device()
            except Exception:  # noqa: BLE001 — default to device 0
                pass
            _NVML_STATE["handle"] = pynvml.nvmlDeviceGetHandleByIndex(index)
        except Exception as exc:  # noqa: BLE001 — no NVIDIA GPU / no binding
            log.debug("NVML unavailable, falling back to torch: %s", exc)
            _NVML_STATE["handle"] = None

    handle = _NVML_STATE["handle"]
    if handle is None:
        return None

    import pynvml

    info = pynvml.nvmlDeviceGetMemoryInfo(handle)
    return int(info.used), int(info.total)


def _torch_memory() -> tuple[int, int] | None:
    """(used, total) VRAM via the CUDA runtime. Under-reports on WDDM."""
    import torch

    if not torch.cuda.is_available():
        return None
    free, total = torch.cuda.mem_get_info()
    return int(total - free), int(total)


def _vram() -> MemStat | None:
    """Device-wide VRAM. NVML first (accurate), CUDA runtime as a fallback."""
    for source in (_nvml_memory, _torch_memory):
        try:
            result = source()
        except Exception as exc:  # noqa: BLE001 — one bad source must not 500
            log.debug("VRAM source %s failed: %s", source.__name__, exc)
            continue
        if result is None:
            continue
        used, total = result
        pct = (used / total * 100.0) if total else 0.0
        return MemStat(used_bytes=used, total_bytes=total, percent=pct)
    return None


@router.get("/stats", response_model=SystemStatsResponse)
def system_stats(
    cache: SynthCache = Depends(get_synth_cache),
    settings: Settings = Depends(get_settings),
) -> SystemStatsResponse:
    vm = psutil.virtual_memory()
    ram = MemStat(used_bytes=vm.used, total_bytes=vm.total, percent=vm.percent)

    try:
        du = shutil.disk_usage(str(_existing_volume(settings.models_dir)))
        disk_pct = (du.used / du.total * 100.0) if du.total else 0.0
        disk = MemStat(used_bytes=du.used, total_bytes=du.total, percent=disk_pct)
    except OSError as exc:
        log.debug("Disk stats unavailable for %s: %s", settings.models_dir, exc)
        disk = MemStat(used_bytes=0, total_bytes=0, percent=0.0)

    try:
        cache_bytes = cache.total_size()
    except Exception as exc:  # noqa: BLE001
        log.debug("Cache size unavailable: %s", exc)
        cache_bytes = 0

    return SystemStatsResponse(
        cpu_percent=psutil.cpu_percent(interval=None),
        ram=ram,
        vram=_vram(),
        disk=disk,
        cache_bytes=cache_bytes,
    )
