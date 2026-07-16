"""/api/asr/* routes, catalog entry, and download-route reuse.

The real WhisperEngine is swapped for a stub on app.state, so no weights load.
"""
import io
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.tests.test_smoke import _make_client  # noqa: E402


class _StubAsr:
    # Mirrors the AsrEngine ABC's class attributes — /api/asr/status surfaces
    # them so the engine popup can render a card without hardcoding strings.
    name = "whisper"
    _model_id = "openai/whisper-large-v3-turbo"
    display_name = "Whisper large-v3-turbo"
    description = "OpenAI's speech-to-text model."
    license = "MIT"
    model_url = "https://huggingface.co/openai/whisper-large-v3-turbo"

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
        from backend.core.asr import AsrResult, AsrSegment

        return AsrResult(
            text="hello world", language="en", duration_sec=1.0, inference_ms=7,
            segments=[AsrSegment(0.0, 1.0, "hello world")],
        )


def _wav_bytes(secs: float = 1.0) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.zeros(int(16000 * secs), dtype=np.float32), 16000, format="WAV")
    return buf.getvalue()


def _client_with_stub(tmp_path):
    client = _make_client(tmp_path / "v", tmp_path / "u")
    client.app.state.asr_service._engine = _StubAsr()
    return client


def test_whisper_in_catalog_and_downloadable():
    from backend.scripts.download_models import MODEL_CATALOG
    from backend.services.model_download import DOWNLOADABLE

    assert MODEL_CATALOG["whisper"]["repo_id"] == "openai/whisper-large-v3-turbo"
    assert "whisper" in DOWNLOADABLE


def test_engines_download_route_accepts_whisper(tmp_path):
    """The download route validates against DOWNLOADABLE, not the engine registry,
    so Whisper reuses it without being a TTS engine."""
    client = _make_client(tmp_path / "v", tmp_path / "u")
    assert client.get("/api/engines/whisper/download").status_code == 200


def test_whisper_is_not_in_the_engine_selector(tmp_path):
    client = _make_client(tmp_path / "v", tmp_path / "u")
    names = {e["name"] for e in client.get("/api/engines").json()["engines"]}
    assert "whisper" not in names


def test_asr_status(tmp_path):
    client = _client_with_stub(tmp_path)
    body = client.get("/api/asr/status").json()
    assert body["model_id"] == "openai/whisper-large-v3-turbo"
    assert body["loaded"] is True and body["downloaded"] is True
    assert body["languages"][0]["code"] == "en"
    # The engine popup renders its Whisper card straight from these.
    assert body["name"] == "whisper"
    assert body["display_name"] == "Whisper large-v3-turbo"
    assert body["license"] == "MIT"
    assert body["model_url"].startswith("https://")


def test_asr_status_exposes_real_engine_metadata(tmp_path):
    """Regression: the card needs these from the real engine, not the stub."""
    client = _make_client(tmp_path / "v", tmp_path / "u")
    body = client.get("/api/asr/status").json()
    assert body["name"] == "whisper"
    assert body["display_name"] == "Whisper large-v3-turbo"
    assert body["license"] == "MIT"


def test_transcribe_requires_exactly_one_source(tmp_path):
    client = _client_with_stub(tmp_path)
    # neither
    assert client.post("/api/asr/transcribe", data={}).status_code == 422
    # both
    r = client.post(
        "/api/asr/transcribe",
        data={"cache_hash": "abc"},
        files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
    )
    assert r.status_code == 422


def test_transcribe_upload(tmp_path):
    client = _client_with_stub(tmp_path)
    r = client.post(
        "/api/asr/transcribe",
        files={"file": ("a.wav", _wav_bytes(), "audio/wav")},
        data={"timestamps": "true"},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["text"] == "hello world"
    assert b["language"] == "en"
    assert b["cache_hit"] is False
    assert b["segments"][0] == {"start": 0.0, "end": 1.0, "text": "hello world"}


def test_transcribe_rejects_bad_extension(tmp_path):
    client = _client_with_stub(tmp_path)
    r = client.post(
        "/api/asr/transcribe",
        files={"file": ("a.txt", b"nope", "text/plain")},
    )
    assert r.status_code == 400


def test_transcribe_unknown_cache_hash_is_404(tmp_path):
    client = _client_with_stub(tmp_path)
    r = client.post("/api/asr/transcribe", data={"cache_hash": "does-not-exist"})
    assert r.status_code == 404


def test_transcribe_by_cache_hash(tmp_path):
    """Subtitles path: transcribe audio already sitting in SynthCache."""
    client = _client_with_stub(tmp_path)
    cache = client.app.state.synth_cache
    h = "abc" + "0" * 21
    cache.put(h, _wav_bytes(), 16000, 1.0, 5, text="t", voice="v")

    r = client.post("/api/asr/transcribe", data={"cache_hash": h, "timestamps": "true"})
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hello world"
