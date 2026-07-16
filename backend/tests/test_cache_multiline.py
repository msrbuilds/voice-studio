"""Single-voice synthesis must be cached even when the text spans lines.

Regression: `_build_script` turns each non-empty line into its own
`Speaker 1:` line, so any multi-line Text-to-Voice input produced >1 chunk and
fell into the multi-speaker branch, which hard-coded `cache_hash_for_write=None`.
The result was never cached — it never appeared in "Recent generations" and had
no hash to download. Single-line text cached fine, which is why this hid for so
long. Engine-agnostic: it bit OmniVoice and Kokoro alike.
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.tests.test_smoke import _make_client  # noqa: E402

MULTILINE = "First line of the paragraph.\nSecond line of the paragraph."
SINGLE = "Just one single line."


def _client(tmp_path):
    voices = tmp_path / "v"
    voices.mkdir(parents=True, exist_ok=True)
    sf.write(str(voices / "en-test.wav"), np.zeros(24000, dtype=np.float32), 24000,
             subtype="PCM_16")
    return _make_client(voices, tmp_path / "u")


def _synth(client, text, force=False):
    return client.post("/api/synthesize", json={
        "text": text,
        "speakers": [{"name": "Alice", "voice": "en-test"}],
        "force_regenerate": force,
    })


def test_single_line_is_cached(tmp_path):
    """Baseline: the path that always worked."""
    r = _synth(_client(tmp_path), SINGLE)
    assert r.status_code == 200
    assert r.headers.get("X-Cache-Hash"), "single-line synth produced no cache hash"


def test_multiline_single_voice_is_cached(tmp_path):
    """The bug: multi-line text produced no cache hash, so it was undownloadable."""
    r = _synth(_client(tmp_path), MULTILINE)
    assert r.status_code == 200
    assert r.headers.get("X-Cache-Hash"), (
        "multi-line single-voice synth produced no cache hash — it will not appear "
        "in Recent generations and cannot be downloaded"
    )


def test_multiline_second_call_hits_cache(tmp_path):
    client = _client(tmp_path)
    first = _synth(client, MULTILINE)
    assert first.headers.get("X-Cache") == "miss"
    second = _synth(client, MULTILINE)
    assert second.headers.get("X-Cache") == "hit", "multi-line synth never re-uses cache"
    assert second.headers["X-Cache-Hash"] == first.headers["X-Cache-Hash"]


def test_multiline_entry_is_listed_and_downloadable(tmp_path):
    """End-to-end of the user's symptom: it shows up and the audio is fetchable."""
    client = _client(tmp_path)
    h = _synth(client, MULTILINE).headers["X-Cache-Hash"]

    listed = {e["hash"] for e in client.get("/api/cache").json()["entries"]}
    assert h in listed, "multi-line generation missing from the cache listing"

    audio = client.get(f"/api/cache/{h}/audio")
    assert audio.status_code == 200
    assert audio.content[:4] == b"RIFF"


def test_multiline_and_single_line_do_not_collide(tmp_path):
    client = _client(tmp_path)
    a = _synth(client, MULTILINE).headers["X-Cache-Hash"]
    b = _synth(client, SINGLE).headers["X-Cache-Hash"]
    assert a != b


def test_force_regenerate_still_bypasses_cache(tmp_path):
    client = _client(tmp_path)
    _synth(client, MULTILINE)
    again = _synth(client, MULTILINE, force=True)
    assert again.headers.get("X-Cache") == "miss"
