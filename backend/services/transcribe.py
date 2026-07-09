"""AsrService: engine-agnostic speech-to-text orchestration.

Everything that is NOT the model lives here: format/size/duration validation,
decoding arbitrary containers down to 16 kHz mono, the result cache, and
serialization onto the shared `GpuGate` so a transcription never runs
concurrently with a TTS synthesis.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..core.asr import AsrRequest
from ..core.exceptions import BackendError

if TYPE_CHECKING:  # pragma: no cover
    from ..core.asr import AsrEngine
    from ..core.gpu_gate import GpuGate
    from .asr_cache import AsrCache

log = logging.getLogger(__name__)

#: Containers librosa/soundfile+audioread can decode.
ALLOWED_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".webm"}

_SAMPLE_RATE = 16000


@dataclass
class TranscribeResult:
    text: str
    language: str
    duration_sec: float
    inference_ms: int
    cache_hash: str
    cache_hit: bool = False
    segments: list[dict[str, Any]] = field(default_factory=list)


class AsrService:
    def __init__(
        self,
        engine: "AsrEngine",
        gate: "GpuGate",
        cache: "AsrCache | None" = None,
        max_upload_mb: int = 100,
        max_duration_sec: int = 3600,
        timeout_s: int | None = None,
    ) -> None:
        self._engine = engine
        self._gate = gate
        self._cache = cache
        self._max_upload_bytes = int(max_upload_mb) * 1024 * 1024
        self._max_duration_sec = float(max_duration_sec)
        self._timeout_s = timeout_s

    @property
    def engine(self) -> "AsrEngine":
        return self._engine

    def status(self) -> dict[str, Any]:
        return {
            "model_id": getattr(self._engine, "_model_id", self._engine.name),
            "loaded": self._engine.is_loaded(),
            "downloaded": self._engine.downloaded(),
            "languages": self._engine.languages(),
        }

    # -- internals
    @staticmethod
    def _cache_key(audio: bytes, language: str | None, timestamps: bool) -> str:
        lang = (language or "auto").strip().lower() or "auto"
        h = hashlib.sha256()
        h.update(audio)
        h.update(f"|{lang}|{int(bool(timestamps))}".encode())
        return "asr-" + h.hexdigest()[:24]

    def _decode(self, path: str):
        """Decode any supported container to 16 kHz mono float32."""
        import librosa

        try:
            wav, _ = librosa.load(path, sr=_SAMPLE_RATE, mono=True)
        except Exception as exc:  # noqa: BLE001 — any decode failure is user error
            raise BackendError(
                f"could not decode audio: {exc}",
                code="audio_invalid",
                http_status=400,
            ) from exc
        if wav.size == 0:
            raise BackendError("audio is empty", code="audio_invalid", http_status=400)
        return wav

    # -- public
    def transcribe_file(
        self,
        path: str,
        language: str | None = None,
        timestamps: bool = False,
    ) -> TranscribeResult:
        p = Path(path)
        if p.suffix.lower() not in ALLOWED_EXT:
            raise BackendError(
                f"unsupported audio format '{p.suffix}'; expected one of "
                + ", ".join(sorted(ALLOWED_EXT)),
                code="audio_invalid",
                http_status=400,
            )
        try:
            size = p.stat().st_size
        except OSError as exc:
            raise BackendError("audio file not readable", code="audio_invalid",
                               http_status=400) from exc
        if size > self._max_upload_bytes:
            raise BackendError(
                f"audio is {size / 1048576:.1f} MB; limit is "
                f"{self._max_upload_bytes / 1048576:.0f} MB",
                code="audio_too_large",
                http_status=413,
            )
        if not self._engine.downloaded():
            raise BackendError(
                "speech-to-text weights are not downloaded",
                code="asr_unavailable",
                http_status=503,
            )

        audio_bytes = p.read_bytes()
        key = self._cache_key(audio_bytes, language, timestamps)
        if self._cache is not None and self._cache.enabled:
            hit = self._cache.get(key)
            if hit is not None:
                return TranscribeResult(
                    text=hit["text"], language=hit["language"],
                    duration_sec=hit["duration_sec"], inference_ms=hit["inference_ms"],
                    cache_hash=key, cache_hit=True, segments=hit.get("segments", []),
                )

        wav = self._decode(str(p))
        duration = len(wav) / float(_SAMPLE_RATE)
        if duration > self._max_duration_sec:
            raise BackendError(
                f"audio is {duration:.0f}s; limit is {self._max_duration_sec:.0f}s",
                code="audio_invalid",
                http_status=400,
            )

        if not self._engine.is_loaded():
            self._engine.load()

        # Hand the engine a normalized 16 kHz mono WAV so it never has to know
        # about the caller's container format.
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            sf.write(tmp_path, wav, _SAMPLE_RATE)
            req = AsrRequest(audio_path=tmp_path, language=language, timestamps=timestamps)
            try:
                res = self._gate.run(self._engine.transcribe, req, timeout=self._timeout_s)
            except concurrent.futures.TimeoutError as exc:
                raise BackendError(
                    "transcription timed out", code="asr_timeout", http_status=504
                ) from exc
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except OSError:
                pass

        segments = [{"start": s.start, "end": s.end, "text": s.text} for s in res.segments]
        payload = {
            "text": res.text, "language": res.language,
            "duration_sec": res.duration_sec, "inference_ms": res.inference_ms,
            "segments": segments,
        }
        if self._cache is not None and self._cache.enabled:
            self._cache.put(key, payload)

        return TranscribeResult(
            text=res.text, language=res.language, duration_sec=res.duration_sec,
            inference_ms=res.inference_ms, cache_hash=key, cache_hit=False,
            segments=segments,
        )
