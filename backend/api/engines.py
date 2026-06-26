"""GET /api/engines, POST /api/engines/activate — list and switch engines."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.engine_manager import EngineLoadError, EngineManager, EngineNotFound
from .deps import get_chatterbox_installer, get_engine_manager

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engines", tags=["engines"])


class EngineInfoModel(BaseModel):
    name: str
    display_name: str
    description: str
    loaded: bool
    supports_voice_cloning: bool
    sample_rate: int | None
    max_speakers: int
    default_cfg_scale: float | None
    active: bool


class EnginesListResponse(BaseModel):
    active: str
    engines: list[EngineInfoModel]


class InstallStatusModel(BaseModel):
    state: str
    log: list[str]
    returncode: int | None


class ActivateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Engine id to activate")


def _to_model(info: dict) -> EngineInfoModel:
    return EngineInfoModel(
        name=info["name"],
        display_name=info["display_name"],
        description=info["description"],
        loaded=info["loaded"],
        supports_voice_cloning=info["supports_voice_cloning"],
        sample_rate=info.get("sample_rate"),
        max_speakers=info["max_speakers"],
        default_cfg_scale=info["default_cfg_scale"],
        active=info.get("active", False),
    )


@router.get("", response_model=EnginesListResponse)
def list_engines(em: EngineManager = Depends(get_engine_manager)) -> EnginesListResponse:
    """List all available engines and which one is active."""
    return EnginesListResponse(
        active=em.active_name,
        engines=[_to_model(info) for info in em.info()],
    )


@router.post("/activate", response_model=EngineInfoModel)
def activate_engine(
    body: Annotated[ActivateRequest, Body(...)],
    em: EngineManager = Depends(get_engine_manager),
) -> EngineInfoModel:
    """Switch the active TTS engine. Unloads the previous one; the new
    engine is loaded lazily on the next synthesize call.
    """
    try:
        em.activate(body.name)
    except EngineNotFound:
        raise HTTPException(status_code=404, detail=f"unknown engine: {body.name}")

    # Return the now-active engine's info. Don't load it here — the user
    # may want to switch and then run a generation; loading is lazy.
    engine = em.active_engine
    info = {**engine.info(), "name": engine.name, "active": True}
    return _to_model(info)


@router.post("/{name}/load", response_model=EngineInfoModel)
def load_engine(
    name: str,
    em: EngineManager = Depends(get_engine_manager),
) -> EngineInfoModel:
    """Eagerly load an engine (useful for the UI to show a spinner)."""
    try:
        engine = em.get_engine(name)
    except EngineNotFound:
        raise HTTPException(status_code=404, detail=f"unknown engine: {name}")
    try:
        if not engine.is_loaded():
            engine.load()
    except EngineLoadError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.exception("Engine load failed")
        raise HTTPException(
            status_code=500, detail=f"engine load failed: {exc}"
        )
    info = {**engine.info(), "name": engine.name, "active": engine.name == em.active_name}
    return _to_model(info)


@router.get("/{name}/install", response_model=InstallStatusModel)
def install_status(name: str, installer=Depends(get_chatterbox_installer)) -> InstallStatusModel:
    """Current install state for an installable engine (Chatterbox only)."""
    if name != "chatterbox":
        raise HTTPException(status_code=400, detail=f"{name} is not installable")
    return InstallStatusModel(**installer.status())


@router.post("/{name}/install", response_model=InstallStatusModel)
def start_install(name: str, installer=Depends(get_chatterbox_installer)) -> InstallStatusModel:
    """Start (or coalesce onto a running) install of the isolated Chatterbox env."""
    if name != "chatterbox":
        raise HTTPException(status_code=400, detail=f"{name} is not installable")
    return InstallStatusModel(**installer.start())
