"""Shared pytest fixtures for the backend test suite.

CRITICAL — cache isolation. Several tests build the app against the default
`Settings` and then synthesize into, and `DELETE /api/cache` (clear), the
synthesis cache. `Settings.cache_dir` defaults to the real `backend/cache/`,
so without this override those tests would wipe the user's saved generations
and leave stub entries behind. Forcing `CACHE_DIR` to a per-test tmp directory
makes the suite never touch real data.

`get_settings()` returns a fresh `Settings()` on each call (no caching), so the
env override is picked up by every `create_app()` / `Settings(...)` built during
the test. `monkeypatch.setenv` auto-reverts after each test.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_cache_dir(tmp_path, monkeypatch):
    """Point the synthesis cache at a throwaway per-test directory."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    yield
