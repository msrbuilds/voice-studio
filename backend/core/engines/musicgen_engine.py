"""MusicGen-small music engine — IN-PROCESS (main venv).

Unlike the removed ACE-Step engine, MusicGen runs directly in the main venv
(transformers >= 4.31 ships `MusicgenForConditionalGeneration`), so there is no
vendored repo, no isolated venv and no subprocess worker.

Characteristics (spike-measured on a 12 GB GPU):
  * 32 000 Hz **mono**, instrumental only (no vocals / lyrics conditioning).
  * ~50 audio tokens per second; trained on 30 s clips, so 30 s is the ceiling.
  * Peak VRAM 1.4-2.8 GB. fp32/bf16/fp16 generate at the same speed, so we use
    fp32 on CUDA (fp16 buys nothing and MusicGen is known to be finicky there).
  * Raw waveforms exceed +/-1.0 (peaks up to 1.9), so every clip is
    peak-normalized before it is wrapped as a WAV.
  * Variations come from repeating the prompt in the batch. Do NOT use
    `num_return_sequences`: it interacts badly with classifier-free guidance.

The weights are CC-BY-NC-4.0 (non-commercial). That is surfaced via `license`
so the UI and /api/engines can display it.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from . import Engine, EngineResult, EngineSynthRequest, wrap_pcm_as_wav

log = logging.getLogger(__name__)

MODEL_ID = "facebook/musicgen-small"

#: The repo ships pytorch_model.bin AND model.safetensors plus audiocraft state
#: dicts; transformers only needs the safetensors. Must match
#: `services/model_download.IGNORE_PATTERNS["musicgen"]` or the "downloaded?"
#: probe would demand files we never fetch.
_IGNORE = ["*.bin"]

_SAMPLE_RATE = 32000
_TOKENS_PER_SEC = 50       # spike-measured: 500 tokens -> 9.94 s of audio
_MIN_DUR, _MAX_DUR = 5.0, 30.0
_PEAK = 0.95               # normalization target (what the approved samples used)


def _duration_to_tokens(seconds: float) -> int:
    """Clamp to MusicGen's usable range and convert to decoder tokens."""
    secs = max(_MIN_DUR, min(_MAX_DUR, float(seconds or _MIN_DUR)))
    return int(secs * _TOKENS_PER_SEC)


def _build_prompt(caption: str, bpm: int | None, keyscale: str | None,
                  timesignature: str | None) -> str:
    """MusicGen has no bpm/key/time-signature conditioning, so fold whatever the
    user set into the text prompt (the reference demo does `"... bpm: 130"`)."""
    parts = [(caption or "").strip()]
    if bpm:
        parts.append(f"bpm: {int(bpm)}")
    if keyscale and keyscale.strip():
        parts.append(f"key: {keyscale.strip()}")
    if timesignature and str(timesignature).strip():
        parts.append(f"{str(timesignature).strip()}/4")
    return ", ".join(p for p in parts if p)


def _apply_fades(wav: np.ndarray, sr: int, fade_in: float, fade_out: float) -> np.ndarray:
    """Linear fades; MusicGen has no fade support of its own."""
    n = len(wav)
    fi = min(int(max(0.0, fade_in) * sr), n)
    fo = min(int(max(0.0, fade_out) * sr), n)
    if fi > 0:
        wav[:fi] *= np.linspace(0.0, 1.0, fi, dtype=wav.dtype)
    if fo > 0:
        wav[n - fo:] *= np.linspace(1.0, 0.0, fo, dtype=wav.dtype)
    return wav


class MusicGenEngine(Engine):
    name = "musicgen"
    display_name = "MusicGen Small (Music)"
    description = "Meta's text-to-music model. 32 kHz mono, instrumental. Non-commercial license."
    license = "CC-BY-NC-4.0"
    model_url = "https://huggingface.co/facebook/musicgen-small"

    def __init__(self, device_request: str = "cuda") -> None:
        self._model_id = MODEL_ID
        self._device_request = device_request
        self._model = None
        self._processor = None

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
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        device = self._device()
        t0 = time.perf_counter()
        self._processor = AutoProcessor.from_pretrained(self._model_id)
        model = MusicgenForConditionalGeneration.from_pretrained(
            self._model_id, torch_dtype=torch.float32
        )
        self._model = model.to(device)
        self._model.train(False)
        log.info("MusicGen loaded on %s in %.1fs", device, time.perf_counter() - t0)

    def unload(self) -> None:
        if self._model is None and self._processor is None:
            return
        self._model = None
        self._processor = None
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

    def is_loaded(self) -> bool:
        return self._model is not None and self._processor is not None

    def downloaded(self) -> bool:
        from ..model_cache import model_downloaded

        return model_downloaded(self._model_id, ignore_patterns=_IGNORE)

    # -- capabilities
    def supports_music(self) -> bool:
        return True

    def sample_rate(self) -> int:
        if self._model is not None:
            return int(self._model.config.audio_encoder.sampling_rate)
        return _SAMPLE_RATE

    def max_speakers(self) -> int:
        return 0

    def supports_voice_cloning(self) -> bool:
        return False

    def default_cfg_scale(self) -> float | None:
        return None

    def available_voices(self) -> list:
        return []

    def engine_info(self) -> dict[str, Any]:
        return {
            "model_id": self._model_id,
            "device": self._device() if self.is_loaded() else self._device_request,
            "dtype": "float32",
            "attn_implementation": "eager",
        }

    # -- generation
    def synthesize(self, req: EngineSynthRequest) -> EngineResult:
        # The ABC requires it; music goes through generate_batch.
        return self.generate_batch(req, 1)[0]

    def generate_batch(self, req: EngineSynthRequest, count: int) -> list[EngineResult]:
        if not self.is_loaded():
            self.load()
        import torch

        caption = (req.caption or "").strip()
        if not caption:
            raise ValueError("caption must be non-empty for music generation")

        prompt = _build_prompt(caption, req.bpm, req.keyscale, req.timesignature)
        tokens = _duration_to_tokens(req.duration_sec or _MIN_DUR)
        count = max(1, min(4, int(count)))
        device = self._device()

        seed = req.music_seed if req.music_seed is not None else -1
        if seed is not None and seed >= 0:
            torch.manual_seed(int(seed))

        # Variations = repeat the prompt in the batch (NOT num_return_sequences,
        # which misbehaves under classifier-free guidance).
        inputs = self._processor(
            text=[prompt] * count, padding=True, return_tensors="pt"
        ).to(device)

        t0 = time.perf_counter()
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                do_sample=True,
                guidance_scale=float(req.guidance_scale if req.guidance_scale is not None else 3.0),
                temperature=float(req.temperature if req.temperature is not None else 1.0),
                max_new_tokens=tokens,
            )
        inference_ms = int((time.perf_counter() - t0) * 1000)

        sr = self.sample_rate()
        arr = out.cpu().float().numpy()  # [batch, channels, samples]
        results: list[EngineResult] = []
        for i in range(arr.shape[0]):
            wav = arr[i, 0].astype(np.float32)
            peak = float(np.abs(wav).max())
            if peak > 0:
                wav = wav / peak * _PEAK  # raw output exceeds +/-1.0
            wav = _apply_fades(wav, sr, req.fade_in or 0.0, req.fade_out or 0.0)
            results.append(EngineResult(
                wav_bytes=wrap_pcm_as_wav(wav, sr),
                sample_rate=sr,
                duration_sec=len(wav) / float(sr),
                inference_ms=inference_ms,
            ))
        return results
