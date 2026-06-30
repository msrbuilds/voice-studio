"""SynthCache must tolerate concurrent reads + writes.

The cache is read by the FastAPI threadpool (GET /api/cache every 15s, playback)
while synthesis writes/evicts on the executor thread. Two guarantees:

- `list()`/`get()` must not crash when a concurrent `put`/evict mutates the
  index (no "dictionary changed size during iteration").
- A reader must never observe a truncated/0-byte WAV mid-write: writes must be
  atomic (temp file + os.replace), so a concurrent reader sees either the old
  complete file or the new complete file.
"""

import os
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.services.synth_cache import SynthCache  # noqa: E402


def test_overwrite_is_atomic_no_partial_reads(tmp_path):
    """Overwriting an entry must never expose a partial/0-byte file."""
    cache = SynthCache(tmp_path, max_entries=500)
    payload = b"RIFF" + b"\x00" * (2 * 1024 * 1024)  # ~2 MB so writes take time
    full = len(payload)
    h = "atomic" + "0" * 18
    cache.put(h, payload, 24000, 1.0, 5, text="t", voice="v")
    wav = tmp_path / f"{h}.wav"

    bad_sizes: list[int] = []
    errors: list[Exception] = []
    stop = threading.Event()

    def writer() -> None:
        while not stop.is_set():
            try:
                cache.put(h, payload, 24000, 1.0, 5, text="t", voice="v")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    def reader() -> None:
        while not stop.is_set():
            try:
                size = os.path.getsize(wav)
            except OSError:
                continue  # brief absence is acceptable; truncation is not
            if size != full:
                bad_sizes.append(size)

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=reader) for _ in range(3)
    ]
    for t in threads:
        t.start()
    time.sleep(0.8)
    stop.set()
    for t in threads:
        t.join()

    assert not bad_sizes, f"reader saw {len(bad_sizes)} partial sizes, e.g. {bad_sizes[:5]}"
    assert not errors, f"writer raised {len(errors)} errors, e.g. {errors[0]!r}"


def test_concurrent_put_list_get_no_crash(tmp_path):
    """Concurrent put/evict + list/get must not raise."""
    cache = SynthCache(tmp_path, max_entries=8)
    errors: list[Exception] = []
    stop = threading.Event()

    def writer() -> None:
        i = 0
        while not stop.is_set():
            i += 1
            try:
                cache.put(f"hash{i % 40:020d}", b"RIFF\x00\x00\x00\x00", 24000, 1.0, 5)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    def reader() -> None:
        while not stop.is_set():
            try:
                for e in cache.list():
                    cache.get(e.hash)
                len(cache)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [
        threading.Thread(target=writer),
        threading.Thread(target=writer),
        threading.Thread(target=reader),
        threading.Thread(target=reader),
    ]
    for t in threads:
        t.start()
    time.sleep(0.6)
    stop.set()
    for t in threads:
        t.join()

    assert not errors, f"concurrency raised {len(errors)} errors, e.g. {errors[0]!r}"
