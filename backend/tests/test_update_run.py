import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.services.update_run import UpdateRunner  # noqa: E402


def _wait(runner, state, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end:
        if runner.status()["state"] == state:
            return
        time.sleep(0.01)
    raise AssertionError(f"runner never reached {state}: {runner.status()}")


def test_runner_success_streams_log_and_finishes():
    seen = {}

    def runner_fn(tag):
        seen["tag"] = tag
        yield "line one", None
        yield "line two", None
        yield None, 0

    r = UpdateRunner(runner_factory=lambda tag: runner_fn(tag))
    started = r.start("v0.3.0")
    assert started["state"] == "running"
    _wait(r, "done")
    s = r.status()
    assert s["returncode"] == 0
    assert "line one" in s["log"] and "line two" in s["log"]
    assert seen["tag"] == "v0.3.0"


def test_runner_nonzero_is_error():
    def runner_fn(tag):
        yield "boom", None
        yield None, 1

    r = UpdateRunner(runner_factory=lambda tag: runner_fn(tag))
    r.start("v0.3.0")
    _wait(r, "error")
    assert r.status()["returncode"] == 1


def test_runner_coalesces_concurrent_starts():
    def runner_fn(tag):
        time.sleep(0.2)
        yield None, 0

    r = UpdateRunner(runner_factory=lambda tag: runner_fn(tag))
    first = r.start("v0.3.0")
    second = r.start("v0.3.0")  # should NOT launch a second job
    assert first["state"] == "running"
    assert second["state"] == "running"
    _wait(r, "done", timeout=2.0)
