"""POST /api/voices/{voice_id}/transcribe — auto-fill reference_transcript.

Uses a stub AsrEngine so the suite never loads Whisper's weights.
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.tests.test_smoke import _make_client  # noqa: E402


class _StubAsr:
    _model_id = "openai/whisper-large-v3-turbo"

    def is_loaded(self):
        return True

    def load(self):
        pass

    def downloaded(self):
        return True

    def sample_rate(self):
        return 16000

    def languages(self):
        return [{"code": "en", "label": "English"}]

    def transcribe(self, req):
        from backend.core.asr import AsrResult

        return AsrResult(
            text="this is the reference clip",
            language="en", duration_sec=1.0, inference_ms=3, segments=[],
        )


def _client(tmp_path):
    voices = tmp_path / "v"
    uploads = tmp_path / "u"
    voices.mkdir(parents=True, exist_ok=True)
    uploads.mkdir(parents=True, exist_ok=True)
    sf.write(voices / "speaker1.wav", np.zeros(16000, dtype=np.float32), 16000)
    client = _make_client(voices, uploads)
    client.app.state.asr_service._engine = _StubAsr()
    return client


def test_transcribe_voice_returns_text(tmp_path):
    client = _client(tmp_path)
    r = client.post("/api/voices/speaker1/transcribe")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "this is the reference clip"
    assert body["language"] == "en"


def test_transcribe_voice_honours_language_override(tmp_path):
    client = _client(tmp_path)
    r = client.post("/api/voices/speaker1/transcribe", json={"language": "ur"})
    assert r.status_code == 200, r.text


def test_transcribe_unknown_voice_is_404(tmp_path):
    client = _client(tmp_path)
    assert client.post("/api/voices/nope/transcribe").status_code == 404


def test_transcribe_voice_does_not_persist_by_itself(tmp_path):
    """The user reviews the text before saving; the route must not write it."""
    client = _client(tmp_path)
    client.post("/api/voices/speaker1/transcribe")
    voices = {v["id"]: v for v in client.get("/api/voices").json()["voices"]}
    assert voices["speaker1"]["reference_transcript"] in (None, "")
