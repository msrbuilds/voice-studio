"""Speech-to-text abstraction.

Deliberately separate from `core.engines.Engine` (text -> audio). ASR runs the
opposite direction (audio -> text), so folding it into the TTS ABC would force
every speech engine to grow methods it can't implement, and would surface
Whisper in the UI's engine selector where it cannot synthesize.

An AsrEngine is constructed at app start but loaded lazily on first use, the
same lifecycle as the TTS engines.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class AsrSegment:
    """One timestamped span of transcript."""

    start: float
    end: float
    text: str


@dataclass
class AsrRequest:
    """A transcription request.

    `audio_path` always points at 16 kHz mono audio — AsrService does the
    decode/resample so engines never deal with arbitrary containers.
    """

    audio_path: str
    language: str | None = None   # None or "auto" => detect
    timestamps: bool = False


@dataclass
class AsrResult:
    text: str
    language: str                 # detected or forced, e.g. "en"
    duration_sec: float
    inference_ms: int
    segments: list[AsrSegment] = field(default_factory=list)


class AsrEngine(abc.ABC):
    """Abstract base class for a speech-to-text engine."""

    name: str = "asr"
    display_name: str = "ASR"
    description: str = ""
    license: str = ""
    model_url: str = ""

    @abc.abstractmethod
    def load(self) -> None: ...

    @abc.abstractmethod
    def unload(self) -> None: ...

    @abc.abstractmethod
    def is_loaded(self) -> bool: ...

    @abc.abstractmethod
    def transcribe(self, req: AsrRequest) -> AsrResult: ...

    def sample_rate(self) -> int:
        """Sample rate the engine expects its input audio at."""
        return 16000

    def downloaded(self) -> bool:
        """True when the weights are present locally."""
        return True

    def languages(self) -> list[dict[str, str]]:
        """UI language options as [{"code","label"}]. Empty when unknown."""
        return []


__all__ = ["AsrEngine", "AsrRequest", "AsrResult", "AsrSegment"]
