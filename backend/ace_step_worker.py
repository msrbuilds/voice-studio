#!/usr/bin/env python3
"""ACE-Step 1.5 music worker — runs INSIDE the ACE-Step venv.

Newline-delimited JSON on stdin/stdout; all logging to stderr. Driven by
backend/core/engines/ace_step_engine.py.

Protocol:
  stdin  {"op":"load","device":"cuda"}
         {"op":"generate","out_dir":<path>,"batch_size":<int>,"caption":<str>,
          "lyrics":<str>,"instrumental":<bool>,"duration_sec":<float>,"steps":<int>,
          "seed":<int>,"bpm":<int|null>,"keyscale":<str>,"timesignature":<str>,
          "fade_in":<float>,"fade_out":<float>}
         {"op":"shutdown"}
  stdout {"ok":true,"device":"cuda"}                                   (load)
         {"ok":true,"clips":[{"file":"clip_0.wav","sample_rate":48000,
          "duration_sec":..,"seed":..}],"inference_ms":..}             (generate)
         {"ok":false,"error":".."}

The DiT runs WITHOUT the LM (llm_handler=None, thinking=False) for the v1
default. Weights are located via ACESTEP_CHECKPOINTS_DIR (set by the proxy).
"""
from __future__ import annotations

import json
import os
import sys
import time

_OUT = sys.stdout


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _reply(obj: dict) -> None:
    _OUT.write(json.dumps(obj) + "\n")
    _OUT.flush()


def _norm_device(device):
    d = (device or "auto").lower()
    if d == "auto":
        try:
            import torch
            d = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:  # noqa: BLE001
            d = "cpu"
    return d


class _Worker:
    def __init__(self) -> None:
        self._dit = None
        self._project_root = os.environ.get("ACESTEP_PROJECT_ROOT") or os.getcwd()

    def handle(self, req: dict) -> dict:
        op = req.get("op")
        if op == "load":
            return self._load(req)
        if op == "generate":
            return self._generate(req)
        if op == "shutdown":
            return {"ok": True}
        return {"ok": False, "error": f"unknown op: {op!r}"}

    def _load(self, req: dict) -> dict:
        device = _norm_device(req.get("device"))
        try:
            from acestep.handler import AceStepHandler
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"import acestep failed: {exc}"}
        try:
            self._dit = AceStepHandler()
            msg, ok = self._dit.initialize_service(
                project_root=self._project_root,
                config_path="acestep-v15-turbo",
                device=device,
                use_mlx_dit=False,
                offload_to_cpu=False,
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"init failed: {exc}"}
        if not ok:
            return {"ok": False, "error": f"init returned failure: {msg}"}
        _log(f"[acestep-worker] DiT initialized on {device}")
        return {"ok": True, "device": device}

    def _generate(self, req: dict) -> dict:
        if self._dit is None:
            return {"ok": False, "error": "model not loaded"}
        out_dir = req.get("out_dir")
        if not out_dir:
            return {"ok": False, "error": "out_dir required"}
        caption = (req.get("caption") or "").strip()
        if not caption:
            return {"ok": False, "error": "caption must be non-empty"}
        try:
            from acestep.inference import GenerationParams, GenerationConfig, generate_music
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"import inference failed: {exc}"}
        instrumental = bool(req.get("instrumental"))
        lyrics = "[Instrumental]" if instrumental else (req.get("lyrics") or "[Instrumental]")
        batch_size = max(1, min(4, int(req.get("batch_size") or 1)))
        base_seed = int(req.get("seed") if req.get("seed") is not None else -1)
        params = GenerationParams(
            task_type="text2music",
            caption=caption,
            lyrics=lyrics,
            instrumental=instrumental,
            duration=float(req.get("duration_sec") or 30.0),
            inference_steps=int(req.get("steps") or 8),
            seed=base_seed,
            bpm=(int(req["bpm"]) if req.get("bpm") else None),
            keyscale=(req.get("keyscale") or ""),
            timesignature=(req.get("timesignature") or ""),
            fade_in_duration=float(req.get("fade_in") or 0.0),
            fade_out_duration=float(req.get("fade_out") or 0.0),
            thinking=False,  # no LM
        )
        config = GenerationConfig(batch_size=batch_size, audio_format="wav")
        import glob
        import shutil
        import tempfile
        work = tempfile.mkdtemp(prefix="acestep-gen-")
        t0 = time.perf_counter()
        try:
            generate_music(self._dit, None, params, config, save_dir=work)
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(work, ignore_errors=True)
            return {"ok": False, "error": f"generate failed: {exc}"}
        inference_ms = int((time.perf_counter() - t0) * 1000)
        wavs = sorted(glob.glob(os.path.join(work, "**", "*.wav"), recursive=True))
        if not wavs:
            shutil.rmtree(work, ignore_errors=True)
            return {"ok": False, "error": "no audio produced"}
        os.makedirs(out_dir, exist_ok=True)
        try:
            import soundfile as sf
        except Exception:  # noqa: BLE001
            sf = None
        clips = []
        for i, w in enumerate(wavs[:batch_size]):
            dest = os.path.join(out_dir, f"clip_{i}.wav")
            shutil.copyfile(w, dest)
            sr, dur = 48000, float(req.get("duration_sec") or 0.0)
            if sf is not None:
                try:
                    info = sf.info(dest)
                    sr, dur = int(info.samplerate), float(info.frames) / float(info.samplerate)
                except Exception:  # noqa: BLE001
                    pass
            # Per-clip seed: base_seed for clip 0 when fixed, else -1 (informational).
            seed = base_seed if (base_seed >= 0 and i == 0) else -1
            clips.append({"file": f"clip_{i}.wav", "sample_rate": sr, "duration_sec": dur, "seed": seed})
        shutil.rmtree(work, ignore_errors=True)
        return {"ok": True, "clips": clips, "inference_ms": inference_ms}


def main() -> int:
    global _OUT
    _OUT = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    try:
        os.dup2(2, 1)
    except OSError:
        pass
    sys.stdout = sys.stderr
    worker = _Worker()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _reply({"ok": False, "error": f"bad json: {exc}"})
            continue
        try:
            resp = worker.handle(req)
        except Exception as exc:  # noqa: BLE001
            resp = {"ok": False, "error": f"worker exception: {exc}"}
        _reply(resp)
        if req.get("op") == "shutdown":
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
