#!/usr/bin/env python3
"""Voice Studio by MSR — one-stop setup & launch dispatcher.

Stdlib only: this runs on a bare system Python before the venv exists.

    python studio.py setup            # one-time install + model picker
    python studio.py start            # run the app (mode auto-selected)
    python studio.py start --dev      # force dev (two processes, hot reload)
    python studio.py start --prod     # force prod (one server, one port)
    python studio.py models           # re-open the model picker
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
VENV_DIR = BACKEND_DIR / "venv"

sys.path.insert(0, str(REPO_ROOT))
from tools import envdetect  # noqa: E402

IS_WINDOWS = os.name == "nt"
BANNER = "=== Voice Studio by MSR ==="


# --------------------------------------------------------------- helpers --
def venv_python(repo_root: Path) -> Path:
    """Path to the venv's Python interpreter for the current OS."""
    venv = repo_root / "backend" / "venv"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def chatterbox_venv_python(repo_root: Path) -> Path:
    """Path to the ISOLATED Chatterbox venv's Python interpreter."""
    venv = repo_root / "backend" / "venv-chatterbox"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def chatterbox_ready_marker(repo_root: Path) -> Path:
    """Sentinel written only after a FULL successful Chatterbox install.

    The venv's Python exists after `python -m venv` (step 1), long before the
    packages are installed, so its mere presence can't mean "installed". This
    marker is created last, so an interrupted install never looks complete.
    """
    return repo_root / "backend" / "venv-chatterbox" / ".chatterbox-ready"


def omnivoice_venv_python(repo_root: Path) -> Path:
    """Path to the ISOLATED OmniVoice venv's Python interpreter."""
    venv = repo_root / "backend" / "venv-omnivoice"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def omnivoice_ready_marker(repo_root: Path) -> Path:
    """Sentinel written only after a FULL successful OmniVoice install.

    Mirrors chatterbox_ready_marker: the venv Python exists right after
    `python -m venv`, long before packages are installed, so only this
    marker (written last) means "fully installed".
    """
    return repo_root / "backend" / "venv-omnivoice" / ".omnivoice-ready"


def voxcpm_venv_python(repo_root: Path) -> Path:
    """Path to the ISOLATED VoxCPM venv's Python interpreter."""
    venv = repo_root / "backend" / "venv-voxcpm"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def voxcpm_ready_marker(repo_root: Path) -> Path:
    """Sentinel written only after a FULL successful VoxCPM install."""
    return repo_root / "backend" / "venv-voxcpm" / ".voxcpm-ready"


def qwen_venv_python(repo_root: Path) -> Path:
    """Path to the ISOLATED Qwen venv's Python interpreter."""
    venv = repo_root / "backend" / "venv-qwen"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def qwen_ready_marker(repo_root: Path) -> Path:
    """Sentinel written only after a FULL successful Qwen install."""
    return repo_root / "backend" / "venv-qwen" / ".qwen-ready"


def uv_executable_path(repo_root: Path) -> Path:
    """Path to the `uv` binary installed inside the base backend/venv."""
    venv = repo_root / "backend" / "venv"
    if os.name == "nt":
        return venv / "Scripts" / "uv.exe"
    return venv / "bin" / "uv"


def uv_cache_dir(repo_root: Path) -> Path:
    """Repo-local uv cache, on the SAME volume as the venvs so uv hardlinks
    (a cross-volume cache would silently fall back to copying — no dedup)."""
    return repo_root / "backend" / ".uv-cache"


# Memoized handle to the uv binary (None once we've decided uv is unavailable).
_UV_RESOLVED: dict[str, Path | None] = {}


def _ensure_uv() -> Path | None:
    """Return a usable `uv` executable, installing it into backend/venv via pip
    on first use. Sets UV_CACHE_DIR to the repo-local cache. Returns None if uv
    can't be obtained — callers then fall back to the pip+venv path.
    """
    if "uv" in _UV_RESOLVED:
        return _UV_RESOLVED["uv"]
    uv = uv_executable_path(REPO_ROOT)
    if not uv.is_file():
        py = venv_python(REPO_ROOT)
        if not py.is_file():
            _UV_RESOLVED["uv"] = None
            return None
        print("  Installing uv into backend/venv (fast, deduplicated installs) …")
        if _run([str(py), "-m", "pip", "install", "uv"]) != 0 or not uv.is_file():
            print("  WARNING: could not install uv — falling back to pip.")
            _UV_RESOLVED["uv"] = None
            return None
    cache = uv_cache_dir(REPO_ROOT)
    try:
        cache.mkdir(parents=True, exist_ok=True)
        os.environ["UV_CACHE_DIR"] = str(cache)
    except OSError as exc:
        print(f"  WARNING: could not create uv cache dir {cache}: {exc} "
              "(disk dedup may not apply).")
    _UV_RESOLVED["uv"] = uv
    return uv


def _engine_venv_python(venv_dir: Path) -> Path:
    """Interpreter path inside an isolated engine venv for the current OS."""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _uv_venv_cmd(uv: Path, venv_dir: Path, python: str) -> list[str]:
    """`uv venv` pinned to a specific interpreter via --python, so the engine
    venv uses the same Python `python -m venv` would have (this preserves
    VoxCPM's 3.10–3.12 requirement — uv otherwise picks its own default)."""
    return [str(uv), "venv", "--python", str(python), str(venv_dir)]


def _uv_pip_install_cmd(uv: Path, venv_dir: Path, extra: list[str]) -> list[str]:
    """`uv pip install` targeting a specific venv via --python."""
    py = _engine_venv_python(venv_dir)
    return [str(uv), "pip", "install", "--python", str(py), *extra]


def _python_supported_for_voxcpm(version_info) -> bool:
    """VoxCPM (torchcodec/funasr) supports Python 3.10–3.12 only."""
    major, minor = version_info[0], version_info[1]
    return major == 3 and 10 <= minor <= 12


