"""Tests for model-download cache detection, the ModelDownloader service,
and the /download API. Uses injected fakes — no network, no real weights."""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import huggingface_hub  # noqa: E402

from backend.core import model_cache  # noqa: E402


def test_model_downloaded_true_when_snapshot_resolves(monkeypatch):
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *a, **k: "/cache/x")
    assert model_cache.model_downloaded("org/repo") is True


def test_model_downloaded_false_when_snapshot_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("not cached")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", _boom)
    assert model_cache.model_downloaded("org/repo") is False


from backend.core.engines import Engine, EngineResult, EngineSynthRequest  # noqa: E402


class _StubEngine(Engine):
    """Minimal concrete Engine for exercising base-class behavior."""

    name = "stub"

    def __init__(self, downloaded=True):
        self._downloaded = downloaded

    def load(self): ...
    def unload(self): ...
    def is_loaded(self): return False
    def synthesize(self, req): raise NotImplementedError
    def sample_rate(self): return 24000
    def max_speakers(self): return 1
    def supports_voice_cloning(self): return False
    def default_cfg_scale(self): return None
    def available_voices(self): return []
    def downloaded(self): return self._downloaded


def test_engine_info_includes_downloaded_default_true():
    info = _StubEngine().info()
    assert info["downloaded"] is True


def test_engine_info_reflects_overridden_downloaded():
    assert _StubEngine(downloaded=False).info()["downloaded"] is False
