"""Guard: the test suite must never operate on the real synthesis cache.

Several tests (test_smoke, test_e2e) build the app against the default
`Settings` and then synthesize into — and `DELETE /api/cache` (clear) — the
cache. Without isolation those run against the real `backend/cache/` directory
and wipe the user's saved generations. `conftest.py` forces `CACHE_DIR` to a
per-test tmp dir; this test fails loudly if that protection regresses.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.config import BACKEND_ROOT, Settings  # noqa: E402


def test_cache_dir_isolated_from_real_dir():
    real = (BACKEND_ROOT / "cache").resolve()
    assert Settings().cache_dir.resolve() != real, (
        "Settings().cache_dir points at the REAL backend/cache — tests would "
        "wipe the user's generations. conftest.py must override CACHE_DIR."
    )
