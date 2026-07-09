"""Detect whether a model repo's weights are present in the local HF cache.

`snapshot_download(..., local_files_only=True)` returns the snapshot path when
every file of the repo's current revision is already cached, and raises
otherwise — so it doubles as a "fully downloaded?" probe with no network call.
"""

from __future__ import annotations


def model_downloaded(repo_id: str, ignore_patterns: list[str] | None = None) -> bool:
    """True if every non-ignored file of `repo_id`'s revision is cached locally.

    `ignore_patterns` must match what the downloader skipped, otherwise the probe
    would demand files that were never fetched (e.g. MusicGen's duplicate *.bin).
    """
    try:
        # Imported lazily so this module is import-safe before the HF cache
        # dir is configured (see backend/core/hf_paths.py).
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id, local_files_only=True,
                          ignore_patterns=ignore_patterns)
        return True
    except Exception:  # noqa: BLE001 — any failure means "not fully cached"
        return False
