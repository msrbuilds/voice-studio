"""POST /api/music/generate — text-to-music via the ACE-Step engine."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Response

from ..core.exceptions import BackendError
from ..services.synthesize import MusicRequest, SynthService
from .deps import get_synth_service
from .schemas import MusicRequestBody

log = logging.getLogger(__name__)
router = APIRouter(tags=["music"])


@router.post("/api/music/generate", responses={200: {"content": {"audio/wav": {}}}})
def generate_music(
    body: MusicRequestBody,
    svc: SynthService = Depends(get_synth_service),
) -> Response:
    try:
        result = svc.synthesize_music(MusicRequest(
            caption=body.caption, lyrics=body.lyrics, instrumental=body.instrumental,
            duration_sec=body.duration_sec, steps=body.steps, seed=body.seed,
            bpm=body.bpm, force_regenerate=body.force_regenerate,
        ))
    except BackendError:
        raise
    headers = {
        "X-Sample-Rate": str(result.sample_rate),
        "X-Inference-Ms": str(result.inference_ms),
        "X-Audio-Duration-Sec": f"{result.duration_sec:.3f}",
        "X-Cache": "hit" if result.cache_hit else "miss",
        "X-Engine": "acestep",
        "Content-Disposition": f'attachment; filename="acestep-{uuid.uuid4().hex[:8]}.wav"',
    }
    if result.cache_hash:
        headers["X-Cache-Hash"] = result.cache_hash
    return Response(content=result.wav_bytes, media_type="audio/wav", headers=headers)
