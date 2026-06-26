# Chatterbox Isolated Environment — Design

**Date:** 2026-06-27
**Status:** Approved (design)

## Problem

The Chatterbox engine cannot share a Python environment with VibeVoice:

- `vibevoice` (community fork) hard-requires `transformers==4.51.3`; its modeling
  code breaks on transformers 5.x (`ValueError: '<VibeVoiceAcousticTokenizerConfig>'
  is already used by a Transformers model`).
- `chatterbox-tts` (>=0.1.7) hard-pins `transformers==5.2.0`.

`backend/requirements.txt` currently lists both, so it is internally self-conflicting:
`pip install -r requirements.txt` (run by `studio.py setup`) upgrades transformers to
5.2.0 and silently breaks VibeVoice, the default engine. Kokoro is unaffected.

## Goals

1. Run Chatterbox without breaking VibeVoice — the two never share a Python process.
2. Keep the default install (`studio.py setup`) producing a working VibeVoice + Kokoro env.
3. Make Chatterbox an opt-in install that lives in its own environment.
4. No change to the public Engine interface, EngineManager, or SynthService.

## Non-Goals (YAGNI)

- Streaming audio from the worker (Chatterbox returns a single tensor; matches today).
- Multi-worker pools / concurrent Chatterbox requests (SynthService serializes synthesis).
- Auto-building the Chatterbox venv on first use (it's an explicit setup step).
- A general plugin/sidecar framework for arbitrary engines.

## Solution Overview

The in-process `ChatterboxEngine` is rewritten as a **thin proxy** that keeps the exact
same `Engine` ABC surface, so EngineManager and SynthService are untouched. Behind that
interface it drives a **persistent worker subprocess** running in a separate
`backend/venv-chatterbox` that has `transformers 5.x` + `chatterbox-tts`. The main venv
keeps `transformers 4.51.3` for VibeVoice.

```
SynthService ──> ChatterboxEngine (proxy, main venv)
                      │  newline-delimited JSON over stdin/stdout
                      │  + generated WAV written to a temp file path
                      ▼
                 chatterbox_worker.py  (backend/venv-chatterbox python)
                      └─ loads ChatterboxMultilingualTTS, runs generate()
```

Communication is local: the reference clip and output WAV are passed as **filesystem
paths**, so no binary audio streams over the pipe.

## Components

### 1. `backend/chatterbox_worker.py` (runs in venv-chatterbox)

A **standalone** script. Imports only the standard library, `chatterbox`, `numpy`, and
`wave`. It MUST NOT import the `backend` package (the Chatterbox venv does not have the
main backend's deps).

Protocol — newline-delimited JSON, one object per line:

- stdin requests:
  - `{"op": "load", "device": "cuda"}`
  - `{"op": "synth", "text": "...", "reference_audio": "<path>", "language_id": "en",
     "cfg_weight": 0.5, "exaggeration": 0.5, "watermark": true, "out_wav": "<temp path>"}`
  - `{"op": "shutdown"}`
- stdout responses (one JSON line each):
  - load → `{"ok": true}` or `{"ok": false, "error": "..."}`
  - synth → `{"ok": true, "sample_rate": 24000, "duration_sec": 1.83, "inference_ms": 412}`
    (the WAV itself is written to `out_wav`), or `{"ok": false, "error": "..."}`
- All logging/warnings go to **stderr** so they never corrupt the stdout protocol.

The worker writes a 16-bit PCM mono WAV to `out_wav` using stdlib `wave` + `numpy`
(self-contained; no dependency on the main repo's `wrap_pcm_as_wav`). It carries over the
existing engine's generation details: `model.generate(text, language_id=...,
audio_prompt_path=ref, exaggeration=..., cfg_weight=..., watermark=...)` with the same
older/newer chatterbox-tts signature fallbacks (no `t3_model`/`watermark` kwargs on <0.2)
that live in today's engine.

### 2. `backend/core/engines/chatterbox_engine.py` (rewritten proxy, main venv)

Same `Engine` interface and capabilities as today (`name="chatterbox"`,
`max_speakers()==1`, `supports_voice_cloning()==True`, `supports_streaming()==False`,
`sample_rate()==24000`, `default_cfg_scale()`, `available_voices()==[]`, `engine_info()`).
Language-id normalization (`_normalize_language_id`, the 23-code set) stays in this module.

Internals:
- The constructor gains two **optional** kwargs, `worker_python: Path | None = None` and
  `worker_script: Path | None = None`, each defaulting to `None` → derived from the backend
  root (`backend/venv-chatterbox/...` and `backend/chatterbox_worker.py`). EngineManager
  keeps calling the constructor exactly as today (it passes neither), so its call site is
  unchanged; tests pass a stub Python + stub script through these kwargs. This is the test seam.
- `_chatterbox_venv_python()` resolves `backend/venv-chatterbox/Scripts/python.exe`
  (Windows) or `backend/venv-chatterbox/bin/python` (POSIX), relative to the backend root,
  unless overridden by the `worker_python` kwarg.
- `_worker_script()` resolves `backend/chatterbox_worker.py`, unless overridden by `worker_script`.
- `load()`:
  - If the venv Python is missing → raise `RuntimeError` with a clear message: *"Chatterbox
    isn't installed in its isolated environment. Run `python studio.py models` and select
    Chatterbox."*
  - Else spawn the worker via `subprocess.Popen([venv_py, worker_script], stdin=PIPE,
    stdout=PIPE, stderr=PIPE, text=True, env=<HF cache env>)`, where the env sets
    `HF_HOME`/`HUGGINGFACE_HUB_CACHE` to the same `backend/models/` cache (so weights are
    shared with the rest of the app). Send `{"op":"load","device":...}`, await the
    response line; on `ok:false` or non-zero exit, raise with captured stderr.
- `synthesize(req)`: under an instance lock, send the `synth` request with a freshly
  created temp `out_wav` path, read the response line, read the WAV bytes from `out_wav`
  (then delete it), and return `EngineResult(wav_bytes, sample_rate, duration_sec,
  inference_ms)`. On EOF/broken pipe/`ok:false`, mark unloaded and raise.
- `unload()`: best-effort send `{"op":"shutdown"}`, then terminate/wait the process; set
  state to unloaded.
- `is_loaded()`: true iff the worker process is alive and `load` succeeded.

### 3. `backend/requirements-chatterbox.txt`

Holds `chatterbox-tts>=0.1.7` (which pulls `transformers==5.2.0`, torch, etc.). The main
`backend/requirements.txt` **removes** `chatterbox-tts`, replacing it with a comment that
points to this file and `python studio.py models`.

### 4. `studio.py`

- `chatterbox_venv_python()` helper (mirrors `venv_python`, for `backend/venv-chatterbox`).
- In the model-download step (used by both `setup` and `models`): when the selection
  includes `chatterbox`, additionally:
  1. Create `backend/venv-chatterbox` if missing.
  2. Install the matching Torch wheel into it (reuse `envdetect.detect_cuda_tag` /
     `torch_index_url`, same logic as the main setup).
  3. `pip install -r backend/requirements-chatterbox.txt` into it.
  Model weights continue to download via the existing `download_models.py` in the main
  venv (it only needs `huggingface_hub`); the worker reads them from the shared
  `backend/models/` cache. `chatterbox` stays a valid key in the picker.

### 5. EngineManager / SynthService

No interface change. EngineManager keeps constructing `ChatterboxEngine` with the same
args it passes today (`model_id`, `default_language_id`, `default_cfg_weight`,
`default_exaggeration`, `watermark`, `device_request`). The proxy derives the worker/venv
paths itself from the backend root, so the constructor signature is unchanged. The
`app.py` line that reads `vibevoice_engine._model_manager` is unaffected (that's the
VibeVoice engine, not Chatterbox).

## Data Flow (one synth call)

1. SynthService resolves the request and calls `ChatterboxEngine.synthesize(EngineSynthRequest)`
   inside its single-worker executor (already serialized).
2. Proxy creates a temp `out_wav`, sends the `synth` JSON line to the worker's stdin.
3. Worker runs `model.generate(...)`, writes a 16-bit PCM WAV to `out_wav`, replies with a
   JSON line carrying `sample_rate`/`duration_sec`/`inference_ms`.
4. Proxy reads the WAV bytes from `out_wav`, deletes the temp file, returns `EngineResult`.

## Error Handling & Lifecycle

- **Missing venv-chatterbox** → `load()` raises the friendly install message.
- **Worker load failure** (bad install, OOM) → captured stderr is included in the raised error.
- **Worker crash / EOF mid-session** → proxy marks itself unloaded and raises; SynthService
  surfaces a clean error; a later `activate`/`load` respawns the worker.
- **Timeouts** — SynthService's existing `synth_timeout_s` wraps the call; on timeout the
  proxy is left in a state where the next call detects a stale/blocked worker and respawns.
- **One-engine-loaded rule** — `EngineManager.activate()` and app shutdown call `unload()`,
  which shuts the worker down and frees its VRAM.

## Testing

- **Proxy plumbing (no real Chatterbox):** a test points the proxy at a **stub worker
  script** run by the *main* venv's Python — the stub speaks the same JSON protocol,
  returns a canned response, and writes a tiny valid WAV. This exercises spawn → request →
  temp-WAV read → `EngineResult` end-to-end without `chatterbox-tts` installed. Achieved by
  making the worker-python and worker-script paths injectable on the engine (test seam).
- **Missing-venv error path:** unit test asserting the friendly `RuntimeError` when the
  venv Python doesn't exist.
- **`studio.py` helper:** unit test for `chatterbox_venv_python()` path shape (Windows vs POSIX).
- **Real generation:** manual verification (heavy, GPU) — documented run-through in the plan.

## Docs

- `README.md`: note that Chatterbox installs into its own environment via
  `python studio.py models` (select Chatterbox), because it requires a different
  transformers version than VibeVoice.
- `CLAUDE.md`: a short architecture note on the proxy + isolated worker and the
  transformers pin conflict (so future work doesn't try to merge the envs).

## File Summary

| Path | Change |
|------|--------|
| `backend/chatterbox_worker.py` | New — standalone stdio worker (runs in venv-chatterbox) |
| `backend/core/engines/chatterbox_engine.py` | Rewritten — proxy over the worker subprocess |
| `backend/requirements-chatterbox.txt` | New — `chatterbox-tts` isolated here |
| `backend/requirements.txt` | Modified — remove `chatterbox-tts`, add pointer comment |
| `studio.py` | Modified — build/install venv-chatterbox when Chatterbox is picked |
| `backend/tests/test_chatterbox_proxy.py` | New — stub-worker plumbing + missing-venv tests |
| `backend/tests/test_setup_helpers.py` | Modified — `chatterbox_venv_python()` path test |
| `README.md`, `CLAUDE.md` | Modified — document the isolated-env install + architecture |
