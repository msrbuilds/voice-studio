"""ACE-Step 1.5 music engine — ISOLATED-ENV PROXY.

ACE-Step hard-requires torch 2.7+cu128, incompatible with the main venv. The
model runs in its own uv-sync'd venv inside the vendored repo. This proxy drives
backend/ace_step_worker.py, exposing the normal Engine surface plus
supports_music(). It generates music (caption/lyrics/duration), not speech.

The subprocess internals (_exchange / _start_stderr_drain / _recent_stderr /
_kill / unload / is_loaded) mirror qwen_engine.py verbatim.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from . import Engine, EngineResult, EngineSynthRequest

log = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # backend/
_VENDOR_REPO = _BACKEND_ROOT / "vendor" / "ace-step"


def _default_worker_python() -> Path:
    venv = _VENDOR_REPO / ".venv"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _default_worker_script() -> Path:
    return _BACKEND_ROOT / "ace_step_worker.py"


class AceStepEngine(Engine):
    name = "acestep"
    display_name = "ACE-Step 1.5 (Music)"
    license = "MIT"
    model_url = "https://huggingface.co/ACE-Step/Ace-Step1.5"
    description = (
        "Text-to-music generation (stereo 48 kHz). Type a style caption + "
        "optional lyrics; runs in its own isolated environment. ~6 GB core "
        "weights download on first use."
    )

    def __init__(
        self,
        device_request: str = "cuda",
        worker_python: Path | None = None,
        worker_script: Path | None = None,
    ) -> None:
        self._model_id = "ACE-Step/Ace-Step1.5"
        self._device_request = device_request
        self._worker_python = Path(worker_python) if worker_python else _default_worker_python()
        self._worker_script = Path(worker_script) if worker_script else _default_worker_script()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()
        self._stderr_tail: collections.deque[str] = collections.deque(maxlen=200)
        self._stderr_thread: threading.Thread | None = None
        self._resolved_device: str | None = None

    # -- lifecycle
    def load(self) -> None:
        with self._load_lock:
            if self.is_loaded():
                return
            if not self._worker_python.is_file():
                raise RuntimeError(
                    "ACE-Step isn't installed in its isolated environment. "
                    "Run `python studio.py install-acestep` (or click Install in the UI)."
                )
            env = dict(os.environ)
            models_dir = _BACKEND_ROOT / "models"
            env["ACESTEP_CHECKPOINTS_DIR"] = str(models_dir / "acestep")
            env["ACESTEP_PROJECT_ROOT"] = str(_VENDOR_REPO)
            env["HF_HOME"] = str(models_dir)
            log.info("Spawning ACE-Step worker: %s %s", self._worker_python, self._worker_script)
            self._proc = subprocess.Popen(
                [str(self._worker_python), str(self._worker_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=str(_VENDOR_REPO),
            )
            self._start_stderr_drain()
            resp = self._exchange({"op": "load", "device": self._device_request})
            if not resp.get("ok"):
                err = resp.get("error", "unknown error")
                self._kill()
                raise RuntimeError(f"ACE-Step worker failed to load: {err}")
            self._resolved_device = resp.get("device") or self._device_request

    def unload(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.poll() is None:
                self._exchange({"op": "shutdown"}, expect_reply=False)
        except Exception:  # noqa: BLE001
            pass
        self._kill()

    def is_loaded(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def installed(self) -> bool:
        return self._ready_marker().is_file()

    def _ready_marker(self) -> Path:
        return _VENDOR_REPO / ".acestep-ready"

    def downloaded(self) -> bool:
        base = _BACKEND_ROOT / "models" / "acestep"
        return all(
            (base / d).is_dir()
            for d in ("acestep-v15-turbo", "vae", "Qwen3-Embedding-0.6B")
        )

    def lm_downloaded(self) -> bool:
        lm = _BACKEND_ROOT / "models" / "acestep" / "acestep-5Hz-lm-0.6B"
        return (lm / "config.json").is_file()

    def engine_info(self) -> dict[str, Any]:
        device = self._resolved_device or self._device_request
        return {
            "model_id": self._model_id,
            "device": device,
            "dtype": "bfloat16",
            "attn_implementation": "sdpa",
        }

    # -- capabilities
    def sample_rate(self) -> int:
        return 48000

    def max_speakers(self) -> int:
        return 0

    def supports_voice_cloning(self) -> bool:
        return False

    def supports_music(self) -> bool:
        return True

    def default_cfg_scale(self) -> float | None:
        return None

    def available_voices(self) -> list:
        return []

    # -- generation
    def _build_generate_msg(self, req: EngineSynthRequest, out_dir: str, batch_size: int) -> dict:
        caption = (req.caption or "").strip()
        if not caption:
            raise ValueError("caption must be non-empty for music generation")
        return {
            "op": "generate",
            "out_dir": out_dir,
            "batch_size": int(batch_size),
            "caption": caption,
            "lyrics": (req.lyrics or ""),
            "instrumental": bool(req.instrumental),
            "duration_sec": float(req.duration_sec or 30.0),
            "steps": int(req.music_steps or 8),
            "seed": int(req.music_seed if req.music_seed is not None else -1),
            "bpm": (int(req.bpm) if req.bpm else None),
            "keyscale": (req.keyscale or ""),
            "timesignature": (req.timesignature or ""),
            "fade_in": float(req.fade_in or 0.0),
            "fade_out": float(req.fade_out or 0.0),
            "thinking": bool(req.thinking),
        }

    def generate_batch(self, req: EngineSynthRequest, count: int) -> list[EngineResult]:
        if not self.is_loaded():
            raise RuntimeError("ACE-Step worker is not loaded")
        import shutil as _sh

        out_dir = tempfile.mkdtemp(prefix="acestep-out-")
        try:
            resp = self._exchange(self._build_generate_msg(req, out_dir, count))
            if not resp.get("ok"):
                raise RuntimeError(
                    f"ACE-Step generate failed: {resp.get('error', 'unknown error')}"
                )
            results: list[EngineResult] = []
            for clip in resp.get("clips", []):
                path = Path(out_dir) / clip["file"]
                results.append(EngineResult(
                    wav_bytes=path.read_bytes(),
                    sample_rate=int(clip.get("sample_rate", self.sample_rate())),
                    duration_sec=float(clip.get("duration_sec", 0.0)),
                    inference_ms=int(resp.get("inference_ms", 0)),
                ))
            if not results:
                raise RuntimeError("ACE-Step returned no clips")
            return results
        finally:
            _sh.rmtree(out_dir, ignore_errors=True)

    def synthesize(self, req: EngineSynthRequest) -> EngineResult:
        # Single-clip convenience (music path uses generate_batch).
        return self.generate_batch(req, 1)[0]

    def inspire(self, query: str, instrumental: bool, language: str | None) -> dict:
        """Run the LM 'Inspiration' flow (create_sample) → a blueprint dict."""
        if not self.is_loaded():
            self.load()
        resp = self._exchange({
            "op": "inspire", "query": query,
            "instrumental": bool(instrumental), "language": (language or ""),
        })
        if not resp.get("ok"):
            raise RuntimeError(f"ACE-Step inspire failed: {resp.get('error', 'unknown error')}")
        return resp.get("blueprint", {})

    # -- internals (identical to QwenEngine)
    def _exchange(self, msg: dict, expect_reply: bool = True) -> dict:
        with self._lock:
            if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
                raise RuntimeError("ACE-Step worker is not running")
            try:
                self._proc.stdin.write(json.dumps(msg) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._kill()
                raise RuntimeError(f"ACE-Step worker pipe broke: {exc}") from exc
            if not expect_reply:
                return {"ok": True}
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    if self._stderr_thread is not None:
                        self._stderr_thread.join(timeout=1.0)
                    stderr = self._recent_stderr()
                    self._kill()
                    raise RuntimeError(
                        "ACE-Step worker closed unexpectedly" + (f": {stderr}" if stderr else "")
                    )
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    log.debug("acestep worker non-protocol stdout: %s", stripped[:200])
                    continue

    def _start_stderr_drain(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        self._stderr_tail.clear()

        def _drain(stream, sink) -> None:
            try:
                for line in stream:
                    sink.append(line.rstrip("\n"))
            except Exception:  # noqa: BLE001
                pass

        thread = threading.Thread(target=_drain, args=(proc.stderr, self._stderr_tail), daemon=True)
        thread.start()
        self._stderr_thread = thread

    def _recent_stderr(self) -> str:
        return "\n".join(self._stderr_tail).strip()

    def _kill(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:  # noqa: BLE001
            pass