# --------------------------------------------------------------- ACE-Step --
ACESTEP_REPO_URL = "https://github.com/ace-step/ACE-Step-1.5"
ACESTEP_PIN = "6d467e4b5081ccb0abf1ec1bf4fdf9051a2d34b0"  # spike-validated commit


def acestep_repo_dir(repo_root: Path) -> Path:
    return repo_root / "backend" / "vendor" / "ace-step"


def acestep_ready_marker(repo_root: Path) -> Path:
    return acestep_repo_dir(repo_root) / ".acestep-ready"


def acestep_venv_python(repo_root: Path) -> Path:
    venv = acestep_repo_dir(repo_root) / ".venv"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _acestep_clone_cmd(dest: Path) -> list[str]:
    return ["git", "clone", ACESTEP_REPO_URL, str(dest)]


def _ensure_acestep_env() -> bool:
    """Clone ACE-Step (pinned) into backend/vendor/ace-step and build its venv
    via `uv sync`. Returns True on full success."""
    if not _python_supported_for_voxcpm(sys.version_info):  # same 3.10–3.12 gate
        print("  ERROR: ACE-Step requires Python 3.11–3.12 (you have "
              f"{sys.version_info.major}.{sys.version_info.minor}).")
        return False
    marker = acestep_ready_marker(REPO_ROOT)
    try:
        marker.unlink()
    except OSError:
        pass
    repo = acestep_repo_dir(REPO_ROOT)
    if not (repo / "pyproject.toml").is_file():
        repo.parent.mkdir(parents=True, exist_ok=True)
        print("  Cloning ACE-Step 1.5 …")
        if _run(_acestep_clone_cmd(repo)) != 0:
            print("  ERROR: git clone failed.")
            return False
    if _run(["git", "-C", str(repo), "checkout", ACESTEP_PIN]) != 0:
        print("  ERROR: failed to check out the pinned ACE-Step commit.")
        return False
    uv = _ensure_uv()
    if uv is None:
        print("  ERROR: uv is required to build the ACE-Step env.")
        return False
    print("  Building ACE-Step env with uv sync (torch 2.7+cu128; several GB) …")
    if _run([str(uv), "sync", "--python", "3.11"], cwd=repo) != 0:
        print("  ERROR: uv sync failed.")
        return False
    try:
        marker.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(f"  ERROR: could not write ready marker: {exc}")
        return False
    print("  ACE-Step environment ready.")
    return True


def cmd_install_acestep(_args: argparse.Namespace) -> int:
    print(BANNER)
    return 0 if _ensure_acestep_env() else 1


def main_venv_torch_tag(repo_root: Path) -> str | None:
    """CUDA build tag (e.g. 'cu124') of the torch installed in the main venv,
    read from its dist-info directory name (no torch import). None if not found
    or it's a non-CUDA (+cpu) build."""
    venv = repo_root / "backend" / "venv"
    if os.name == "nt":
        sp = venv / "Lib" / "site-packages"
    else:
        cands = sorted(venv.glob("lib/python*/site-packages"))
        sp = cands[0] if cands else venv / "lib" / "site-packages"
    try:
        dist_infos = list(sp.glob("torch-*.dist-info"))
    except OSError:
        return None
    for d in dist_infos:
        name = d.name  # e.g. "torch-2.6.0+cu124.dist-info"
        if "+cu" in name:
            return "cu" + name.split("+cu", 1)[1].split(".dist-info", 1)[0]
    return None


def _chatterbox_torch_tag(detected_tag: str | None,
                          preferred_tag: str | None = None) -> str | None:
    """Pick a CUDA wheel build for Chatterbox's pinned torch (torch>=2.6.0,
    published for cu124/cu118).

    If the main venv already runs a CUDA torch build (`preferred_tag`, proof the
    driver supports it), reuse that exact tag so the identical torch VERSION
    deduplicates with the main venv under uv. Otherwise fall back to the
    conservative driver-derived mapping:
      - cu124 driver -> cu124
      - cu121 / cu118 driver -> cu118 (CUDA 11.8 runs on every 12.x driver)
      - cpu / mps / unknown -> None (leave the CPU wheel in place)
    """
    if preferred_tag in ("cu124", "cu118"):
        return preferred_tag
    if detected_tag == "cu124":
        return "cu124"
    if detected_tag in ("cu121", "cu118"):
        return "cu118"
    return None


