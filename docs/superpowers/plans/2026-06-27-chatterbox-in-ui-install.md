# In-UI Chatterbox Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users install the isolated Chatterbox environment from the engine selector — an `installed` flag on engines, a background install manager that runs `studio.py`'s installer as a subprocess, install endpoints, and a full-log modal.

**Architecture:** `/api/engines` gains an `installed` flag (Chatterbox = its venv exists). A thread-safe `ChatterboxInstaller` singleton on `app.state` runs `python studio.py install-chatterbox` in a background thread, streaming its merged stdout/stderr into a capped log buffer with a `not_installed → installing → installed | error` state machine. `POST/GET /api/engines/{name}/install` drive it; a React modal POSTs the install and polls the log to completion.

**Tech Stack:** FastAPI + Pydantic, Python stdlib (`subprocess`, `threading`), pytest + `fastapi.testclient`; React + TypeScript + Tailwind, `lucide-react`.

---

## Context for the implementer

- Repo root `f:\Vibe Projects\vibe-podcast`. Backend package `backend`; main venv Python `backend\venv\Scripts\python.exe`. Run tests from repo root:
  `backend\venv\Scripts\python.exe -m pytest backend/tests/<file>.py -v`
- Existing test files insert the repo root into `sys.path` (`parents[2]`) so `import studio` and `from backend... import` resolve. Copy that 2-line pattern in new test files.
- `Engine` ABC: `backend/core/engines/__init__.py` — `info()` returns a dict of capabilities; add to it here.
- `ChatterboxEngine` (`backend/core/engines/chatterbox_engine.py`) is a proxy; it has `self._worker_python: Path` (the isolated venv's Python). "Installed" == that file exists.
- API: `backend/api/engines.py` (router `/api/engines`, `EngineInfoModel`, `_to_model`). Dependencies in `backend/api/deps.py` follow the `get_engine_manager(request)` pattern reading `request.app.state.*`. Singletons are built in `backend/app.py::create_app` and assigned to `app.state`.
- `studio.py` already has `chatterbox_venv_python(repo_root)`, `_ensure_chatterbox_env()`, `_run`, `REPO_ROOT`, `BACKEND_DIR`, and a `main(argv)` with `add_subparsers(dest="command")` dispatching `setup`/`start`/`models`.
- Frontend: `EngineInfo` type in `frontend/src/types/models.ts`; API wrappers in `frontend/src/lib/api.ts`; engine UI in `frontend/src/components/EngineSelector.tsx`; it's wired `App.tsx → ActionBar.tsx → EngineSelector` (props `onSelect`/`onLoad`). Frontend has no unit tests — verify with `cd frontend && npm run typecheck`.

## File Structure

| Path | Responsibility |
|------|----------------|
| `backend/core/engines/__init__.py` | `Engine.installed()` (base True) + `installed` in `info()` |
| `backend/core/engines/chatterbox_engine.py` | override `installed()` from venv presence |
| `studio.py` | `_ensure_chatterbox_env()` returns bool; `install-chatterbox` subcommand |
| `backend/services/chatterbox_install.py` | `ChatterboxInstaller` state machine + default subprocess runner |
| `backend/api/deps.py` | `get_chatterbox_installer` |
| `backend/api/engines.py` | `installed` in model; `GET`/`POST /{name}/install` |
| `backend/app.py` | construct installer onto `app.state` |
| `backend/tests/test_chatterbox_proxy.py` | `installed`-flag test (append) |
| `backend/tests/test_chatterbox_install.py` | installer + endpoint tests (new) |
| `backend/tests/test_setup_helpers.py` | `install-chatterbox` subcommand test (append) |
| `frontend/src/types/models.ts` | `EngineInfo.installed`; `InstallStatus` |
| `frontend/src/lib/api.ts` | install start/status calls |
| `frontend/src/components/EngineSelector.tsx` | Install action when not installed |
| `frontend/src/components/InstallChatterboxDialog.tsx` | full-log install modal |
| `frontend/src/App.tsx`, `frontend/src/components/ActionBar.tsx` | wire dialog + refresh |
| `README.md`, `CLAUDE.md` | note the in-UI install path |

---

## Task 1: `installed` flag on engines

**Files:**
- Modify: `backend/core/engines/__init__.py`
- Modify: `backend/core/engines/chatterbox_engine.py`
- Modify: `backend/api/engines.py`
- Test: `backend/tests/test_chatterbox_proxy.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_chatterbox_proxy.py`:

```python
def test_installed_flag_reflects_worker_python(tmp_path):
    present = tmp_path / "py.exe"
    present.write_text("", encoding="utf-8")
    eng_yes = ChatterboxEngine(worker_python=present, worker_script=tmp_path / "w.py")
    assert eng_yes.installed() is True
    assert eng_yes.info()["installed"] is True

    eng_no = ChatterboxEngine(worker_python=tmp_path / "nope.exe", worker_script=tmp_path / "w.py")
    assert eng_no.installed() is False
    assert eng_no.info()["installed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_chatterbox_proxy.py -k installed_flag -v`
Expected: FAIL — `AttributeError: 'ChatterboxEngine' object has no attribute 'installed'`.

- [ ] **Step 3: Add `installed()` to the base `Engine` and include it in `info()`**

In `backend/core/engines/__init__.py`, inside `class Engine`, add this method (place it just after the `supports_streaming` method, near the other capability methods):

```python
    def installed(self) -> bool:
        """True if the engine's runtime is present and usable. Engines that
        live in the main venv are always installed; engines that need a
        separate environment (Chatterbox) override this."""
        return True
```

Then, in the same class's `info(self)` method, add an `"installed"` entry to the returned dict (add this line alongside the existing keys like `"loaded"`):

```python
            "installed": self.installed(),
```

- [ ] **Step 4: Override `installed()` in `ChatterboxEngine`**

In `backend/core/engines/chatterbox_engine.py`, add this method to `class ChatterboxEngine` (place it right after the `is_loaded` method):

```python
    def installed(self) -> bool:
        return self._worker_python.is_file()
```

- [ ] **Step 5: Surface `installed` in the API model**

In `backend/api/engines.py`:

(a) Add `installed: bool` to `EngineInfoModel` (after the `loaded: bool` field):

```python
class EngineInfoModel(BaseModel):
    name: str
    display_name: str
    description: str
    loaded: bool
    installed: bool
    supports_voice_cloning: bool
    sample_rate: int | None
    max_speakers: int
    default_cfg_scale: float | None
    active: bool
```

(b) In `_to_model`, map it (add after the `loaded=info["loaded"],` line):

```python
        installed=info.get("installed", True),
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_chatterbox_proxy.py -k installed_flag -v`
Expected: PASS.

- [ ] **Step 7: Run the full suite (no regression)**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/core/engines/__init__.py backend/core/engines/chatterbox_engine.py backend/api/engines.py backend/tests/test_chatterbox_proxy.py
git commit -m "feat: expose an installed flag on engines"
```

---

## Task 2: `studio.py install-chatterbox` subcommand

**Files:**
- Modify: `studio.py`
- Test: `backend/tests/test_setup_helpers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_setup_helpers.py`:

```python
def test_install_chatterbox_subcommand_success(monkeypatch):
    calls = {"n": 0}
    def _fake():
        calls["n"] += 1
        return True
    monkeypatch.setattr(studio, "_ensure_chatterbox_env", _fake)
    assert studio.main(["install-chatterbox"]) == 0
    assert calls["n"] == 1


def test_install_chatterbox_subcommand_failure(monkeypatch):
    monkeypatch.setattr(studio, "_ensure_chatterbox_env", lambda: False)
    assert studio.main(["install-chatterbox"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k install_chatterbox -v`
Expected: FAIL — `install-chatterbox` is not a valid subcommand (argparse `SystemExit`), and/or `_ensure_chatterbox_env` returns None.

- [ ] **Step 3: Make `_ensure_chatterbox_env()` return a bool**

In `studio.py`, edit `_ensure_chatterbox_env` so EVERY early-return-on-error returns `False` and the success path returns `True`. The full function becomes:

```python
def _ensure_chatterbox_env() -> bool:
    """Create backend/venv-chatterbox and install chatterbox-tts into it.

    Chatterbox can't share the main venv (transformers pin conflict), so it
    gets its own environment with a CUDA-matched torch + chatterbox-tts.
    Returns True on success, False on any failure.
    """
    cpy = chatterbox_venv_python(REPO_ROOT)
    if not cpy.is_file():
        print("  Creating isolated Chatterbox environment (backend/venv-chatterbox) …")
        if _run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv-chatterbox")]) != 0:
            print("  ERROR: failed to create venv-chatterbox.")
            return False
    # CUDA-matched torch first (same detection as the main setup).
    tag = envdetect.detect_cuda_tag()
    index = envdetect.torch_index_url(tag)
    pip_torch = [str(cpy), "-m", "pip", "install", "torch", "torchaudio"]
    if index:
        pip_torch += ["--index-url", index]
    print("  Installing PyTorch into the Chatterbox env …")
    if _run(pip_torch) != 0:
        print("  ERROR: torch install into venv-chatterbox failed.")
        return False
    print("  Installing chatterbox-tts into the Chatterbox env …")
    if _run([str(cpy), "-m", "pip", "install", "-r",
             str(BACKEND_DIR / "requirements-chatterbox.txt")]) != 0:
        print("  ERROR: chatterbox-tts install failed.")
        return False
    print("  Chatterbox environment ready.")
    return True
```

(The existing caller in `_interactive_model_picker` ignores the return value, so it's unaffected.)

- [ ] **Step 4: Add the `install-chatterbox` subcommand**

In `studio.py`, add this command handler (place it right after the existing `cmd_models` function):

```python
def cmd_install_chatterbox(_args: argparse.Namespace) -> int:
    """Non-interactive: build/refresh the isolated Chatterbox env. Used by the
    backend's in-UI installer. Returns 0 on success, 1 on failure."""
    print(BANNER)
    ok = _ensure_chatterbox_env()
    return 0 if ok else 1
```

Then register it in `main()`. Find the subparser block (where `sub.add_parser("models", ...)` is) and add after it:

```python
    sub.add_parser("install-chatterbox", help="build the isolated Chatterbox env (non-interactive)")
```

And in `main()`'s dispatch (where it checks `if args.command == "models": return cmd_models(args)`), add:

```python
    if args.command == "install-chatterbox":
        return cmd_install_chatterbox(args)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_setup_helpers.py -k install_chatterbox -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Smoke-check the CLI**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe studio.py --help`
Expected: help lists `install-chatterbox` among the commands; exit 0.

- [ ] **Step 7: Commit**

```bash
git add studio.py backend/tests/test_setup_helpers.py
git commit -m "feat: add non-interactive studio.py install-chatterbox subcommand"
```

---

## Task 3: `ChatterboxInstaller` service

**Files:**
- Create: `backend/services/chatterbox_install.py`
- Test: `backend/tests/test_chatterbox_install.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_chatterbox_install.py`:

```python
"""Tests for the Chatterbox install manager using an injected fake runner."""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from backend.services.chatterbox_install import ChatterboxInstaller  # noqa: E402


def _fake_runner(lines, rc):
    def run():
        for ln in lines:
            yield ln, None
        yield None, rc
    return run


def _wait(inst, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and inst.status()["state"] == "installing":
        time.sleep(0.02)


def test_initial_state_not_installed():
    inst = ChatterboxInstaller(runner=_fake_runner([], 0))
    assert inst.status()["state"] == "not_installed"


def test_install_success_accumulates_log():
    inst = ChatterboxInstaller(runner=_fake_runner(["a", "b"], 0))
    inst.start()
    _wait(inst)
    s = inst.status()
    assert s["state"] == "installed"
    assert s["returncode"] == 0
    assert s["log"] == ["a", "b"]


def test_install_failure_sets_error():
    inst = ChatterboxInstaller(runner=_fake_runner(["boom"], 1))
    inst.start()
    _wait(inst)
    s = inst.status()
    assert s["state"] == "error"
    assert s["returncode"] == 1


def test_start_is_idempotent_while_running():
    started = {"n": 0}
    def run():
        started["n"] += 1
        time.sleep(0.2)
        yield "x", None
        yield None, 0
    inst = ChatterboxInstaller(runner=run)
    inst.start()
    inst.start()  # second call while installing must NOT launch a second run
    _wait(inst)
    assert started["n"] == 1
    assert inst.status()["state"] == "installed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_chatterbox_install.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.chatterbox_install'`.

- [ ] **Step 3: Implement `backend/services/chatterbox_install.py`**

```python
"""Background installer for the isolated Chatterbox environment.

Runs `python studio.py install-chatterbox` in a daemon thread, streaming its
merged stdout/stderr into a capped log buffer. State machine:
    not_installed -> installing -> installed | error

The subprocess runner is injectable (`runner`) so tests don't run real pip.
A runner is a zero-arg callable returning an iterator of (line, returncode):
each output line is yielded as (line, None); the final item is (None, rc).
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Iterator, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/services/.. -> repo root
_MAX_LOG_LINES = 2000

RunnerItem = Tuple[Optional[str], Optional[int]]
Runner = Callable[[], Iterator[RunnerItem]]


def _default_runner(repo_root: Path) -> Iterator[RunnerItem]:
    """Spawn `python studio.py install-chatterbox` and stream its output."""
    proc = subprocess.Popen(
        [sys.executable, "studio.py", "install-chatterbox"],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge so a single stream is drained to EOF
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n"), None
    proc.wait()
    yield None, proc.returncode


class ChatterboxInstaller:
    """Thread-safe install state machine for the isolated Chatterbox env."""

    def __init__(self, *, runner: Runner | None = None, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or _REPO_ROOT
        self._runner: Runner = runner or (lambda: _default_runner(self._repo_root))
        self._lock = threading.Lock()
        self._state = "not_installed"
        self._log: list[str] = []
        self._returncode: int | None = None
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "log": list(self._log),
                "returncode": self._returncode,
            }

    def start(self) -> dict:
        with self._lock:
            if self._state == "installing":
                # Already running — coalesce; don't launch a second process.
                return {
                    "state": self._state,
                    "log": list(self._log),
                    "returncode": self._returncode,
                }
            self._state = "installing"
            self._log = []
            self._returncode = None
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return {"state": self._state, "log": [], "returncode": None}

    def _run(self) -> None:
        rc: int | None = None
        try:
            for line, code in self._runner():
                if line is not None:
                    with self._lock:
                        self._log.append(line)
                        if len(self._log) > _MAX_LOG_LINES:
                            del self._log[: len(self._log) - _MAX_LOG_LINES]
                if code is not None:
                    rc = code
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._log.append(f"[installer error] {exc}")
                self._state = "error"
                self._returncode = -1
            return
        with self._lock:
            self._returncode = rc
            self._state = "installed" if rc == 0 else "error"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_chatterbox_install.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/services/chatterbox_install.py backend/tests/test_chatterbox_install.py
git commit -m "feat: add background Chatterbox install manager"
```

---

## Task 4: Install endpoints + wiring

**Files:**
- Modify: `backend/api/deps.py`
- Modify: `backend/api/engines.py`
- Modify: `backend/app.py`
- Test: `backend/tests/test_chatterbox_install.py` (append)

- [ ] **Step 1: Write the failing endpoint tests**

Append to `backend/tests/test_chatterbox_install.py`:

```python
def _make_client(installer):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.engines import router
    app = FastAPI()
    app.include_router(router)
    app.state.chatterbox_installer = installer
    return TestClient(app)


def test_install_endpoint_rejects_non_chatterbox():
    client = _make_client(ChatterboxInstaller(runner=_fake_runner([], 0)))
    assert client.get("/api/engines/kokoro/install").status_code == 400
    assert client.post("/api/engines/kokoro/install").status_code == 400


def test_install_endpoint_status_and_start():
    inst = ChatterboxInstaller(runner=_fake_runner(["hello"], 0))
    client = _make_client(inst)
    assert client.get("/api/engines/chatterbox/install").json()["state"] == "not_installed"
    r = client.post("/api/engines/chatterbox/install")
    assert r.status_code == 200
    _wait(inst)
    s = client.get("/api/engines/chatterbox/install").json()
    assert s["state"] == "installed"
    assert "hello" in s["log"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_chatterbox_install.py -k endpoint -v`
Expected: FAIL — the `/{name}/install` routes don't exist yet (404), and `get_chatterbox_installer` isn't defined.

- [ ] **Step 3: Add the dependency**

In `backend/api/deps.py`, add (after `get_engine_manager`):

```python
def get_chatterbox_installer(request: Request):
    return request.app.state.chatterbox_installer  # type: ignore[no-any-return]
```

- [ ] **Step 4: Add the endpoints**

In `backend/api/engines.py`:

(a) Add the import near the top (after the existing `from .deps import get_engine_manager`):

```python
from .deps import get_chatterbox_installer
```

(b) Add a response model (after `EnginesListResponse`):

```python
class InstallStatusModel(BaseModel):
    state: str
    log: list[str]
    returncode: int | None
```

(c) Add the two routes at the end of the file:

```python
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
```

NOTE: the existing `POST /{name}/load` route already uses the `/{name}/...` shape, so these coexist fine.

- [ ] **Step 5: Wire the singleton in `app.py`**

In `backend/app.py`, inside `create_app`, where the other `app.state.*` singletons are assigned, construct and attach the installer. Add the import near the other service imports at the top:

```python
from .services.chatterbox_install import ChatterboxInstaller
```

And in the body where `app.state.synth_service = synth_service` (and the other `app.state.*` lines) are set, add:

```python
    app.state.chatterbox_installer = ChatterboxInstaller()
```

- [ ] **Step 6: Run the endpoint tests + full suite**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/test_chatterbox_install.py -v`
Expected: PASS (6 tests).

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/api/deps.py backend/api/engines.py backend/app.py backend/tests/test_chatterbox_install.py
git commit -m "feat: add Chatterbox install endpoints and wire the installer"
```

---

## Task 5: Frontend types + API calls

**Files:**
- Modify: `frontend/src/types/models.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add `installed` to `EngineInfo` and an `InstallStatus` type**

In `frontend/src/types/models.ts`, add `installed: boolean;` to the `EngineInfo` interface (after `loaded: boolean;`):

```typescript
export interface EngineInfo {
  name: string;
  display_name: string;
  description: string;
  loaded: boolean;
  installed: boolean;
  supports_voice_cloning: boolean;
  sample_rate: number | null;
  max_speakers: number;
  default_cfg_scale: number | null;
  active: boolean;
}
```

Then add a new exported type (anywhere among the interfaces, e.g. right after `EngineInfo`):

```typescript
export interface InstallStatus {
  state: "not_installed" | "installing" | "installed" | "error";
  log: string[];
  returncode: number | null;
}
```

- [ ] **Step 2: Add the API wrappers**

In `frontend/src/lib/api.ts`, add `InstallStatus` to the type import block at the top:

```typescript
import type {
  ConfigResponse,
  EngineInfo,
  HealthResponse,
  InstallStatus,
  SynthBase64Response,
  SynthSpeaker,
  UploadVoiceResponse,
  Voice,
} from "@/types/models";
```

Then add two functions (after `loadEngine`):

```typescript
export async function startChatterboxInstall(): Promise<InstallStatus> {
  return jsonOrThrow<InstallStatus>(
    await fetch(`${API_BASE}/engines/chatterbox/install`, { method: "POST" }),
  );
}

export async function getChatterboxInstallStatus(): Promise<InstallStatus> {
  return jsonOrThrow<InstallStatus>(
    await fetch(`${API_BASE}/engines/chatterbox/install`),
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/models.ts frontend/src/lib/api.ts
git commit -m "feat: frontend types and api for chatterbox install"
```

---

## Task 6: Install modal + selector wiring

**Files:**
- Create: `frontend/src/components/InstallChatterboxDialog.tsx`
- Modify: `frontend/src/components/EngineSelector.tsx`
- Modify: `frontend/src/components/ActionBar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create the install modal**

Create `frontend/src/components/InstallChatterboxDialog.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { getChatterboxInstallStatus, startChatterboxInstall } from "@/lib/api";
import type { InstallStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  onClose: () => void;
  onInstalled: () => void;
}

export function InstallChatterboxDialog({ isDark, onClose, onInstalled }: Props) {
  const [status, setStatus] = useState<InstallStatus>({
    state: "installing",
    log: [],
    returncode: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);

  const poll = async () => {
    try {
      const s = await getChatterboxInstallStatus();
      setStatus(s);
      if (s.state === "installing") {
        timerRef.current = window.setTimeout(() => void poll(), 1000);
      } else if (s.state === "installed") {
        onInstalled();
      }
    } catch (err) {
      setStatus((prev) => ({
        ...prev,
        state: "error",
        log: [...prev.log, err instanceof Error ? err.message : String(err)],
      }));
    }
  };

  const begin = async () => {
    setStatus({ state: "installing", log: [], returncode: null });
    try {
      await startChatterboxInstall();
    } catch (err) {
      setStatus({
        state: "error",
        log: [err instanceof Error ? err.message : String(err)],
        returncode: -1,
      });
      return;
    }
    void poll();
  };

  useEffect(() => {
    void begin();
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [status.log]);

  const installing = status.state === "installing";
  const done = status.state === "installed";
  const failed = status.state === "error";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        className={`w-full max-w-2xl rounded-xl border shadow-xl ${
          isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
        }`}
      >
        <div
          className={`flex items-center justify-between px-5 py-3 border-b ${
            isDark ? "border-zinc-800" : "border-gray-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {installing && <Loader2 className="w-4 h-4 animate-spin text-teal-400" />}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {installing
                ? "Installing Chatterbox…"
                : done
                  ? "Chatterbox installed"
                  : "Chatterbox install failed"}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={installing}
            className={`p-1 rounded ${
              installing
                ? "opacity-40 cursor-not-allowed"
                : isDark
                  ? "hover:bg-zinc-800 text-zinc-400"
                  : "hover:bg-gray-100 text-gray-500"
            }`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-3">
          <p className={`text-sm ${isDark ? "text-zinc-400" : "text-gray-600"}`}>
            {installing
              ? "Building the isolated Chatterbox environment (venv + PyTorch + chatterbox-tts). This takes a few minutes."
              : done
                ? "Done. Close this dialog, then switch to Chatterbox in the engine menu."
                : "The install failed. Review the log below and retry."}
          </p>
          <pre
            ref={logRef}
            className={`h-72 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap ${
              isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
            }`}
          >
            {status.log.length ? status.log.join("\n") : "Starting…"}
          </pre>
          <div className="flex justify-end gap-2">
            {failed && (
              <button
                type="button"
                onClick={() => void begin()}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-teal-600 hover:bg-teal-500 text-white"
              >
                Retry
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              disabled={installing}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${
                installing
                  ? "opacity-40 cursor-not-allowed bg-zinc-700 text-zinc-300"
                  : isDark
                    ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700"
              }`}
            >
              {done ? "Done" : "Close"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add an `onInstall` path to `EngineSelector`**

In `frontend/src/components/EngineSelector.tsx`:

(a) Add `onInstall` to the `Props` interface:

```tsx
interface Props {
  isDark: boolean;
  engines: EngineInfo[];
  activeName: string | null;
  onSelect: (name: string) => Promise<void>;
  onLoad: (name: string) => Promise<void>;
  onInstall: (name: string) => void;
}
```

(b) Destructure it in the component signature: change `}: Props) {` so the params include `onInstall`:

```tsx
export function EngineSelector({
  isDark,
  engines,
  activeName,
  onSelect,
  onLoad,
  onInstall,
}: Props) {
```

(c) Replace the existing switch `<button ...>` block (the one rendering "Currently active"/"Loading…"/`Switch to …`) with this conditional that shows an Install button when the engine isn't installed:

```tsx
                      {e.installed === false ? (
                        <button
                          type="button"
                          onClick={() => {
                            onInstall(e.name);
                            setOpen(false);
                          }}
                          className={`mt-2 w-full text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                            isDark
                              ? "bg-teal-700/40 hover:bg-teal-700/60 text-teal-200"
                              : "bg-teal-50 hover:bg-teal-100 text-teal-700"
                          }`}
                        >
                          {`Install ${e.display_name}`}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void handleSelect(e.name)}
                          disabled={isActive}
                          className={`mt-2 w-full text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                            isActive
                              ? "bg-teal-600/20 text-teal-300 cursor-default"
                              : isDark
                                ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                                : "bg-gray-100 hover:bg-gray-200 text-gray-700"
                          }`}
                        >
                          {isActive
                            ? "Currently active"
                            : switching
                              ? "Loading…"
                              : `Switch to ${e.display_name}`}
                        </button>
                      )}
```

- [ ] **Step 3: Thread `onInstall` through `ActionBar`**

In `frontend/src/components/ActionBar.tsx`:

(a) Add to the props interface (after `onLoadEngine: ...`):

```tsx
  onInstallEngine: (name: string) => void;
```

(b) Add `onInstallEngine` to the destructured params (after `onLoadEngine,`).

(c) Pass it to `<EngineSelector ... />` (add the prop after `onLoad={onLoadEngine}`):

```tsx
          onInstall={onInstallEngine}
```

- [ ] **Step 4: Wire the dialog in `App.tsx`**

In `frontend/src/App.tsx`:

(a) Add the import (with the other component imports):

```tsx
import { InstallChatterboxDialog } from "@/components/InstallChatterboxDialog";
```

(b) In the `useEngine()` destructure, also pull `refresh`:

```tsx
  const {
    engines,
    activeName: activeEngine,
    setActive: setActiveEngine,
    ensureLoaded: ensureEngineLoaded,
    refresh: refreshEngines,
  } = useEngine();
```

(c) Add state near the other `useState` hooks:

```tsx
  const [installEngineOpen, setInstallEngineOpen] = useState(false);
```

(d) Pass `onInstallEngine` to `<ActionBar ... />` (next to `onLoadEngine={...}`):

```tsx
          onInstallEngine={() => setInstallEngineOpen(true)}
```

(e) Render the dialog. Just before the closing `</main>` tag (right after `<PlayerFooter ... />`), add:

```tsx
        {installEngineOpen && (
          <InstallChatterboxDialog
            isDark={isDark}
            onClose={() => setInstallEngineOpen(false)}
            onInstalled={() => {
              void refreshEngines();
            }}
          />
        )}
```

- [ ] **Step 5: Typecheck + build**

Run: `cd frontend && npm run typecheck`
Expected: no errors.

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/InstallChatterboxDialog.tsx frontend/src/components/EngineSelector.tsx frontend/src/components/ActionBar.tsx frontend/src/App.tsx
git commit -m "feat: in-UI Chatterbox install modal and selector action"
```

---

## Task 7: Docs

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the README Chatterbox note**

In `README.md`, find the blockquote that starts with `> **Chatterbox installs separately.**` and append this sentence to the END of that blockquote (inside it, as a new `>` line):

```markdown
> You can also install it later **from the app** — open the engine menu and click
> **Install Chatterbox**; a dialog streams the build log and, when it finishes, you can
> switch to Chatterbox right away.
```

- [ ] **Step 2: Update the CLAUDE.md architecture note**

In `CLAUDE.md`, find the bullet that starts with `- **Chatterbox runs out-of-process.**` and append this sentence to the end of that same bullet:

```markdown
 The UI can build that venv on demand: `POST /api/engines/chatterbox/install` runs `studio.py install-chatterbox` via the `ChatterboxInstaller` (`backend/services/chatterbox_install.py`) and the `InstallChatterboxDialog` polls `GET /api/engines/chatterbox/install` for the live log. Each engine's `info()` carries an `installed` flag (Chatterbox = its venv exists).
```

- [ ] **Step 3: Verify**

Run: `cd "f:/Vibe Projects/vibe-podcast" && grep -c "Install Chatterbox" README.md && grep -c "install" CLAUDE.md`
Expected: README ≥ 1; CLAUDE ≥ 1.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document in-UI Chatterbox install"
```

---

## Task 8: Final verification

**No code — verification run-through.**

- [ ] **Step 1: Full backend suite green**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -m pytest backend/tests/ -q`
Expected: all pass (previous 30 + installed-flag + 2 studio + 4 installer + 2 endpoint = ~39).

- [ ] **Step 2: Frontend typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: both succeed.

- [ ] **Step 3: Main venv still VibeVoice-clean (isolation preserved)**

Run: `cd "f:/Vibe Projects/vibe-podcast" && backend/venv/Scripts/python.exe -c "import transformers; print(transformers.__version__); from vibevoice.modular.modeling_vibevoice_inference import VibeVoiceForConditionalGenerationInference; print('vibevoice OK')"`
Expected: `4.51.3` and `vibevoice OK`.

- [ ] **Step 4 (optional, manual, heavy): real end-to-end**

Start the app (`python studio.py start --dev`), open the engine menu. If `venv-chatterbox` is absent, the Chatterbox row shows **Install Chatterbox** → click → modal streams the pip log → on success, Close, then **Switch to Chatterbox** and Generate (first run downloads the model). Switching back to VibeVoice still works.

- [ ] **Step 5: Finish**

Use the `superpowers:finishing-a-development-branch` skill to integrate the work.

---

## Self-Review Notes

- **Spec coverage:** `installed` flag (T1), `studio.py install-chatterbox` + bool return (T2), `ChatterboxInstaller` state machine w/ injectable runner (T3), endpoints + deps + app.state wiring (T4), FE types/api (T5), modal + selector + wiring (T6), docs (T7), verification incl. isolation re-check (T8). All spec sections map to a task.
- **Type/name consistency:** `Engine.installed()`, `info()["installed"]`, `EngineInfoModel.installed`, `ChatterboxInstaller(runner=, repo_root=)`, `.start()`/`.status()` returning `{state, log, returncode}`, states `not_installed|installing|installed|error`, endpoints `GET/POST /api/engines/{name}/install`, `get_chatterbox_installer`, FE `InstallStatus`, `startChatterboxInstall`/`getChatterboxInstallStatus`, `onInstall`/`onInstallEngine` — used identically across backend, API, and frontend tasks.
- **Isolation invariant:** all backend tests use fakes/monkeypatch; none run real pip or import `chatterbox-tts`. T8 step 3 re-verifies VibeVoice/transformers untouched.
- **No-regression:** the `installed` key is additive; `_to_model` uses `info.get("installed", True)` so any engine info dict lacking it defaults to installed.
