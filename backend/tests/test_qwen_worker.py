"""Tests for the Qwen worker's generate_custom_voice dispatch (fake model)."""

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _load_worker():
    import backend.qwen_worker as w
    return importlib.reload(w)


def test_basic_kwargs():
    w = _load_worker()
    k = w._build_generate_kwargs(
        {"text": "hi", "speaker": "Vivian", "language": "English"}
    )
    assert k["text"] == "hi"
    assert k["speaker"] == "Vivian"
    assert k["language"] == "English"
    assert "instruct" not in k
    assert k["max_new_tokens"] > 0  # auto-computed


def test_language_defaults_to_auto():
    w = _load_worker()
    k = w._build_generate_kwargs({"text": "hi", "speaker": "Aiden"})
    assert k["language"] == "Auto"


def test_instruct_passed_when_present():
    w = _load_worker()
    k = w._build_generate_kwargs(
        {"text": "hi", "speaker": "Vivian", "instruct": "Very happy."}
    )
    assert k["instruct"] == "Very happy."


def test_empty_instruct_omitted():
    w = _load_worker()
    k = w._build_generate_kwargs(
        {"text": "hi", "speaker": "Vivian", "instruct": "   "}
    )
    assert "instruct" not in k


def test_quality_kwargs_passed_through_only_when_set():
    w = _load_worker()
    k = w._build_generate_kwargs(
        {"text": "hi", "speaker": "Vivian",
         "temperature": 0.8, "top_p": 0.9, "top_k": 40, "repetition_penalty": 1.1}
    )
    assert k["temperature"] == 0.8
    assert k["top_p"] == 0.9
    assert k["top_k"] == 40
    assert k["repetition_penalty"] == 1.1
    # seed is NOT a generate kwarg (handled via torch.manual_seed in _synth)
    assert "seed" not in k


def test_missing_speaker_raises():
    w = _load_worker()
    try:
        w._build_generate_kwargs({"text": "hi"})
    except ValueError:
        return
    raise AssertionError("expected ValueError when speaker is missing")


def test_max_new_tokens_scales_with_text():
    w = _load_worker()
    short = w._build_generate_kwargs({"text": "hi", "speaker": "Vivian"})["max_new_tokens"]
    long = w._build_generate_kwargs({"text": "x" * 1000, "speaker": "Vivian"})["max_new_tokens"]
    assert long >= short


def test_synth_end_to_end_with_fake_model(tmp_path):
    import numpy as np

    w = _load_worker()
    worker = w._Worker()

    class _FakeModel:
        def generate_custom_voice(self, **kwargs):
            return [np.zeros(24000, dtype=np.float32)], 24000  # 1s @ 24k

    worker._model = _FakeModel()
    out = tmp_path / "o.wav"
    resp = worker._synth({"text": "hi", "speaker": "Vivian", "out_wav": str(out)})
    assert resp["ok"] is True
    assert resp["sample_rate"] == 24000
    assert abs(resp["duration_sec"] - 1.0) < 0.01
    assert out.is_file() and out.stat().st_size > 0
