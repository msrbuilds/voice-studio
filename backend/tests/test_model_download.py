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
