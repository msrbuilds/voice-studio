"""AsrService: validation, decode, cache, GPU gate.

Uses a stub AsrEngine throughout — the suite must never load Whisper's weights.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.asr import AsrResult, AsrSegment  # noqa: E402
from backend.core.exceptions import BackendError  # noqa: E402
from backend.core.gpu_gate import GpuGate  # noqa: E402


class _StubAsr:
    """Counts transcribe() calls so cache hits are observable."""

    name = "stub"
    calls = 0

    def __init__(self, downloaded: bool = True) -> None:
        self._downloaded = downloaded

    def is_loaded(self) -> bool:
        return True

    def load(self) -> None:
        pass

    def downloaded(self) -> bool:
        return self._downloaded

    def sample_rate(self) -> int:
        return 16000

    def languages(self):
        return [{"code": "en", "label": "English"}]

    def transcribe(self, req):
        type(self).calls += 1
        return AsrResult(
            text="hello world",
            language="en",
            duration_sec=1.0,
            inference_ms=7,
            segments=[AsrSegment(0.0, 1.0, "hello world")],
        )


def _wav(tmp_path: Path, name: str = "a.wav", secs: float = 1.0) -> Path:
    p = tmp_path / name
    sf.write(p, np.zeros(int(16000 * secs), dtype=np.float32), 16000)
    return p


def _svc(tmp_path: Path, engine=None, **kw):
    from backend.services.asr_cache import AsrCache
    from backend.services.transcribe import AsrService

    return AsrService(
        engine=engine or _StubAsr(),
        gate=GpuGate(timeout_s=10),
        cache=AsrCache(tmp_path / "asrcache"),
        max_upload_mb=kw.get("max_upload_mb", 100),
        max_duration_sec=kw.get("max_duration_sec", 3600),
    )


def test_transcribe_happy_path(tmp_path):
    _StubAsr.calls = 0
    r = _svc(tmp_path).transcribe_file(str(_wav(tmp_path)), language=None, timestamps=True)
    assert r.text == "hello world"
    assert r.language == "en"
    assert r.cache_hit is False
    assert r.segments == [{"start": 0.0, "end": 1.0, "text": "hello world"}]
    assert r.cache_hash.startswith("asr-")


def test_second_identical_call_is_a_cache_hit(tmp_path):
    _StubAsr.calls = 0
    svc = _svc(tmp_path)
    p = _wav(tmp_path)
    svc.transcribe_file(str(p), language=None, timestamps=True)
    r2 = svc.transcribe_file(str(p), language=None, timestamps=True)
    assert r2.cache_hit is True
    assert r2.text == "hello world"
    assert r2.segments[0]["end"] == 1.0
    assert _StubAsr.calls == 1, "engine ran twice despite identical request"


def test_cache_key_folds_language_and_timestamps(tmp_path):
    _StubAsr.calls = 0
    svc = _svc(tmp_path)
    p = _wav(tmp_path)
    svc.transcribe_file(str(p), language=None, timestamps=True)
    svc.transcribe_file(str(p), language="ur", timestamps=True)    # language differs
    svc.transcribe_file(str(p), language=None, timestamps=False)   # flag differs
    assert _StubAsr.calls == 3


def test_different_audio_different_key(tmp_path):
    _StubAsr.calls = 0
    svc = _svc(tmp_path)
    svc.transcribe_file(str(_wav(tmp_path, "a.wav", 1.0)), language=None, timestamps=False)
    svc.transcribe_file(str(_wav(tmp_path, "b.wav", 2.0)), language=None, timestamps=False)
    assert _StubAsr.calls == 2


def test_rejects_unsupported_extension(tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_text("not audio")
    with pytest.raises(BackendError) as e:
        _svc(tmp_path).transcribe_file(str(bad), language=None, timestamps=False)
    assert e.value.http_status == 400


def test_rejects_oversize_upload(tmp_path):
    svc = _svc(tmp_path, max_upload_mb=0)  # everything is too big
    with pytest.raises(BackendError) as e:
        svc.transcribe_file(str(_wav(tmp_path)), language=None, timestamps=False)
    assert e.value.http_status == 413


def test_rejects_too_long_audio(tmp_path):
    svc = _svc(tmp_path, max_duration_sec=0.5)
    with pytest.raises(BackendError) as e:
        svc.transcribe_file(str(_wav(tmp_path, secs=2.0)), language=None, timestamps=False)
    assert e.value.http_status == 400


def test_503_when_weights_absent(tmp_path):
    svc = _svc(tmp_path, engine=_StubAsr(downloaded=False))
    with pytest.raises(BackendError) as e:
        svc.transcribe_file(str(_wav(tmp_path)), language=None, timestamps=False)
    assert e.value.http_status == 503


def test_undecodable_audio_is_400(tmp_path):
    junk = tmp_path / "junk.wav"
    junk.write_bytes(b"not really a wav")
    with pytest.raises(BackendError) as e:
        _svc(tmp_path).transcribe_file(str(junk), language=None, timestamps=False)
    assert e.value.http_status == 400


def test_asr_cache_roundtrip_and_clear(tmp_path):
    from backend.services.asr_cache import AsrCache

    c = AsrCache(tmp_path / "c")
    assert c.get("nope") is None
    c.put("asr-1", {"text": "hi"})
    assert c.get("asr-1") == {"text": "hi"}
    assert len(c) == 1
    assert c.clear() == 1
    assert c.get("asr-1") is None
