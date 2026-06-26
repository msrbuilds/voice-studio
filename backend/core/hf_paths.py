"""Pin HuggingFace Hub cache to a project-local directory.

`huggingface_hub` reads its cache location from the `HF_HOME` env var
(or `HUGGINGFACE_HUB_CACHE` as a direct override). We set it at import
time so that any HF-using library — `transformers`, `kokoro`, etc. —
picks up the right path on first download.

This module MUST be imported before `transformers`, `vibevoice`,
`kokoro`, or anything that calls into `huggingface_hub`.
"""

from __future__ import annotations

import os
from pathlib import Path


def configure_hf_cache(models_dir: Path | str) -> Path:
    """Point HuggingFace Hub at a project-local directory.

    Idempotent: safe to call multiple times. Returns the resolved
    cache directory.
    """
    models_path = Path(models_dir).expanduser().resolve()
    models_path.mkdir(parents=True, exist_ok=True)

    # HF_HOME is the umbrella env var; the Hub uses $HF_HOME/hub/ as its
    # cache root. Setting both HF_HOME and HUGGINGFACE_HUB_CACHE makes
    # sure we cover every library version (some old versions only
    # respect HUGGINGFACE_HUB_CACHE).
    os.environ["HF_HOME"] = str(models_path)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(models_path / "hub")
    # Note: we intentionally do NOT set TRANSFORMERS_CACHE — that env
    # var is deprecated in transformers 5.x. HF_HOME is the umbrella
    # var that both huggingface_hub and transformers respect.

    # Some libraries inspect XDG_CACHE_HOME too. Point it at our
    # project-local cache root so any other XDG-aware tool (datasets,
    # tokenizers) also lands here.
    os.environ["XDG_CACHE_HOME"] = str(models_path)

    # Mirror sites (e.g. hf-mirror.com) — unset any pre-existing
    # redirect that might point at a different host.
    os.environ.pop("HF_ENDPOINT", None)

    return models_path