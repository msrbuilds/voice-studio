"""Chatterbox Multilingual V3 engine — Resemble AI's 0.5B multilingual TTS.

See https://huggingface.co/ResembleAI/chatterbox and
https://github.com/resemble-ai/chatterbox.

Chatterbox Multilingual V3 is a 500M-parameter Llama-backbone TTS model
supporting 23 languages with zero-shot voice cloning from a short reference
clip. Key tuning knobs:

- ``cfg_weight`` (0.0–1.0) — classifier-free guidance strength. Lower
  values produce more natural pacing; higher values adhere more strictly
  to the reference voice.
- ``exaggeration`` (0.0–1.0+) — voice expressiveness. Higher values
  sound more dramatic; lower values are more neutral.
- ``language_id`` — BCP-47 short code (e.g. ``"en"``, ``"fr"``, ``"ur"``,
  ``"zh"``). Must be one of the 23 supported codes.

All Chatterbox outputs are watermarked by Resemble AI's Perth
(Perceptual Threshold) system; this can be disabled via the
``chatterbox_watermark`` setting for development/testing.

The ``chatterbox-tts`` import is lazy so the backend still boots when
the package is not installed. If ``chatterbox-tts`` is missing, the
engine registers itself with ``loaded=False`` and ``load()`` raises a
helpful error on first use.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from . import Engine, EngineResult, EngineSynthRequest, wrap_pcm_as_wav

log = logging.getLogger(__name__)


# Chatterbox supports these 23 language ids (per the HF model card).
# The model takes the short 2-letter code; we accept either case and
# any 3+ char BCP-47 variant and truncate to the first two letters.
SUPPORTED_LANGUAGE_IDS: frozenset[str] = frozenset({
    "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi",
    "it", "ja", "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv",
    "sw", "tr", "zh",
})


def _normalize_language_id(value: str | None, default: str) -> str:
    """Coerce a voice-language code into a Chatterbox-compatible id.

    - None / empty → default
    - Normalize to lowercase, strip locale suffix (e.g. ``"en-US"`` → ``"en"``)
    - If the 2-letter prefix isn't in the supported set, fall back to default.
    """
    if not value:
        return default
    candidate = value.strip().lower().split("-")[0].split("_")[0][:2]
    if candidate in SUPPORTED_LANGUAGE_IDS:
        return candidate
    log.warning(
        "Unsupported Chatterbox language_id %r (got %r); falling back to %r. "
        "Supported: %s",
        candidate, value, default, sorted(SUPPORTED_LANGUAGE_IDS),
    )
    return default


class ChatterboxEngine(Engine):
    """Chatterbox Multilingual V3 via the `chatterbox-tts` PyPI package.

    Notes:
    - Voice cloning only — no built-in voice catalog. Voices are resolved
      from the filesystem (VoiceRegistry) the same way VibeVoice does it.
    - Single-speaker per call. Multi-speaker scripts reuse the first
      speaker's voice for the whole segment (the SynthService already
      handles this).
    - Requires ``chatterbox-tts`` to be installed. First load downloads
      the model weights (~500 MB) into the configured HF cache
      (``backend/models/`` by default).
    """

    name = "chatterbox"
    display_name = "Chatterbox Multilingual V3"
    description = (
        "Resemble AI's 0.5B multilingual TTS. 23 languages, voice cloning, "
        "watermarked output. ~500 MB."
    )

    def __init__(
        self,
        model_id: str = "ResembleAI/chatterbox",
        default_language_id: str = "en",
        default_cfg_weight: float = 0.5,
        default_exaggeration: float = 0.5,
        watermark: bool = True,
        device_request: str = "cuda",
    ) -> None:
        self._model_id = model_id
        self._default_language_id = _normalize_language_id(
            default_language_id, "en"
        )
        self._default_cfg_weight = float(default_cfg_weight)
        self._default_exaggeration = float(default_exaggeration)
        self._watermark = bool(watermark)
        self._device_request = device_request
        self._model: Any | None = None
        self._available: bool | None = None  # cache import check

    # -- lifecycle
    def load(self) -> None:
        self._ensure_chatterbox()
        device = self._device_request
        if device == "auto":
            device = "cuda"
        log.info(
            "Loading Chatterbox Multilingual TTS (%s) on %s",
            self._model_id, device,
        )
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        # The `t3_model="v3"` kwarg was added in a later release of
        # chatterbox-tts. v0.1.x exposes only `device` on
        # `from_pretrained`. Try the newer signature first, fall back
        # to the older one so the engine works regardless of which
        # version the user installed.
        try:
            self._model = ChatterboxMultilingualTTS.from_pretrained(
                device=device,
                t3_model="v3",
            )
        except TypeError as exc:
            if "t3_model" in str(exc):
                log.info(
                    "chatterbox-tts <0.2 detected (no t3_model kwarg); "
                    "loading the bundled multilingual model directly."
                )
                self._model = ChatterboxMultilingualTTS.from_pretrained(
                    device=device,
                )
            else:
                raise

    def unload(self) -> None:
        if self._model is not None:
            del self._model
            self._model = None
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def is_loaded(self) -> bool:
        if self._available is False:
            return False
        return self._model is not None

    def engine_info(self) -> dict[str, Any]:
        """Surface Chatterbox's runtime info to /api/config.

        Chatterbox uses bfloat16 on CUDA by default (matching its
        training dtype) and float32 on CPU. Resemble AI doesn't expose
        a custom attention implementation — it uses vanilla PyTorch SDPA.
        """
        import torch
        device = self._device_request
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        # Report the dtype the engine will use once loaded — independent
        # of whether it's currently loaded. The UI wants a stable hint
        # about what hardware/dtype will be used, not just "loaded vs not".
        dtype = "bfloat16" if device == "cuda" else "float32"
        return {
            "model_id": self._model_id,
            "device": device,
            "dtype": dtype,
            "attn_implementation": "sdpa",
        }

    # -- capabilities
    def sample_rate(self) -> int:
        return 24000

    def max_speakers(self) -> int:
        return 1

    def supports_voice_cloning(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        # Chatterbox's generate() returns a single tensor after running
        # T3 inference + S3Gen vocoding. Streaming would require exposing
        # the t3.inference() step loop, which the upstream chatterbox-tts
        # library doesn't surface in this version. Fall back to
        # /api/synthesize.
        return False

    def default_cfg_scale(self) -> float | None:
        # The SettingsMenu's "CFG" slider maps to cfg_weight here. Both
        # are classifier-free guidance strength on a 0.0–1.0+ scale.
        return self._default_cfg_weight

    def available_voices(self) -> list:
        # No built-in voice catalog; voices come from VoiceRegistry and
        # are tagged with engine="chatterbox" by SynthService when the
        # active engine supports cloning. Returning [] here is correct.
        return []

    # -- synthesis
    def synthesize(self, req: EngineSynthRequest) -> EngineResult:
        if self._model is None:
            raise RuntimeError("Chatterbox model is not loaded")

        text = (req.text or "").strip()
        if not text:
            raise ValueError("text must be non-empty")
        if not req.reference_audio:
            raise ValueError(
                "Chatterbox requires a reference_audio path for voice cloning"
            )

        language_id = _normalize_language_id(
            req.language_id, self._default_language_id
        )
        cfg_weight = (
            req.cfg_weight
            if req.cfg_weight is not None
            else self._default_cfg_weight
        )
        exaggeration = (
            req.exaggeration
            if req.exaggeration is not None
            else self._default_exaggeration
        )
        # Clamp into the documented ranges so a runaway slider doesn't
        # crash generation. Chatterbox tolerates values up to ~2.0 for
        # exaggeration but anything higher tends to produce artifacts.
        cfg_weight = max(0.0, min(1.0, float(cfg_weight)))
        exaggeration = max(0.0, min(2.0, float(exaggeration)))

        log.debug(
            "Chatterbox synth: language_id=%s cfg_weight=%.2f exaggeration=%.2f "
            "watermark=%s ref=%s text_len=%d",
            language_id, cfg_weight, exaggeration, self._watermark,
            req.reference_audio, len(text),
        )

        # The `watermark` kwarg was added in a later release of
        # chatterbox-tts. v0.1.x always embeds Perth watermarks
        # unconditionally and doesn't expose a flag to disable them.
        # Try the newer signature first; if the kwarg is rejected,
        # fall back to the older one and log a warning so the user
        # knows `CHATTERBOX_WATERMARK=false` won't take effect on this
        # version.
        t0 = time.perf_counter()
        try:
            wav_tensor = self._model.generate(
                text,
                language_id=language_id,
                audio_prompt_path=req.reference_audio,
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                watermark=self._watermark,
            )
        except TypeError as exc:
            if "watermark" in str(exc):
                if not self._watermark:
                    log.warning(
                        "chatterbox-tts <0.2 detected (no watermark kwarg); "
                        "the output will be watermarked regardless of "
                        "CHATTERBOX_WATERMARK=false. Upgrade chatterbox-tts "
                        "to disable watermarking."
                    )
                wav_tensor = self._model.generate(
                    text,
                    language_id=language_id,
                    audio_prompt_path=req.reference_audio,
                    exaggeration=exaggeration,
                    cfg_weight=cfg_weight,
                )
            else:
                raise
        inference_ms = int((time.perf_counter() - t0) * 1000)

        # Tensor → numpy → WAV bytes
        import numpy as np
        import torch

        if hasattr(wav_tensor, "detach"):
            arr = wav_tensor.detach().cpu()
            if hasattr(arr, "to") and arr.is_floating_point():
                arr = arr.to(torch.float32)
            arr = arr.numpy()
        else:
            arr = np.asarray(wav_tensor, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.reshape(-1)

        sr = self.sample_rate()
        duration = float(arr.size) / float(sr)
        wav_bytes = wrap_pcm_as_wav(arr, sr)

        return EngineResult(
            wav_bytes=wav_bytes,
            sample_rate=sr,
            duration_sec=duration,
            inference_ms=inference_ms,
        )

    # -- helpers
    def _ensure_chatterbox(self) -> None:
        if self._available is False:
            raise RuntimeError(
                "The 'chatterbox-tts' package is not installed. "
                "Run `pip install -r backend/requirements.txt` (or "
                "`pip install --user chatterbox-tts` on Windows if you hit "
                "the Scripts/ launcher race condition)."
            )
        if self._available is None:
            try:
                import chatterbox  # noqa: F401
                self._available = True
            except ImportError as exc:
                self._available = False
                raise RuntimeError(
                    "The 'chatterbox-tts' package is not installed. "
                    "Run `pip install -r backend/requirements.txt` "
                    f"(import error: {exc})"
                ) from exc
