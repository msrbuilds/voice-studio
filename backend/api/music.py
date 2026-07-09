"""POST /api/music/generate + WAV/FLAC download.

Engine-agnostic: SynthService resolves whichever registered engine reports
supports_music(). With no music engine installed, generate returns 503.
"""
from __future__ import annotations

import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from ..core.exceptions import BackendError
from ..services.synth_cache import SynthCache
from ..services.synthesize import MusicRequest, SynthService
from .deps import get_synth_cache, get_synth_service
from .schemas import MusicClipModel, MusicGenerateResponse, MusicRequestBody

log = logging.getLogger(__name__)
router = APIRouter(tags=["music"])


@router.post("/api/music/generate", response_model=MusicGenerateResponse)
def generate_music(
    body: MusicRequestBody,
    svc: SynthService = Depends(get_synth_service),
) -> MusicGenerateResponse:
    try:
        results = svc.synthesize_music(MusicRequest(
            caption=body.caption, lyrics=body.lyrics, instrumental=body.instrumental,
            duration_sec=body.duration_sec, steps=body.steps, seed=body.seed, bpm=body.bpm,
            key=body.key, time_signature=body.time_signature,
            fade_in=body.fade_in, fade_out=body.fade_out, count=body.count,
            force_regenerate=body.force_regenerate,
        ))
    except BackendError:
        raise
    return MusicGenerateResponse(clips=[
        MusicClipModel(
            cache_hash=r.cache_hash or "", sample_rate=r.sample_rate,
            duration_sec=r.duration_sec, inference_ms=r.inference_ms,
        )
        for r in results
    ])


@router.get("/api/music/download/{content_hash}")
def download_music(
    content_hash: str,
    format: str = Query("wav", pattern="^(wav|flac)$"),
    cache: SynthCache = Depends(get_synth_cache),
) -> Response:
    entry = cache.get(content_hash)
    if entry is None or not entry.wav_path.is_file():
        raise HTTPException(status_code=404, detail=f"clip not found: {content_hash}")
    filename = f"music-{content_hash[:8]}.{format}"
    if format == "wav":
        return Response(
            content=entry.wav_path.read_bytes(), media_type="audio/wav",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    # FLAC: convert the cached WAV with soundfile (no ffmpeg).
    import soundfile as sf

    data, sr = sf.read(str(entry.wav_path))
    buf = io.BytesIO()
    sf.write(buf, data, sr, format="FLAC")
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="audio/flac",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
