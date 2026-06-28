"""Tests for the non-blocking startup engine warm-up helpers in app.py."""

import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.app import _start_background_warmup, _warmup_active_engine  # noqa: E402


class _FakeEngine:
    """Minimal engine stub used by fake EMs."""

    def __init__(self, downloaded: bool = True) -> None:
        self._downloaded = downloaded

    def downloaded(self) -> bool:
        return self._downloaded


class _BlockingEM:
    """Fake EngineManager whose ensure_active_loaded blocks until an Event."""

    def __init__(self):
        self._event = threading.Event()
        self.call_count = 0
        self.active_engine = _FakeEngine(downloaded=True)

    def ensure_active_loaded(self):
        self.call_count += 1
        self._event.wait()

    def release(self):
        self._event.set()


class _RaisingEM:
    """Fake EngineManager whose ensure_active_loaded always raises."""

    def __init__(self):
        self.active_engine = _FakeEngine(downloaded=True)

    def ensure_active_loaded(self):
        raise RuntimeError("simulated load failure")


class _CountingEM:
    """Fake EngineManager that counts ensure_active_loaded calls."""

    def __init__(self, downloaded: bool = True):
        self.call_count = 0
        self.active_engine = _FakeEngine(downloaded=downloaded)

    def ensure_active_loaded(self):
        self.call_count += 1


def test_start_background_warmup_returns_promptly():
    """_start_background_warmup returns while the warm-up thread is still alive."""
    em = _BlockingEM()
    thread = _start_background_warmup(em)

    # Thread started but its ensure_active_loaded is still blocking
    assert thread.is_alive() is True

    # Release the block; thread should complete
    em.release()
    thread.join(timeout=5.0)
    assert thread.is_alive() is False
    assert em.call_count == 1


def test_warmup_swallows_exception():
    """_warmup_active_engine swallows load failures without propagating."""
    # Must not raise
    _warmup_active_engine(_RaisingEM())


def test_warmup_calls_ensure_active_loaded_once():
    """_warmup_active_engine calls ensure_active_loaded exactly once."""
    em = _CountingEM(downloaded=True)
    _warmup_active_engine(em)
    assert em.call_count == 1


def test_warmup_skips_when_not_downloaded():
    """_warmup_active_engine skips load when the engine weights are not cached."""
    em = _CountingEM(downloaded=False)
    _warmup_active_engine(em)
    assert em.call_count == 0
