"""POST /api/music/generate + FLAC download — ACE-Step music."""
from __future__ import annotations

import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from ..core.exceptions import BackendError
from ..services.synth_cache import SynthCache
from ..services.synthesize import MusicRequest, SynthService
from .deps import get_synth_cache, get_synth_service
from .schemas import (
    MusicBlueprintResponse,
    MusicClipModel,
    MusicGenerateResponse,
    MusicInspireBody,
    MusicRequestBody,
)

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
            thinking=body.thinking, force_regenerate=body.force_regenerate,
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
    filename = f"acestep-{content_hash[:8]}.{format}"
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


@router.post("/api/music/inspire", response_model=MusicBlueprintResponse)
def inspire_music(
    body: MusicInspireBody,
    svc: SynthService = Depends(get_synth_service),
) -> MusicBlueprintResponse:
    try:
        bp = svc.inspire_music(body.query, body.instrumental, body.language or None)
    except BackendError:
        raise
    return MusicBlueprintResponse(**bp)


@router.get("/api/music/lm/status")
def lm_status(request: Request) -> dict:
    em = request.app.state.engine_manager
    dl = request.app.state.lm_downloader
    try:
        downloaded = em.get_engine("acestep").lm_downloaded()
    except Exception:  # noqa: BLE001
        downloaded = False
    return {"downloaded": downloaded, **dl.status()}


@router.post("/api/music/lm/download")
def lm_download(request: Request) -> dict:
    return request.app.state.lm_downloader.start()
