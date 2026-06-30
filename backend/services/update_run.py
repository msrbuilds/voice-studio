"""Background runner for `python studio.py update --tag <tag>`.

Mirrors services.chatterbox_install.EngineEnvInstaller but with the update
state vocabulary (idle -> running -> done | error) and a release tag passed to
the subprocess. The runner factory is injectable so tests don't run real git.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Iterator, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAX_LOG_LINES = 2000

RunnerItem = Tuple[Optional[str], Optional[int]]
RunnerFactory = Callable[[str], Iterator[RunnerItem]]


def _default_runner(repo_root: Path, tag: str) -> Iterator[RunnerItem]:
    """Spawn `python studio.py update --tag <tag>` and stream merged output."""
    proc = subprocess.Popen(
        [sys.executable, "studio.py", "update", "--tag", tag],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n"), None
    proc.wait()
    yield None, proc.returncode


class UpdateRunner:
    """Thread-safe single-flight runner for the update subprocess."""

    def __init__(
        self,
        *,
        runner_factory: RunnerFactory | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self._repo_root = repo_root or _REPO_ROOT
        self._runner_factory: RunnerFactory = runner_factory or (
            lambda tag: _default_runner(self._repo_root, tag)
        )
        self._lock = threading.Lock()
        self._state = "idle"
        self._log: list[str] = []
        self._returncode: int | None = None
        self._error: str | None = None
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "log": list(self._log),
                "returncode": self._returncode,
                "error": self._error,
            }

    def start(self, tag: str) -> dict:
        with self._lock:
            if self._state == "running":
                return {
                    "state": self._state,
                    "log": list(self._log),
                    "returncode": self._returncode,
                    "error": self._error,
                }
            self._state = "running"
            self._log = []
            self._returncode = None
            self._error = None
            self._thread = threading.Thread(target=self._run, args=(tag,), daemon=True)
            self._thread.start()
            return {"state": self._state, "log": [], "returncode": None, "error": None}

    def _run(self, tag: str) -> None:
        rc: int | None = None
        try:
            for line, code in self._runner_factory(tag):
                if line is not None:
                    with self._lock:
                        self._log.append(line)
                        if len(self._log) > _MAX_LOG_LINES:
                            del self._log[: len(self._log) - _MAX_LOG_LINES]
                if code is not None:
                    rc = code
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._log.append(f"[update error] {exc}")
                self._state = "error"
                self._returncode = -1
                self._error = str(exc)
            return
        with self._lock:
            self._returncode = rc
            self._state = "done" if rc == 0 else "error"
            if rc != 0:
                self._error = f"update exited with code {rc}"
