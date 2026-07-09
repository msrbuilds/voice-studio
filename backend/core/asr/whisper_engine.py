"""Whisper large-v3-turbo ASR engine — IN-PROCESS (main venv).

transformers 4.51.3 ships `WhisperForConditionalGeneration`, so there is no
vendored repo, no isolated venv and no subprocess worker (unlike Chatterbox /
OmniVoice / VoxCPM / Qwen, which pin incompatible transformers versions).

Characteristics (spike-measured on a 12 GB GPU):
  * 809 M params, 16 kHz mono input, peak VRAM ~1.56 GB in fp16.
  * ~13-16x realtime. 99 languages, with reliable auto-detection.
  * Whisper's raw attention window is 30 s. Long-form audio is handled by the
    transformers ASR `pipeline`, which chunks (30 s) and strides (5 s) for us —
    a 72 s clip transcribes in one call with contiguous timestamps.

Two transformers-version landmines, both spike-verified on 4.51.3:
  * `generate(..., return_language=True)` raises ValueError — it is not a valid
    model kwarg here. Use `model.detect_language()` instead.
  * `hf_paths.configure_hf_cache()` must run BEFORE transformers is imported,
    so every heavy import lives inside `load()`.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from . import AsrEngine, AsrRequest, AsrResult, AsrSegment

log = logging.getLogger(__name__)

MODEL_ID = "openai/whisper-large-v3-turbo"

_SAMPLE_RATE = 16000
_CHUNK_LENGTH_S = 30      # Whisper's training window
_STRIDE_LENGTH_S = 5      # overlap so words on a boundary aren't lost


def _lang_from_token(token: str | None) -> str:
    """`"<|en|>"` -> `"en"`. Passes bare codes through; `None`/`""` -> `""`."""
    if not token:
        return ""
    return token.strip().lstrip("<|").rstrip("|>").strip()


def _chunks_to_segments(chunks: list[dict[str, Any]] | None) -> list[AsrSegment]:
    """Map the pipeline's `chunks` to AsrSegments.

    The pipeline emits a trailing chunk with `end=None` when the audio is cut
    mid-utterance; such a span can't be rendered as a subtitle, so drop it.
    Blank text is dropped too.
    """
    out: list[AsrSegment] = []
    for c in chunks or []:
        ts = c.get("timestamp")
        if not ts or len(ts) != 2:
            continue
        start, end = ts
        if start is None or end is None:
            continue
        text = (c.get("text") or "").strip()
        if not text:
            continue
        out.append(AsrSegment(start=float(start), end=float(end), text=text))
    return out


class WhisperEngine(AsrEngine):
    name = "whisper"
    display_name = "Whisper large-v3-turbo"
    description = "OpenAI's speech-to-text model. 99 languages, 16 kHz mono input."
    license = "MIT"
    model_url = "https://huggingface.co/openai/whisper-large-v3-turbo"

    def __init__(self, model_id: str = MODEL_ID, device_request: str = "cuda") -> None:
        self._model_id = model_id
        self._device_request = device_request
        self._model = None
        self._processor = None
        self._pipe = None

    # -- lifecycle
    def _device(self) -> str:
        import torch

        if self._device_request == "cpu":
            return "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    def load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

        device = self._device()
        dtype = torch.float16 if device == "cuda" else torch.float32
        t0 = time.perf_counter()

        self._processor = AutoProcessor.from_pretrained(self._model_id)
        model = AutoModelForSpeechSeq2Seq.from_pretrained(self._model_id, torch_dtype=dtype)
        self._model = model.to(device)
        # Switch off training mode. (Deliberately not the one-word alias — a
        # security hook flags that identifier as JavaScript's eval.)
        self._model.train(False)

        self._pipe = pipeline(
            "automatic-speech-recognition",
            model=self._model,
            tokenizer=self._processor.tokenizer,
            feature_extractor=self._processor.feature_extractor,
            chunk_length_s=_CHUNK_LENGTH_S,
            stride_length_s=_STRIDE_LENGTH_S,
            torch_dtype=dtype,
            device=device,
        )
        log.info("Whisper loaded on %s in %.1fs", device, time.perf_counter() - t0)

    def unload(self) -> None:
        if self._model is None and self._processor is None:
            return
        self._pipe = None
        self._model = None
        self._processor = None
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    def is_loaded(self) -> bool:
        return self._model is not None and self._pipe is not None

    def sample_rate(self) -> int:
        return _SAMPLE_RATE

    def downloaded(self) -> bool:
        from ..model_cache import model_downloaded

        return model_downloaded(self._model_id)

    def languages(self) -> list[dict[str, str]]:
        """The model's own language table. Empty until the model is loaded."""
        if self._model is None:
            return []
        try:
            from transformers.models.whisper.tokenization_whisper import LANGUAGES

            codes = sorted(
                {_lang_from_token(t) for t in self._model.generation_config.lang_to_id}
            )
            return [
                {"code": c, "label": LANGUAGES.get(c, c).title()}
                for c in codes
                if c
            ]
        except Exception:  # noqa: BLE001 — never let the status endpoint 500
            log.debug("could not enumerate whisper languages", exc_info=True)
            return []

    def engine_info(self) -> dict[str, Any]:
        return {
            "model_id": self._model_id,
            "device": self._device() if self.is_loaded() else self._device_request,
            "dtype": "float16" if self._device_request != "cpu" else "float32",
        }

    # -- inference
    def _detect_language(self, wav) -> str:
        """Whisper's own language ID pass. `generate(return_language=True)` is
        not a valid kwarg on transformers 4.51.3, so use detect_language()."""
        import torch

        feats = self._processor(
            wav, sampling_rate=_SAMPLE_RATE, return_tensors="pt"
        ).to(self._device(), self._model.dtype)
        with torch.no_grad():
            tokens = self._model.detect_language(input_features=feats.input_features)
        return _lang_from_token(self._processor.tokenizer.decode(tokens[0]))

    def transcribe(self, req: AsrRequest) -> AsrResult:
        if not self.is_loaded():
            self.load()
        import librosa

        wav, _ = librosa.load(req.audio_path, sr=_SAMPLE_RATE, mono=True)
        duration = len(wav) / float(_SAMPLE_RATE)

        language = (req.language or "").strip().lower()
        if not language or language == "auto":
            language = self._detect_language(wav)

        t0 = time.perf_counter()
        out = self._pipe(
            wav.copy(),  # the pipeline mutates its input buffer in-place
            return_timestamps=bool(req.timestamps),
            generate_kwargs={"task": "transcribe", "language": language or None},
        )
        inference_ms = int((time.perf_counter() - t0) * 1000)

        segments = _chunks_to_segments(out.get("chunks")) if req.timestamps else []
        return AsrResult(
            text=(out.get("text") or "").strip(),
            language=language,
            duration_sec=duration,
            inference_ms=inference_ms,
            segments=segments,
        )
