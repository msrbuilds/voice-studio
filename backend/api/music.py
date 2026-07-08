"""POST /api/music/generate + FLAC download — ACE-Step music."""
from __future__ import annotations

import io
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

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
    MusicUploadResponse,
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["music"])


def _music_src_path(uploads_dir, src_audio_id: str) -> Path | None:
    """Return the re-encoded source WAV for a cover/repaint id, or None."""
    if not src_audio_id:
        return None
    p = Path(uploads_dir) / "music" / f"{src_audio_id}.wav"
    return p if p.is_file() else None


@router.post("/api/music/upload", response_model=MusicUploadResponse, status_code=201)
def upload_music_source(request: Request, file: UploadFile = File(...)) -> MusicUploadResponse:
    import uuid

    import soundfile as sf

    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        data, sr = sf.read(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"unsupported/undecodable audio (use WAV/FLAC/OGG): {exc}",
        ) from exc
    uploads_dir = request.app.state.settings.uploads_dir
    dest_dir = Path(uploads_dir) / "music"
    dest_dir.mkdir(parents=True, exist_ok=True)
    sid = uuid.uuid4().hex
    dest = dest_dir / f"{sid}.wav"
    sf.write(str(dest), data, sr, format="WAV")
    duration = float(len(data)) / float(sr) if sr else 0.0
    return MusicUploadResponse(id=sid, name=(file.filename or "source.wav"), duration_sec=duration)


@router.get("/api/music/source/{src_audio_id}")
def get_music_source(src_audio_id: str, request: Request) -> Response:
    p = _music_src_path(request.app.state.settings.uploads_dir, src_audio_id)
    if p is None:
        raise HTTPException(status_code=404, detail="source not found")
    return FileResponse(str(p), media_type="audio/wav")


@router.post("/api/music/generate", response_model=MusicGenerateResponse)
def generate_music(
    body: MusicRequestBody,
    request: Request,
    svc: SynthService = Depends(get_synth_service),
) -> MusicGenerateResponse:
    src_path = ""
    if body.task_type in ("cover", "repaint"):
        resolved = _music_src_path(request.app.state.settings.uploads_dir, body.src_audio_id)
        if resolved is None:
            raise HTTPException(status_code=400, detail="source audio not found for cover/repaint")
        src_path = str(resolved)
    try:
        results = svc.synthesize_music(MusicRequest(
            caption=body.caption, lyrics=body.lyrics, instrumental=body.instrumental,
            duration_sec=body.duration_sec, steps=body.steps, seed=body.seed, bpm=body.bpm,
            key=body.key, time_signature=body.time_signature,
            fade_in=body.fade_in, fade_out=body.fade_out, count=body.count,
            thinking=body.thinking,
            task_type=body.task_type, src_audio=src_path, src_audio_id=body.src_audio_id,
            cover_strength=body.cover_strength,
            repaint_start=body.repaint_start, repaint_end=body.repaint_end,
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