def _pip_pkg_version(py: Path, pkg: str) -> str | None:
    """Public version of an installed package (local '+cuXXX/+cpu' stripped)."""
    try:
        out = subprocess.run(
            [str(py), "-m", "pip", "show", pkg],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.stdout.splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip().split("+", 1)[0]
    return None


def _install_main_deps_uv(uv: Path, index: str | None) -> bool:
    """Install torch(+torchaudio) and backend requirements into the main venv
    via uv (hardlinked from the shared cache). Returns True on success."""
    torch_extra = ["torch", "torchaudio"]
    if index:
        torch_extra += ["--index-url", index]
    print("  Installing torch into backend/venv with uv …")
    if _run(_uv_pip_install_cmd(uv, VENV_DIR, torch_extra)) != 0:
        return False
    print("  Installing backend requirements with uv …")
    return _run(_uv_pip_install_cmd(
        uv, VENV_DIR, ["-r", str(BACKEND_DIR / "requirements.txt")])) == 0


def _ensure_engine_env_uv(
    uv: Path,
    venv_dir: Path,
    requirements_file: Path,
    marker: Path,
    label: str,
    cuda_tag: str | None,
    torch_strategy: str,           # "newest" | "pinned"
) -> bool:
    """Build an isolated engine venv with uv (hardlinked from the shared cache).

    Steps: uv venv -> uv pip install -r <req> -> reinstall the CUDA torch build.
    Returns True on success. The caller handles pip fallback if uv is None.
    """
    try:
        marker.unlink()
    except OSError:
        pass
    epy = _engine_venv_python(venv_dir)
    if not epy.is_file():
        print(f"  Creating isolated {label} environment ({venv_dir.name}) with uv …")
        if _run(_uv_venv_cmd(uv, venv_dir, sys.executable)) != 0:
            print(f"  ERROR: failed to create {venv_dir.name}.")
            return False
    print(f"  Installing {label} deps with uv …")
    if _run(_uv_pip_install_cmd(uv, venv_dir, ["-r", str(requirements_file)])) != 0:
        print(f"  ERROR: {label} dependency install failed.")
        return False
    index = envdetect.torch_index_url(cuda_tag) if cuda_tag else None
    if index:
        if torch_strategy == "pinned":
            tv = _pip_pkg_version(epy, "torch")
            av = _pip_pkg_version(epy, "torchaudio")
            specs = []
            if tv:
                specs.append(f"torch=={tv}+{cuda_tag}")
            if av:
                specs.append(f"torchaudio=={av}+{cuda_tag}")
            if not specs:
                specs = ["torch", "torchaudio"]
        else:
            specs = ["torch", "torchaudio"]
        print(f"  Installing the CUDA build of torch ({cuda_tag}) for GPU …")
        if _run(_uv_pip_install_cmd(
                uv, venv_dir,
                ["--index-url", index, "--reinstall", *specs])) != 0:
            print("  ERROR: CUDA torch install failed.")
            return False
    else:
        print(f"  No matching torch CUDA build for this driver — {label} will "
              "run on CPU (slow).")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(f"  ERROR: could not write ready marker: {exc}")
        return False
    print(f"  {label} environment ready.")
    return True


def _ensure_chatterbox_env() -> bool:
    uv = _ensure_uv()
    if uv is None:
        return _ensure_chatterbox_env_pip()
    cb_tag = _chatterbox_torch_tag(
        envdetect.detect_cuda_tag(),
        preferred_tag=main_venv_torch_tag(REPO_ROOT),
    )
    return _ensure_engine_env_uv(
        uv,
        BACKEND_DIR / "venv-chatterbox",
        BACKEND_DIR / "requirements-chatterbox.txt",
        chatterbox_ready_marker(REPO_ROOT),
        "Chatterbox",
        cb_tag,
        torch_strategy="pinned",
    )


def _ensure_omnivoice_env() -> bool:
    uv = _ensure_uv()
    if uv is None:
        return _ensure_omnivoice_env_pip()
    return _ensure_engine_env_uv(
        uv,
        BACKEND_DIR / "venv-omnivoice",
        BACKEND_DIR / "requirements-omnivoice.txt",
        omnivoice_ready_marker(REPO_ROOT),
        "OmniVoice",
        envdetect.detect_omnivoice_cuda_tag(),
        torch_strategy="newest",
    )


def _ensure_voxcpm_env() -> bool:
    if not _python_supported_for_voxcpm(sys.version_info):
        print("  ERROR: VoxCPM requires Python 3.10–3.12 (you have "
              f"{sys.version_info.major}.{sys.version_info.minor}). "
              "Install a supported Python and re-run.")
        return False
    uv = _ensure_uv()
    if uv is None:
        return _ensure_voxcpm_env_pip()
    return _ensure_engine_env_uv(
        uv,
        BACKEND_DIR / "venv-voxcpm",
        BACKEND_DIR / "requirements-voxcpm.txt",
        voxcpm_ready_marker(REPO_ROOT),
        "VoxCPM",
        envdetect.detect_voxcpm_cuda_tag(),
        torch_strategy="newest",
    )


def _ensure_qwen_env() -> bool:
    uv = _ensure_uv()
    if uv is None:
        return _ensure_qwen_env_pip()
    return _ensure_engine_env_uv(
        uv,
        BACKEND_DIR / "venv-qwen",
        BACKEND_DIR / "requirements-qwen.txt",
        qwen_ready_marker(REPO_ROOT),
        "Qwen",
        envdetect.detect_qwen_cuda_tag(),
        torch_strategy="newest",
    )


def installed_engine_venvs(repo_root: Path):
    """List (name, venv_dir, marker, ensure_fn) for engine venvs whose ready
    marker exists — i.e. those safe to rebuild."""
    backend = repo_root / "backend"
    specs = [
        ("chatterbox", backend / "venv-chatterbox",
         chatterbox_ready_marker(repo_root), _ensure_chatterbox_env),
        ("omnivoice", backend / "venv-omnivoice",
         omnivoice_ready_marker(repo_root), _ensure_omnivoice_env),
        ("voxcpm", backend / "venv-voxcpm",
         voxcpm_ready_marker(repo_root), _ensure_voxcpm_env),
        ("qwen", backend / "venv-qwen",
         qwen_ready_marker(repo_root), _ensure_qwen_env),
    ]
    return [(n, vd, mk, fn) for (n, vd, mk, fn) in specs if mk.is_file()]


def _dir_size_bytes(path: Path) -> int:
    """Total size of files under `path` (0 if it doesn't exist)."""
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def _ensure_chatterbox_env_pip() -> bool:
    """Create backend/venv-chatterbox and install chatterbox-tts into it.

    Chatterbox can't share the main venv (transformers pin conflict), so it
    gets its own environment with a CUDA-matched torch + chatterbox-tts.
    Returns True on success, False on any failure.
    """
    # Clear any stale "ready" marker up front so a half-finished re-install
    # never reports as complete; it's re-created only on full success below.
    marker = chatterbox_ready_marker(REPO_ROOT)
    try:
        marker.unlink()
    except OSError:
        pass
    cpy = chatterbox_venv_python(REPO_ROOT)
    if not cpy.is_file():
        print("  Creating isolated Chatterbox environment (backend/venv-chatterbox) …")
        if _run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv-chatterbox")]) != 0:
            print("  ERROR: failed to create venv-chatterbox.")
            return False
    # Upgrade pip so we can stream download progress: pip's machine-readable
    # `--progress-bar raw` (which works when output is piped, unlike the
    # animated bar) needs pip >= 23.1, but a fresh venv ships an older one.
    # Best effort — if the upgrade fails (e.g. offline), fall back to no bar.
    print("  Upgrading pip in the Chatterbox env …")
    raw_ok = _run([str(cpy), "-m", "pip", "install", "--upgrade", "pip"]) == 0
    progress = ["--progress-bar", "raw"] if raw_ok else []
    # Multi-GB torch wheels download from a CDN that can stall; give pip a
    # longer per-read timeout and more retries so a slow link doesn't fail.
    net = ["--retries", "10", "--timeout", "120"]
    # 1. Install chatterbox-tts FIRST. It hard-pins an exact torch version and
    #    would otherwise overwrite a pre-installed CUDA torch with a CPU build
    #    from PyPI (the bug that left the engine running on CPU).
    print("  Installing chatterbox-tts into the Chatterbox env …")
    if _run([str(cpy), "-m", "pip", "install", *progress, *net, "-r",
             str(BACKEND_DIR / "requirements-chatterbox.txt")]) != 0:
        print("  ERROR: chatterbox-tts install failed.")
        return False
    # 2. Swap the CPU torch for the CUDA build of the SAME version so the model
    #    runs on GPU. The CPU wheel is already installed, so deps are satisfied;
    #    --no-deps avoids re-resolving them from the wheel-only CUDA index.
    cb_tag = _chatterbox_torch_tag(envdetect.detect_cuda_tag())
    index = envdetect.torch_index_url(cb_tag) if cb_tag else None
    if index:
        tv = _pip_pkg_version(cpy, "torch")
        av = _pip_pkg_version(cpy, "torchaudio")
        if tv:
            specs = [f"torch=={tv}+{cb_tag}"]
            if av:
                specs.append(f"torchaudio=={av}+{cb_tag}")
            print(f"  Installing the CUDA build of torch {tv} ({cb_tag}) for GPU …")
            if _run([str(cpy), "-m", "pip", "install", *progress, *net, "--force-reinstall",
                     "--no-deps", "--index-url", index, *specs]) != 0:
                print("  ERROR: CUDA torch install failed.")
                return False
    # Mark the install complete (written last, after both pip steps succeed).
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(f"  ERROR: could not write ready marker: {exc}")
        return False
    print("  Chatterbox environment ready.")
    return True


def _ensure_omnivoice_env_pip() -> bool:
    """Create backend/venv-omnivoice and install omnivoice into it.

    OmniVoice can't share any existing venv (transformers>=5.3.0 + torch 2.8),
    so it gets its own environment with a CUDA-matched torch + omnivoice.
    Returns True on success, False on any failure.
    """
    marker = omnivoice_ready_marker(REPO_ROOT)
    try:
        marker.unlink()
    except OSError:
        pass
    opy = omnivoice_venv_python(REPO_ROOT)
    if not opy.is_file():
        print("  Creating isolated OmniVoice environment (backend/venv-omnivoice) …")
        if _run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv-omnivoice")]) != 0:
            print("  ERROR: failed to create venv-omnivoice.")
            return False
    print("  Upgrading pip in the OmniVoice env …")
    raw_ok = _run([str(opy), "-m", "pip", "install", "--upgrade", "pip"]) == 0
    progress = ["--progress-bar", "raw"] if raw_ok else []
    net = ["--retries", "10", "--timeout", "120"]
    # 1. Install omnivoice FIRST (pulls a torch build to satisfy its pin).
    print("  Installing omnivoice into the OmniVoice env …")
    if _run([str(opy), "-m", "pip", "install", *progress, *net, "-r",
             str(BACKEND_DIR / "requirements-omnivoice.txt")]) != 0:
        print("  ERROR: omnivoice install failed.")
        return False
    # 2. Swap in the CUDA build of torch+torchaudio for GPU. Do NOT pin to the
    #    version pip just installed from PyPI: PyPI routinely ships a newer
    #    torch than the CUDA wheel index publishes (e.g. PyPI has torch 2.12.x
    #    while download.pytorch.org/whl/cu128 tops out at 2.11.x), so pinning
    #    the exact version 404s ("No matching distribution for torch==2.12.1+
    #    cu128"). Instead let pip pick the newest matching torch+torchaudio
    #    pair the CUDA index actually has (OmniVoice only needs torch>=2.4). On
    #    Windows the CUDA wheels are self-contained, so --no-deps is safe.
    ov_tag = envdetect.detect_omnivoice_cuda_tag()
    index = envdetect.torch_index_url(ov_tag) if ov_tag else None
    if index:
        print(f"  Installing the CUDA build of torch+torchaudio ({ov_tag}) for GPU …")
        if _run([str(opy), "-m", "pip", "install", *progress, *net, "--force-reinstall",
                 "--no-deps", "--index-url", index, "torch", "torchaudio"]) != 0:
            print("  ERROR: CUDA torch install failed.")
            return False
    else:
        print("  No matching torch CUDA build for this driver — leaving the "
              "default (CPU) torch in place. OmniVoice will run on CPU (slow).")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(f"  ERROR: could not write ready marker: {exc}")
        return False
    print("  OmniVoice environment ready.")
    return True


def _ensure_voxcpm_env_pip() -> bool:
    """Create backend/venv-voxcpm and install voxcpm into it.

    VoxCPM needs torch>=2.5 / CUDA>=12 plus a heavy dependency tail, so it gets
    its own environment with a CUDA-matched torch + voxcpm. Returns True on
    success, False on any failure.
    """
    if not _python_supported_for_voxcpm(sys.version_info):
        print(
            "  ERROR: VoxCPM requires Python 3.10–3.12 (you have "
            f"{sys.version_info.major}.{sys.version_info.minor}). "
            "Install a supported Python and re-run."
        )
        return False
    marker = voxcpm_ready_marker(REPO_ROOT)
    try:
        marker.unlink()
    except OSError:
        pass
    vpy = voxcpm_venv_python(REPO_ROOT)
    if not vpy.is_file():
        print("  Creating isolated VoxCPM environment (backend/venv-voxcpm) …")
        if _run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv-voxcpm")]) != 0:
            print("  ERROR: failed to create venv-voxcpm.")
            return False
    print("  Upgrading pip in the VoxCPM env …")
    raw_ok = _run([str(vpy), "-m", "pip", "install", "--upgrade", "pip"]) == 0
    progress = ["--progress-bar", "raw"] if raw_ok else []
    net = ["--retries", "10", "--timeout", "120"]
    # 1. Install voxcpm FIRST (pulls a torch build to satisfy its pin).
    print("  Installing voxcpm into the VoxCPM env …")
    if _run([str(vpy), "-m", "pip", "install", *progress, *net, "-r",
             str(BACKEND_DIR / "requirements-voxcpm.txt")]) != 0:
        print("  ERROR: voxcpm install failed.")
        return False
    # 2. Swap in the CUDA build of torch+torchaudio for GPU. Let pip pick the
    #    newest matching pair the CUDA index has (VoxCPM only needs torch>=2.5);
    #    pinning an exact PyPI version 404s on the wheel-only CUDA index.
    vx_tag = envdetect.detect_voxcpm_cuda_tag()
    index = envdetect.torch_index_url(vx_tag) if vx_tag else None
    if index:
        print(f"  Installing the CUDA build of torch+torchaudio ({vx_tag}) for GPU …")
        if _run([str(vpy), "-m", "pip", "install", *progress, *net, "--force-reinstall",
                 "--no-deps", "--index-url", index, "torch", "torchaudio"]) != 0:
            print("  ERROR: CUDA torch install failed.")
            return False
    else:
        print("  No matching torch CUDA build for this driver — leaving the "
              "default (CPU) torch in place. VoxCPM will run on CPU (slow).")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(f"  ERROR: could not write ready marker: {exc}")
        return False
    print("  VoxCPM environment ready.")
    return True


def _ensure_qwen_env_pip() -> bool:
    """Create backend/venv-qwen and install qwen-tts into it.

    qwen-tts pins transformers==4.57.3 (incompatible with every other engine),
    so it gets its own environment with a CUDA-matched torch + qwen-tts.
    Returns True on success, False on any failure.
    """
    marker = qwen_ready_marker(REPO_ROOT)
    try:
        marker.unlink()
    except OSError:
        pass
    qpy = qwen_venv_python(REPO_ROOT)
    if not qpy.is_file():
        print("  Creating isolated Qwen environment (backend/venv-qwen) …")
        if _run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv-qwen")]) != 0:
            print("  ERROR: failed to create venv-qwen.")
            return False
    print("  Upgrading pip in the Qwen env …")
    raw_ok = _run([str(qpy), "-m", "pip", "install", "--upgrade", "pip"]) == 0
    progress = ["--progress-bar", "raw"] if raw_ok else []
    net = ["--retries", "10", "--timeout", "120"]
    # 1. Install qwen-tts FIRST (pulls a torch build to satisfy its deps).
    print("  Installing qwen-tts into the Qwen env …")
    if _run([str(qpy), "-m", "pip", "install", *progress, *net, "-r",
             str(BACKEND_DIR / "requirements-qwen.txt")]) != 0:
        print("  ERROR: qwen-tts install failed.")
        return False
    # 2. Swap in the CUDA build of torch+torchaudio for GPU.
    qtag = envdetect.detect_qwen_cuda_tag()
    index = envdetect.torch_index_url(qtag) if qtag else None
    if index:
        print(f"  Installing the CUDA build of torch+torchaudio ({qtag}) for GPU …")
        if _run([str(qpy), "-m", "pip", "install", *progress, *net, "--force-reinstall",
                 "--no-deps", "--index-url", index, "torch", "torchaudio"]) != 0:
            print("  ERROR: CUDA torch install failed.")
            return False
    else:
        print("  No matching torch CUDA build for this driver — leaving the "
              "default (CPU) torch in place. Qwen will run on CPU (slow).")
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok\n", encoding="utf-8")
    except OSError as exc:
        print(f"  ERROR: could not write ready marker: {exc}")
        return False
    print("  Qwen environment ready.")
    return True


def build_backend_cmd(py: Path, passthrough: list[str]) -> list[str]:
    """Command to launch the backend server via the venv Python."""
    return [py.as_posix(), "-m", "backend.cli", *passthrough]


def _which(name: str) -> str | None:
    return shutil.which(name)


def _npm() -> str | None:
    # On Windows npm is npm.cmd; shutil.which resolves it.
    return shutil.which("npm")


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"  $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None).returncode


def remote_is_voice_studio(url: str) -> bool:
    """True if a git remote URL points at the Voice Studio repo (any form)."""
    return "msrbuilds/voice-studio" in (url or "").lower()


def worktree_is_clean(porcelain: str) -> bool:
    """True if `git status --porcelain` output indicates no local changes."""
    return not (porcelain or "").strip()


def _confirm(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    ans = input(prompt + suffix).strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes")


# ----------------------------------------------------------------- setup --
def cmd_setup(_args: argparse.Namespace) -> int:
    print(BANNER)
    print("Setup — installing the backend, frontend, and (optionally) models.\n")

    if sys.version_info < (3, 10):
        print("ERROR: Python 3.10+ is required. You have "
              f"{sys.version_info.major}.{sys.version_info.minor}.")
        return 1

    # 1. venv
    py = venv_python(REPO_ROOT)
    if not py.is_file():
        print("[1/5] Creating virtual environment at backend/venv …")
        if _run([sys.executable, "-m", "venv", str(VENV_DIR)]) != 0:
            print("ERROR: failed to create venv.")
            return 1
    else:
        print("[1/5] venv already exists — reusing it.")

    # 2. PyTorch (auto-detect + confirm)
    print("\n[2/5] Selecting a PyTorch build …")
    tag = envdetect.detect_cuda_tag()
    index = envdetect.torch_index_url(tag)
    if tag:
        print(f"  Detected NVIDIA GPU → CUDA wheel '{tag}'.")
    elif platform.system() == "Darwin" and platform.machine() == "arm64":
        print("  Apple Silicon detected → default (MPS-capable) wheel.")
    else:
        print("  No NVIDIA GPU detected → CPU-only wheel (slower).")
    if not _confirm("  Install this PyTorch build?"):
        print("  Choose a build:  1) CUDA 12.4  2) CUDA 12.1  3) CUDA 11.8  4) CPU/MPS")
        choice = input("  > ").strip()
        index = {
            "1": envdetect.torch_index_url("cu124"),
            "2": envdetect.torch_index_url("cu121"),
            "3": envdetect.torch_index_url("cu118"),
            "4": None,
        }.get(choice, index)
    # 3. torch + backend requirements — via uv when available (hardlinked from
    #    the shared cache so the main venv's torch dedupes with the engine
    #    venvs); pip is the fallback.
    print("\n[3/5] Installing torch + backend dependencies …")
    uv = _ensure_uv()
    if uv is not None:
        if not _install_main_deps_uv(uv, index):
            print("ERROR: dependency install failed. Re-run setup.")
            return 1
    else:
        pip_torch = [str(py), "-m", "pip", "install", "torch", "torchaudio"]
        if index:
            pip_torch += ["--index-url", index]
        if _run(pip_torch) != 0:
            print("ERROR: torch install failed. Re-run setup or install torch manually.")
            return 1
        if _run([str(py), "-m", "pip", "install", "-r",
                 str(BACKEND_DIR / "requirements.txt")]) != 0:
            print("ERROR: backend dependency install failed.")
            return 1

    # 4. system deps + frontend
    print("\n[4/5] Checking system dependencies …")
    _check_system_deps()
    if _npm():
        print("  Installing frontend dependencies (npm install) …")
        _run([_npm(), "install"], cwd=FRONTEND_DIR)
    else:
        print("  WARNING: npm not found. Install Node.js 18+ "
              "(https://nodejs.org) then run: cd frontend && npm install")

    # 5. model picker
    print("\n[5/5] Model download")
    _interactive_model_picker(py)

    print("\nSetup complete. Start the app with:  python studio.py start")
    return 0


def _check_system_deps() -> None:
    mgr = (
        "winget install eSpeak-NG.eSpeak-NG" if IS_WINDOWS
        else "brew install espeak-ng" if platform.system() == "Darwin"
        else "sudo apt-get install espeak-ng"
    )
    ff = (
        "winget install Gyan.FFmpeg" if IS_WINDOWS
        else "brew install ffmpeg" if platform.system() == "Darwin"
        else "sudo apt-get install ffmpeg"
    )
    if _which("espeak-ng") is None:
        print(f"  NOTE: espeak-ng not found (needed by Kokoro). Install: {mgr}")
    if _which("ffmpeg") is None:
        print(f"  NOTE: ffmpeg not found (some audio I/O). Install: {ff}")


def _interactive_model_picker(py: Path) -> None:
    # Import the catalog via the venv is overkill; mirror keys here for the
    # prompt, and let download_models validate.
    catalog = [
        ("vibevoice", "VibeVoice-1.5B", "~5.4 GB"),
        ("kokoro", "Kokoro-82M", "~350 MB"),
        ("chatterbox", "Chatterbox V3", "~500 MB"),
    ]
    print("  Select models to download now (others download lazily on first use):")
    for i, (_key, label, size) in enumerate(catalog, 1):
        print(f"    {i}) {label:<16} {size}")
    print("  Enter numbers separated by commas (e.g. 2,3), or blank to skip.")
    raw = input("  > ").strip()
    if not raw:
        print("  Skipping model download.")
        return
    picked: list[str] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if tok.isdigit() and 1 <= int(tok) <= len(catalog):
            picked.append(catalog[int(tok) - 1][0])
    if not picked:
        print("  Nothing valid selected — skipping.")
        return
    _run([str(py), "-m", "backend.scripts.download_models",
          "--models", ",".join(picked)], cwd=REPO_ROOT)
    if "chatterbox" in picked:
        print("  Chatterbox selected — setting up its isolated environment …")
        _ensure_chatterbox_env()


# --------------------------------------------------------------- models --
def cmd_models(_args: argparse.Namespace) -> int:
    py = venv_python(REPO_ROOT)
    if not py.is_file():
        print("No venv found. Run:  python studio.py setup")
        return 1
    _interactive_model_picker(py)
    return 0


# ------------------------------------------------ install-chatterbox --
def cmd_install_chatterbox(_args: argparse.Namespace) -> int:
    """Non-interactive: build/refresh the isolated Chatterbox env. Used by the
    backend's in-UI installer. Returns 0 on success, 1 on failure."""
    print(BANNER)
    ok = _ensure_chatterbox_env()
    return 0 if ok else 1


def cmd_install_omnivoice(_args: argparse.Namespace) -> int:
    """Non-interactive: build/refresh the isolated OmniVoice env. Used by the
    backend's in-UI installer. Returns 0 on success, 1 on failure."""
    print(BANNER)
    ok = _ensure_omnivoice_env()
    return 0 if ok else 1


def cmd_install_voxcpm(_args: argparse.Namespace) -> int:
    """Non-interactive: build/refresh the isolated VoxCPM env. Used by the
    backend's in-UI installer. Returns 0 on success, 1 on failure."""
    print(BANNER)
    ok = _ensure_voxcpm_env()
    return 0 if ok else 1


def cmd_install_qwen(_args: argparse.Namespace) -> int:
    """Non-interactive: build/refresh the isolated Qwen env. Used by the
    backend's in-UI installer. Returns 0 on success, 1 on failure."""
    print(BANNER)
    ok = _ensure_qwen_env()
    return 0 if ok else 1


# --------------------------------------------------------- optimize-venvs --
def _rebuild_main_venv_uv() -> int:
    """Recreate backend/venv and reinstall its deps via uv. studio.py runs on
    the system Python, so removing the venv is safe when no server is running."""
    shutil.rmtree(VENV_DIR, ignore_errors=True)
    if _run([sys.executable, "-m", "venv", str(VENV_DIR)]) != 0:
        print("  ERROR: failed to recreate backend/venv.")
        return 1
    _UV_RESOLVED.pop("uv", None)  # force re-install of uv into the fresh venv
    uv = _ensure_uv()
    if uv is None:
        print("  ERROR: could not install uv into the rebuilt main venv.")
        return 1
    tag = envdetect.detect_cuda_tag()
    index = envdetect.torch_index_url(tag)
    return 0 if _install_main_deps_uv(uv, index) else 1


def cmd_optimize_venvs(args: argparse.Namespace) -> int:
    """Rebuild existing engine venvs via uv to reclaim disk (dedup via the
    shared uv cache). Optionally rebuild the main venv with --include-main."""
    print(BANNER)
    if _ensure_uv() is None:
        print("uv is unavailable and could not be installed — nothing to "
              "optimize. (Engine venvs already use pip; no dedup possible.)")
        return 1
    present = installed_engine_venvs(REPO_ROOT)
    if not present and not args.include_main:
        print("No installed engine venvs found. Nothing to do.")
        return 0

    gb = 1024 * 1024 * 1024
    # Logical footprint (informational). Note: after uv hardlinks packages from
    # the shared cache, this sum barely changes — hardlinks report full size at
    # every link. Real reclaimed space is the volume's FREE-space delta below.
    logical = sum(_dir_size_bytes(p) for p in (REPO_ROOT / "backend").glob("venv*"))
    print(f"Current venv footprint (logical): {logical / gb:.1f} GB")
    free_before = shutil.disk_usage(str(BACKEND_DIR)).free

    failed: list[str] = []
    for name, venv_dir, _marker, ensure_fn in present:
        print(f"\nRebuilding {name} ({venv_dir.name}) via uv …")
        shutil.rmtree(venv_dir, ignore_errors=True)
        if not ensure_fn():
            print(f"  ERROR: {name} rebuild failed — reinstall it later "
                  f"(studio.py install-{name}).")
            failed.append(name)

    if args.include_main:
        print("\nRebuilding the main venv (backend/venv) via uv …")
        if _rebuild_main_venv_uv() != 0:
            failed.append("main")

    free_after = shutil.disk_usage(str(BACKEND_DIR)).free
    reclaimed = (free_after - free_before) / gb
    print(f"\nDisk reclaimed on {BACKEND_DIR.anchor or BACKEND_DIR}: "
          f"{reclaimed:.1f} GB free "
          f"({'freed' if reclaimed >= 0 else 'used'}).")
    if failed:
        print("Rebuild failed for: " + ", ".join(failed))
        return 1
    return 0


# --------------------------------------------------------------- update --
def _git_out(args: list[str]) -> tuple[int, str]:
    """Run a git command in REPO_ROOT, returning (returncode, stdout)."""
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return p.returncode, p.stdout
    except FileNotFoundError:
        return 127, "git not found on PATH"


def cmd_update(args: argparse.Namespace) -> int:
    """Apply an update by checking out a release tag, then re-syncing deps and
    rebuilding the frontend. Guards refuse to touch a non-git / dirty checkout.
    Used by the in-app updater; --tag is the release tag to check out.
    """
    print(BANNER)
    tag = args.tag

    # --- Guards (the notify-only fallback path lives here) ---
    if not (REPO_ROOT / ".git").exists():
        print("ERROR: not a git checkout — auto-update is unavailable. "
              "Download the latest release from GitHub instead.")
        return 1
    rc, _ = _git_out(["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        print("ERROR: git is unavailable or this is not a git repo. "
              "Install git or update manually.")
        return 1
    rc, remote = _git_out(["remote", "get-url", "origin"])
    if rc != 0 or not remote_is_voice_studio(remote):
        print("ERROR: the 'origin' remote is not the Voice Studio repo. "
              "Refusing to auto-update.")
        return 1
    rc, porcelain = _git_out(["status", "--porcelain"])
    if rc != 0 or not worktree_is_clean(porcelain):
        print("ERROR: you have uncommitted local changes. Commit or discard "
              "them before updating, or update manually.")
        return 1

    # --- Apply ---
    print("\n[1/4] Fetching tags …")
    if _run(["git", "fetch", "origin", "--tags"], cwd=REPO_ROOT) != 0:
        print("ERROR: git fetch failed.")
        return 1
    print(f"[2/4] Checking out {tag} …")
    # Intentional detached HEAD: the updater pins to a release tag, not a branch.
    # A detached HEAD is still "clean", so it doesn't trip the dirty-worktree guard
    # on the next update. Don't "fix" this into a branch checkout.
    if _run(["git", "checkout", tag], cwd=REPO_ROOT) != 0:
        print(f"ERROR: could not check out {tag}.")
        return 1

    py = venv_python(REPO_ROOT)
    if py.is_file():
        print("[3/4] Syncing backend dependencies …")
        if _run([str(py), "-m", "pip", "install", "-r",
                 str(BACKEND_DIR / "requirements.txt")]) != 0:
            print("ERROR: dependency sync failed.")
            return 1
    else:
        print("[3/4] No backend venv found — skipping dependency sync. "
              "Run `python studio.py setup`.")

    npm = _npm()
    if npm:
        print("[4/4] Rebuilding frontend …")
        if _run([npm, "install"], cwd=FRONTEND_DIR) != 0:
            print("ERROR: npm install failed.")
            return 1
        if _run([npm, "run", "build"], cwd=FRONTEND_DIR) != 0:
            print("ERROR: frontend build failed.")
            return 1
    else:
        print("[4/4] npm not found — skipping frontend rebuild. "
              "Install Node.js 18+ and run `cd frontend && npm run build`.")

    print(f"\nUPDATE OK — now on {tag}. Restart Voice Studio to apply.")
    return 0


# ---------------------------------------------------------------- start --
def _backend_port(passthrough: list[str]) -> int:
    """The port the backend will bind: --port from passthrough, else 8880."""
    for i, a in enumerate(passthrough):
        if a == "--port" and i + 1 < len(passthrough):
            try:
                return int(passthrough[i + 1])
            except ValueError:
                return 8880
        if a.startswith("--port="):
            try:
                return int(a.split("=", 1)[1])
            except ValueError:
                return 8880
    return 8880


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """True if something is already accepting connections on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def cmd_start(args: argparse.Namespace) -> int:
    print(BANNER)
    # Refuse to start a second backend on a port that's already serving — a
    # stray old instance would silently load the model again and thrash VRAM.
    port = _backend_port(args.passthrough)
    if _port_in_use(port):
        print(
            f"ERROR: port {port} is already in use - a Voice Studio backend looks\n"
            f"like it's already running. Stop it first (Ctrl+C in its terminal, or\n"
            f"close the other window) so a second one doesn't load the model again."
        )
        return 1
    py = venv_python(REPO_ROOT)
    if not py.is_file():
        if _confirm("No venv found. Run setup now?"):
            rc = cmd_setup(args)
            if rc != 0:
                return rc
        else:
            return 1

    mode = _resolve_mode(args)
    if mode == "prod":
        return _start_prod(py, args.passthrough)
    return _start_dev(py, args.passthrough)


def _resolve_mode(args: argparse.Namespace) -> str:
    if args.prod:
        return "prod"
    if args.dev:
        return "dev"
    if _npm():
        return "dev"
    if (FRONTEND_DIR / "dist" / "index.html").is_file():
        return "prod"
    print("ERROR: npm not found and no frontend/dist build present.\n"
          "Install Node.js 18+ (then re-run), or build once with --prod.")
    sys.exit(1)


def _start_dev(py: Path, passthrough: list[str]) -> int:
    print("Mode: DEV (backend :8880 + Vite :5173, hot reload). Ctrl+C to stop.\n")
    procs: list[subprocess.Popen] = []
    popen_kwargs: dict = {}
    if IS_WINDOWS:
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    backend = subprocess.Popen(
        build_backend_cmd(py, passthrough), cwd=str(REPO_ROOT), **popen_kwargs
    )
    procs.append(backend)
    if _npm():
        frontend = subprocess.Popen(
            [_npm(), "run", "dev"], cwd=str(FRONTEND_DIR), **popen_kwargs
        )
        procs.append(frontend)

    try:
        while True:
            for p in procs:
                rc = p.poll()
                if rc is not None:
                    print(f"\nA process exited (code {rc}); shutting the rest down.")
                    _terminate_all(procs)
                    return rc
            try:
                procs[0].wait(timeout=1)
            except subprocess.TimeoutExpired:
                continue
    except KeyboardInterrupt:
        print("\nStopping …")
        _terminate_all(procs)
        return 0


def _start_prod(py: Path, passthrough: list[str]) -> int:
    dist = FRONTEND_DIR / "dist" / "index.html"
    if not dist.is_file():
        if _npm() is None:
            print("ERROR: need to build the frontend but npm is not installed.")
            return 1
        print("Building frontend (npm run build) …")
        if _run([_npm(), "run", "build"], cwd=FRONTEND_DIR) != 0:
            print("ERROR: frontend build failed.")
            return 1
    print("Mode: PROD (single server on :8880). Ctrl+C to stop.\n")
    return subprocess.run(
        build_backend_cmd(py, passthrough), cwd=str(REPO_ROOT)
    ).returncode


def _terminate_all(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is not None:
            continue
        try:
            if IS_WINDOWS:
                p.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
    for p in procs:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()


# ------------------------------------------------------------------ main --
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="studio.py", description="Voice Studio by MSR — setup & launch"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="one-time install + model picker")

    p_start = sub.add_parser("start", help="run the app")
    p_start.add_argument("--dev", action="store_true", help="force dev mode")
    p_start.add_argument("--prod", action="store_true", help="force prod mode")
    p_start.add_argument(
        "passthrough", nargs=argparse.REMAINDER,
        help="flags forwarded to backend.cli (e.g. --device cuda --port 9000)",
    )

    sub.add_parser("models", help="re-open the model picker")
    sub.add_parser("install-chatterbox", help="build the isolated Chatterbox env (non-interactive)")
    sub.add_parser("install-omnivoice", help="build the isolated OmniVoice env (non-interactive)")
    sub.add_parser("install-voxcpm", help="build the isolated VoxCPM env (non-interactive)")
    sub.add_parser("install-qwen", help="build the isolated Qwen env (non-interactive)")
    sub.add_parser("install-acestep", help="clone + build the ACE-Step music env (non-interactive)")

    p_opt = sub.add_parser("optimize-venvs",
                           help="rebuild engine venvs via uv to reclaim disk")
    p_opt.add_argument("--include-main", action="store_true",
                       help="also rebuild the main backend/venv")

    p_update = sub.add_parser("update", help="check out a release tag, sync deps, rebuild frontend")
    p_update.add_argument("--tag", required=True, help="release tag to check out (e.g. v0.3.0)")

    args = parser.parse_args(argv)
    if args.command == "setup":
        return cmd_setup(args)
    if args.command == "models":
        return cmd_models(args)
    if args.command == "install-chatterbox":
        return cmd_install_chatterbox(args)
    if args.command == "install-omnivoice":
        return cmd_install_omnivoice(args)
    if args.command == "install-voxcpm":
        return cmd_install_voxcpm(args)
    if args.command == "install-qwen":
        return cmd_install_qwen(args)
    if args.command == "install-acestep":
        return cmd_install_acestep(args)
    if args.command == "optimize-venvs":
        return cmd_optimize_venvs(args)
    if args.command == "update":
        return cmd_update(args)
    if args.command == "start":
        return cmd_start(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
