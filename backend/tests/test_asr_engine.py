"""WhisperEngine metadata + pure helpers.

Deliberately never calls load(): the suite must not pull 1.6 GB of weights.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.asr import AsrRequest, AsrResult, AsrSegment  # noqa: E402
from backend.core.asr.whisper_engine import (  # noqa: E402
    MODEL_ID,
    WhisperEngine,
    _chunks_to_segments,
    _lang_from_token,
)


def test_whisper_metadata():
    e = WhisperEngine()
    assert e.name == "whisper"
    assert e.sample_rate() == 16000
    assert e.is_loaded() is False
    assert MODEL_ID == "openai/whisper-large-v3-turbo"
    assert e.model_url.endswith("whisper-large-v3-turbo")


def test_lang_from_token():
    assert _lang_from_token("<|en|>") == "en"
    assert _lang_from_token("<|ur|>") == "ur"
    assert _lang_from_token("<|yue|>") == "yue"
    assert _lang_from_token("en") == "en"      # already bare
    assert _lang_from_token(None) == ""
    assert _lang_from_token("") == ""


def test_chunks_to_segments_drops_open_ended_tail():
    """The ASR pipeline emits a final chunk with end=None on a truncated tail."""
    chunks = [
        {"timestamp": (0.0, 2.5), "text": " Hello"},
        {"timestamp": (2.5, 5.0), "text": " world"},
        {"timestamp": (5.0, None), "text": " tail"},
    ]
    segs = _chunks_to_segments(chunks)
    assert len(segs) == 2
    assert segs[0] == AsrSegment(start=0.0, end=2.5, text="Hello")
    assert segs[1].text == "world"


def test_chunks_to_segments_handles_missing_and_empty():
    assert _chunks_to_segments([]) == []
    assert _chunks_to_segments([{"text": "no timestamp"}]) == []
    assert _chunks_to_segments([{"timestamp": (0.0, 1.0), "text": "   "}]) == []


def test_asr_dataclass_defaults():
    r = AsrRequest(audio_path="x.wav")
    assert r.language is None and r.timestamps is False
    res = AsrResult(text="hi", language="en", duration_sec=1.0, inference_ms=5)
    assert res.segments == []


def test_whisper_is_not_a_tts_engine():
    """Whisper must never surface in the TTS engine selector."""
    from backend.core.engines import Engine

    assert not issubclass(WhisperEngine, Engine)
