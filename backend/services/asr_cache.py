"""On-disk cache for transcription results.

Not `SynthCache`: that stores WAV bytes keyed to a synthesis request. ASR
results are small JSON documents (text + language + segments), so they get a
much simpler store — one JSON file per hash, written atomically.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class AsrCache:
    def __init__(self, cache_dir: Path | str, enabled: bool = True) -> None:
        self._dir = Path(cache_dir)
        self._enabled = enabled
        if self._enabled:
            self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def dir(self) -> Path:
        return self._dir

    def _path(self, content_hash: str) -> Path:
        return self._dir / f"{content_hash}.json"

    def __len__(self) -> int:
        if not self._enabled:
            return 0
        return sum(1 for _ in self._dir.glob("*.json"))

    def get(self, content_hash: str) -> dict[str, Any] | None:
        if not self._enabled:
            return None
        p = self._path(content_hash)
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, content_hash: str, payload: dict[str, Any]) -> None:
        if not self._enabled:
            return
        p = self._path(content_hash)
        tmp = p.with_name(f"{p.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, p)
        except OSError as exc:
            log.debug("asr cache put failed: %s", exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def clear(self) -> int:
        if not self._enabled:
            return 0
        n = 0
        for f in self._dir.glob("*.json"):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
        return n

    def total_size(self) -> int:
        if not self._enabled:
            return 0
        return sum(f.stat().st_size for f in self._dir.glob("*.json") if f.is_file())
