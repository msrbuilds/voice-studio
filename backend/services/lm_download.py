"""Single-flight download of the ACE-Step 0.6B 5Hz LM into the checkpoints dir.

Unlike ModelDownloader (which fills the HF hub cache), the LM must land at
<models_dir>/acestep/acestep-5Hz-lm-0.6B/ in the ACE-Step checkpoints layout,
so we snapshot_download with local_dir.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

LM_REPO = "ACE-Step/acestep-5Hz-lm-0.6B"
LM_SUBDIR = "acestep-5Hz-lm-0.6B"


class _Progress:
    def __init__(self, dl: "LmDownloader") -> None:
        self._d = dl

    def set_total(self, n: int) -> None:
        with self._d._lock:
            self._d._total = int(n) if n and n > 0 else None

    def add_bytes(self, n: int) -> None:
        with self._d._lock:
            self._d._downloaded += int(n)

    def log(self, line: str) -> None:
        with self._d._lock:
            self._d._log.append(line)
            if len(self._d._log) > 500:
                del self._d._log[: len(self._d._log) - 500]


def _default_runner(repo_id: str, local_dir: Path, progress: "_Progress") -> None:
    from huggingface_hub import snapshot_download

    progress.log(f"Downloading {repo_id} -> {local_dir}")

    def _dir_bytes() -> int:
        try:
            return sum(f.stat().st_size for f in local_dir.rglob("*") if f.is_file())
        except OSError:
            return 0

    stop = threading.Event()
    last = _dir_bytes()

    def _poll() -> None:
        nonlocal last
        while not stop.is_set():
            stop.wait(0.5)
            cur = _dir_bytes()
            if cur > last:
                progress.add_bytes(cur - last)
                last = cur

    t = threading.Thread(target=_poll, daemon=True)
    t.start()
    try:
        snapshot_download(repo_id, local_dir=str(local_dir))
        progress.log("Download complete.")
    finally:
        stop.set()
        t.join(timeout=2.0)


Runner = Callable[[str, Path, "_Progress"], None]


class LmDownloader:
    """Thread-safe, single-flight download of the 0.6B LM with a progress snapshot."""

    def __init__(self, *, models_dir: Path, runner: Runner | None = None,
                 clock: Callable[[], float] | None = None) -> None:
        self._models_dir = Path(models_dir)
        self._runner = runner or _default_runner
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state = "idle"
        self._downloaded = 0
        self._total: int | None = None
        self._log: list[str] = []
        self._error: str | None = None

    def target_dir(self) -> Path:
        return self._models_dir / "acestep" / LM_SUBDIR

    def _snapshot_locked(self) -> dict:
        pct = None
        if self._total:
            pct = min(100.0, round(self._downloaded / self._total * 100.0, 1))
        return {
            "state": self._state, "percent": pct,
            "downloaded_bytes": self._downloaded, "total_bytes": self._total,
            "log": list(self._log[-20:]), "error": self._error,
        }

    def status(self) -> dict:
        with self._lock:
            return self._snapshot_locked()

    def start(self) -> dict:
        with self._lock:
            if self._state == "downloading":
                return self._snapshot_locked()
            self._state = "downloading"
            self._downloaded = 0
            self._total = None
            self._log = []
            self._error = None
            dest = self.target_dir()
            dest.mkdir(parents=True, exist_ok=True)
            self._thread = threading.Thread(target=self._run, args=(dest,), daemon=True)
            self._thread.start()
            return self._snapshot_locked()

    def _run(self, dest: Path) -> None:
        try:
            self._runner(LM_REPO, dest, _Progress(self))
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._error = str(exc)
                self._log.append(f"[lm download error] {exc}")
                self._state = "error"
            return
        with self._lock:
            self._state = "done"
