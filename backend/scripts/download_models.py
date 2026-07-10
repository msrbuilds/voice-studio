"""Voice Studio model downloader.

Pre-fetches selected TTS model weights into the project-local HF cache
(``backend/models/``). Run inside the venv:

    python -m backend.scripts.download_models --models kokoro,chatterbox
"""

from __future__ import annotations

import argparse
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent  # backend/

# Ordered: drives display order in the picker.
MODEL_CATALOG: dict[str, dict[str, str]] = {
    "vibevoice": {
        "repo_id": "vibevoice/VibeVoice-1.5B",
        "size": "~5.4 GB",
        "label": "VibeVoice-1.5B",
    },
    "kokoro": {
        "repo_id": "hexgrad/Kokoro-82M",
        "size": "~350 MB",
        "label": "Kokoro-82M",
    },
    "chatterbox": {
        "repo_id": "ResembleAI/chatterbox",
        "size": "~500 MB",
        "label": "Chatterbox V3",
    },
    "omnivoice": {
        "repo_id": "k2-fsa/OmniVoice",
        "size": "~3.3 GB",
        "label": "OmniVoice",
    },
    "voxcpm": {
        "repo_id": "openbmb/VoxCPM2",
        "size": "~5 GB",
        "label": "VoxCPM2",
    },
    "qwen": {
        "repo_id": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "size": "~3.5 GB",
        "label": "Qwen3-TTS CustomVoice",
    },
    # Speech-to-text, not a TTS engine — lives in AsrService, not EngineManager.
    # Listed here so it reuses the shared weight downloader.
    "whisper": {
        "repo_id": "openai/whisper-large-v3-turbo",
        "size": "~1.6 GB",
        "label": "Whisper large-v3-turbo (ASR)",
    },
}


def parse_model_selection(value: str) -> list[str]:
    """Parse a comma-separated list of engine keys; validate + de-dupe."""
    keys = [k.strip().lower() for k in value.split(",") if k.strip()]
    unknown = [k for k in keys if k not in MODEL_CATALOG]
    if unknown:
        raise ValueError(
            f"unknown model(s): {', '.join(unknown)}. "
            f"Valid keys: {', '.join(MODEL_CATALOG)}"
        )
    deduped: dict[str, None] = {}
    for k in keys:
        deduped.setdefault(k, None)
    return list(deduped)


def download_models(keys: list[str], models_dir: Path | str | None = None) -> None:
    """Download each selected engine's weights into the HF cache."""
    from backend.core.hf_paths import configure_hf_cache

    cache_dir = Path(models_dir) if models_dir else _BACKEND_ROOT / "models"
    configure_hf_cache(cache_dir)

    from huggingface_hub import snapshot_download

    for key in keys:
        spec = MODEL_CATALOG[key]
        print(f"[models] Downloading {spec['label']} ({spec['size']}) …", flush=True)
        snapshot_download(repo_id=spec["repo_id"])
        print(f"[models] {spec['label']} ready.", flush=True)


def list_catalog() -> list[dict[str, str]]:
    """The catalog as ordered, JSON-serializable rows.

    `studio.py` is stdlib-only and cannot import this module (it runs before the
    venv exists), so its model picker shells out to `--list` rather than keeping
    a hand-mirrored copy of the catalog — which is exactly what silently rotted
    when OmniVoice/VoxCPM/Qwen/Whisper were added.
    """
    return [
        {"key": key, "label": entry["label"], "size": entry["size"]}
        for key, entry in MODEL_CATALOG.items()
    ]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="download_models",
        description="Voice Studio by MSR — model downloader",
    )
    p.add_argument(
        "--models",
        help="comma-separated engine keys: " + ", ".join(MODEL_CATALOG),
    )
    p.add_argument("--models-dir", default=None, help="HF cache dir (default: backend/models)")
    p.add_argument(
        "--list",
        action="store_true",
        help="print the catalog as JSON and exit (used by studio.py's picker)",
    )
    args = p.parse_args(argv)

    if args.list:
        import json

        print(json.dumps(list_catalog()))
        return
    if not args.models:
        p.error("--models is required (or pass --list)")
    download_models(parse_model_selection(args.models), args.models_dir)


if __name__ == "__main__":
    main()
