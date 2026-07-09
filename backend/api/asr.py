"""POST /api/asr/transcribe + GET /api/asr/status.

Weight downloads deliberately have no route here: `api/engines.py`'s
`/{name}/download` validates against `DOWNLOADABLE` rather than the engine
registry, so `/api/engines/whisper/download` already drives the shared
ModelDownloader — and the frontend's DownloadModelDialog works unchanged.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..services.synth_cache import SynthCache
from .deps import get_asr_service, get_synth_cache
from .schemas import AsrStatusResponse, AsrTranscribeResponse

log = logging.getLogger(__name__)
router = APIRouter(tags=["asr"])


@router.get("/api/asr/status", response_model=AsrStatusResponse)
def asr_status(svc=Depends(get_asr_service)) -> AsrStatusResponse:
    return AsrStatusResponse(**svc.status())


@router.post("/api/asr/transcribe", response_model=AsrTranscribeResponse)
def transcribe(
    file: UploadFile | None = File(None),
    cache_hash: str | None = Form(None),
    language: str | None = Form(None),
    timestamps: bool = Form(False),
    svc=Depends(get_asr_service),
    cache: SynthCache = Depends(get_synth_cache),
) -> AsrTranscribeResponse:
    """Transcribe an uploaded file, or audio already in the synthesis cache.

    Exactly one of `file` / `cache_hash` must be provided. The `cache_hash`
    form is how subtitles are produced for generated audio without a re-upload.
    """
    has_file = file is not None and bool(file.filename)
    has_hash = bool(cache_hash)
    if has_file == has_hash:
        raise HTTPException(
            status_code=422,
            detail="provide exactly one of 'file' or 'cache_hash'",
        )

    if has_hash:
        entry = cache.get(cache_hash)  # type: ignore[arg-type]
        if entry is None or not entry.wav_path.is_file():
            raise HTTPException(status_code=404, detail=f"clip not found: {cache_hash}")
        result = svc.transcribe_file(
            str(entry.wav_path), language=language, timestamps=timestamps
        )
        return AsrTranscribeResponse(**result.__dict__)

    # Uploaded file: persist to a temp path with its original suffix so the
    # service's extension check and librosa's decoder both see the real format.
    suffix = Path(file.filename or "").suffix  # type: ignore[union-attr]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        shutil.copyfileobj(file.file, tmp)  # type: ignore[union-attr]
    try:
        result = svc.transcribe_file(tmp_path, language=language, timestamps=timestamps)
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass

    return AsrTranscribeResponse(**result.__dict__)
