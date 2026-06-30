import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import create_app  # noqa: E402
from backend.services.update_check import UpdateChecker  # noqa: E402


def _client_with_fake_release(tag: str) -> TestClient:
    app = create_app()
    # Replace the real (network) checker with one using a stub fetcher.
    app.state.update_checker = UpdateChecker(
        current="0.2.0",
        fetcher=lambda: {
            "tag_name": tag,
            "html_url": f"https://github.com/msrbuilds/voice-studio/releases/tag/{tag}",
            "published_at": "2026-07-01T00:00:00Z",
            "body": "notes",
        },
    )
    return TestClient(app)


def test_get_update_reports_available():
    client = _client_with_fake_release("v0.9.0")
    data = client.get("/api/update?force=1").json()
    assert data["current"] == "0.2.0"
    assert data["latest"] == "0.9.0"
    assert data["update_available"] is True
    assert data["html_url"].endswith("/v0.9.0")


def test_get_update_run_status_starts_idle():
    client = _client_with_fake_release("v0.9.0")
    data = client.get("/api/update/run").json()
    assert data["state"] in ("idle", "running", "done", "error")
    assert isinstance(data["log"], list)
