import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.services.update_check import (  # noqa: E402
    UpdateChecker,
    build_snapshot,
    is_newer,
)


def test_is_newer_basic():
    assert is_newer("0.3.0", "0.2.0") is True
    assert is_newer("v0.3.0", "0.2.0") is True
    assert is_newer("0.2.0", "0.2.0") is False
    assert is_newer("0.1.0", "0.2.0") is False


def test_is_newer_prerelease_and_garbage():
    # A pre-release ranks below the same X.Y.Z release.
    assert is_newer("0.3.0-rc1", "0.2.0") is True
    assert is_newer("0.2.0-rc1", "0.2.0") is False
    # Malformed input is never "newer" (fail safe).
    assert is_newer("garbage", "0.2.0") is False
    assert is_newer("0.3.0", "nonsense") is False


def test_build_snapshot_update_available():
    payload = {
        "tag_name": "v0.3.0",
        "html_url": "https://github.com/msrbuilds/voice-studio/releases/tag/v0.3.0",
        "published_at": "2026-07-01T00:00:00Z",
        "body": "Release notes here",
    }
    snap = build_snapshot(payload, current="0.2.0", checked_at=123.0)
    assert snap["current"] == "0.2.0"
    assert snap["latest"] == "0.3.0"
    assert snap["update_available"] is True
    assert snap["html_url"].endswith("/v0.3.0")
    assert snap["body"] == "Release notes here"
    assert snap["checked_at"] == 123.0
    assert snap["error"] is None


def test_build_snapshot_error_is_safe():
    snap = build_snapshot(None, current="0.2.0", checked_at=1.0, error="boom")
    assert snap["update_available"] is False
    assert snap["latest"] is None
    assert snap["error"] == "boom"


def test_checker_uses_injected_fetcher_and_caches():
    calls = {"n": 0}

    def fetcher():
        calls["n"] += 1
        return {"tag_name": "v0.9.0", "html_url": "u", "published_at": "p", "body": "b"}

    chk = UpdateChecker(current="0.2.0", fetcher=fetcher)
    first = chk.check()
    assert first["update_available"] is True
    assert first["latest"] == "0.9.0"
    # Second call is served from cache (no extra fetch).
    chk.check()
    assert calls["n"] == 1
    # force=True re-fetches.
    chk.check(force=True)
    assert calls["n"] == 2


def test_checker_swallows_fetch_errors():
    def fetcher():
        raise RuntimeError("network down")

    chk = UpdateChecker(current="0.2.0", fetcher=fetcher)
    snap = chk.check()
    assert snap["update_available"] is False
    assert snap["error"] is not None
    # snapshot() returns the last result without crashing.
    assert chk.snapshot()["current"] == "0.2.0"
