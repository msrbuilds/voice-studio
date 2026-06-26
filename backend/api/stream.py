"""WebSocket /api/stream — low-latency chunked TTS.

Protocol:
  Client → server (one text frame after connect):
    {
      "text": "...",                  # required
      "voice": "af_heart",            # required for voice-catalog engines
      "engine": "kokoro",             # optional; defaults to active engine
      "speed": 1.0,                   # optional
      "cfg_weight": 0.5,              # optional (Chatterbox)
      "exaggeration": 0.5,            # optional (Chatterbox)
      "language_id": "en"             # optional
    }

  Server → client:
    1. Text frame: {"event": "start", "sample_rate": 24000,
                    "sample_width": 2, "channels": 1, "engine": "kokoro"}
    2. Binary frames: one per audio chunk, each a complete WAV (header
       + PCM int16). The client strips headers and concatenates PCM.
    3. Text frame: {"event": "end", "inference_ms": 1234,
                    "duration_sec": 3.45}

  Errors:
    - {"event": "error", "message": "..."} before close
    - Close codes:
        1000 normal end
        1008 engine does not support streaming
        1011 server error during inference
        4001 invalid request payload

The route is the streaming counterpart of POST /api/synthesize. It does
NOT write to the per-segment cache (caching mid-stream would add I/O
jitter). Use the non-streaming path when you want a cached result.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ..core.exceptions import (
    BackendError,
    EngineStreamingNotSupported,
    SynthesisTimeout,
    TextInvalid,
    VoiceNotFound,
)
from ..services.synthesize import SynthRequest, SynthService, Speaker as ServiceSpeaker
from .deps import get_synth_service

log = logging.getLogger(__name__)

router = APIRouter(tags=["stream"])


@router.websocket("/api/stream")
async def stream_synthesize(
    ws: WebSocket,
    svc: SynthService = Depends(get_synth_service),
) -> None:
    """Stream audio chunks for a single-segment synthesis request."""
    await ws.accept()

    # --- 1. Parse the request ---
    try:
        raw = await ws.receive_text()
    except WebSocketDisconnect:
        return
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        await _send_error(ws, 4001, f"invalid JSON: {exc}")
        return

    text = (payload.get("text") or "").strip()
    voice = (payload.get("voice") or "").strip()
    if not text:
        await _send_error(ws, 4001, "missing 'text'")
        return
    if not voice:
        await _send_error(ws, 4001, "missing 'voice'")
        return

    engine = payload.get("engine") or None
    speed = float(payload.get("speed") or 1.0)
    cfg_weight = payload.get("cfg_weight")
    exaggeration = payload.get("exaggeration")
    language_id = payload.get("language_id") or None

    req = SynthRequest(
        text=text,
        speakers=[ServiceSpeaker(name="stream", voice_id=voice)],
        engine=engine,
        speed=speed,
        cfg_weight=cfg_weight,
        exaggeration=exaggeration,
        language_id=language_id,
    )

    # --- 2. Resolve engine + validate, then start the stream ---
    try:
        # Resolve target engine upfront so we can advertise supports_streaming
        # + sample_rate in the "start" frame.
        target_engine = (
            svc._engines.get_engine(engine) if engine else svc._engines.active_engine
        )
        if not target_engine.supports_streaming():
            await _send_error(
                ws,
                1008,
                f"{target_engine.display_name} does not support streaming synthesis",
            )
            return
        sr = target_engine.sample_rate()
        engine_name = target_engine.name

        # "start" frame
        await ws.send_json({
            "event": "start",
            "sample_rate": sr,
            "sample_width": 2,
            "channels": 1,
            "engine": engine_name,
            "cache": "bypass",
        })
    except Exception as exc:  # noqa: BLE001
        await _send_error(ws, 1011, f"startup failed: {exc}")
        return

    # --- 3. Stream chunks ---
    final_inference_ms = 0
    try:
        for chunk in svc.stream_synthesize(req):
            if chunk.is_final:
                # Terminator: empty wav_bytes, real inference_ms.
                final_inference_ms = chunk.inference_ms
                continue
            # Send the chunk's WAV bytes raw. Client strips headers.
            await ws.send_bytes(chunk.wav_bytes)
    except EngineStreamingNotSupported as exc:
        await _send_error(ws, 1008, str(exc))
        return
    except VoiceNotFound as exc:
        await _send_error(ws, 4001, str(exc))
        return
    except TextInvalid as exc:
        await _send_error(ws, 4001, str(exc))
        return
    except SynthesisTimeout as exc:
        await _send_error(ws, 1011, f"timeout: {exc}")
        return
    except BackendError as exc:
        await _send_error(ws, 1011, f"{exc.code}: {exc.message}")
        return
    except WebSocketDisconnect:
        # Client went away mid-stream; just close.
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("Streaming synthesis failed")
        await _send_error(ws, 1011, f"{type(exc).__name__}: {exc}")
        return

    # --- 4. "end" frame + close ---
    try:
        await ws.send_json({
            "event": "end",
            "inference_ms": final_inference_ms,
        })
    except WebSocketDisconnect:
        pass
    try:
        await ws.close(code=1000)
    except Exception:  # noqa: BLE001
        pass


async def _send_error(ws: WebSocket, code: int, message: str) -> None:
    """Best-effort: send a JSON error frame, then close with `code`."""
    try:
        await ws.send_json({"event": "error", "message": message})
    except Exception:  # noqa: BLE001
        pass
    try:
        await ws.close(code=code)
    except Exception:  # noqa: BLE001
        pass
