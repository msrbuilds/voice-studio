"""Serializes every GPU consumer onto a single worker thread.

TTS synthesis (`SynthService`) and ASR transcription (`AsrService`) share one
GPU. Without a common gate, a transcription could run while a synthesis is
mid-generate and the two would fight over VRAM. Both services submit their
blocking model calls through `GpuGate.run`, which holds a lock for the whole
call and dispatches onto a single-worker executor.

The executor exists (rather than calling `fn` inline) so the work happens off
the request thread, matching the behaviour `SynthService` had when it owned a
private lock + executor.
"""

from __future__ import annotations

import concurrent.futures
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator


class GpuGate:
    """One lock + one worker thread for all GPU work."""

    def __init__(self, timeout_s: int) -> None:
        self._timeout_s = timeout_s
        self._lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="gpu"
        )

    @property
    def timeout_s(self) -> int:
        return self._timeout_s

    def run(self, fn: Callable[..., Any], *args: Any, timeout: float | None = None) -> Any:
        """Run `fn(*args)` exclusively; re-raises whatever `fn` raises.

        The lock is released even when `fn` blows up, so one failed job never
        wedges the gate for later callers.
        """
        with self._lock:
            future = self._executor.submit(fn, *args)
            return future.result(timeout=timeout or self._timeout_s)

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        """Hold the gate for the duration of a block.

        Needed by streaming synthesis, which yields from a generator and so
        must keep the GPU reserved across yields — something `run()` (a single
        submit+result) cannot express.
        """
        with self._lock:
            yield
