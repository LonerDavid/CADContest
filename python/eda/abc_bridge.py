"""
ABC (Berkeley Logic Synthesis) subprocess bridge.

Wraps the `abc` CLI for heavy logic optimizations:
  - remap_to_and_not (abc -c 'strash; dc2; write_verilog')
  - remap_to_nand_not
  - combinational equivalence check (cec)

Falls back gracefully to the Python implementation when abc is not found.
Auto-installs ABC on first use by building from source.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Sentinel so we only attempt installation once per process
_install_attempted = False

# Install target: alongside the project's venv or a local cache dir
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_VENV_BIN = _PROJECT_ROOT / ".venv" / "bin"
_LOCAL_BIN = _PROJECT_ROOT / ".abc_bin"
ABC_REPO = "https://github.com/berkeley-abc/abc.git"


def _find_abc() -> Optional[str]:
    # Check standard PATH first
    found = shutil.which("abc") or shutil.which("berkeley-abc")
    if found:
        return found
    # Check our local install dirs
    for candidate in [_VENV_BIN / "abc", _LOCAL_BIN / "abc"]:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _run_silent(cmd: list, cwd=None, timeout: int = 300) -> bool:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        return r.returncode == 0
    except Exception:
        return False


def _install_via_apt() -> Optional[str]:
    print("[abc_bridge] Trying apt-get install abc...", flush=True)
    for prefix in ([], ["sudo"]):
        if _run_silent([*prefix, "apt-get", "install", "-y", "abc"]):
            return _find_abc()
    return None


def _install_via_dnf() -> Optional[str]:
    print("[abc_bridge] Trying dnf install abc...", flush=True)
    for prefix in ([], ["sudo"]):
        if _run_silent([*prefix, "dnf", "install", "-y", "abc"]):
            return _find_abc()
    return None


def _build_from_source() -> Optional[str]:
    """Clone berkeley-abc and build it; install binary into .venv/bin or .abc_bin."""
    if not shutil.which("git"):
        print("[abc_bridge] git not found — cannot build ABC from source.", flush=True)
        return None

    # Choose install location
    install_dir = _VENV_BIN if _VENV_BIN.exists() else _LOCAL_BIN
    install_dir.mkdir(parents=True, exist_ok=True)
    dest = install_dir / "abc"

    print("[abc_bridge] Building ABC from source (this takes ~1 min)...", flush=True)
    with tempfile.TemporaryDirectory() as td:
        # Clone (shallow to save time)
        if not _run_silent(
            ["git", "clone", "--depth=1", ABC_REPO, "abc"], cwd=td, timeout=120
        ):
            print("[abc_bridge] git clone failed.", flush=True)
            return None

        src = Path(td) / "abc"
        # Determine parallelism
        try:
            import multiprocessing
            jobs = str(max(1, multiprocessing.cpu_count()))
        except Exception:
            jobs = "4"

        if not _run_silent(["make", f"-j{jobs}"], cwd=src, timeout=300):
            print("[abc_bridge] make failed.", flush=True)
            return None

        built = src / "abc"
        if not built.exists():
            print("[abc_bridge] Build succeeded but binary not found.", flush=True)
            return None

        shutil.copy2(built, dest)
        dest.chmod(0o755)

    print(f"[abc_bridge] ABC installed at {dest}", flush=True)
    return str(dest)


def _try_install_abc() -> Optional[str]:
    global _install_attempted
    if _install_attempted:
        return None
    _install_attempted = True

    system = platform.system()

    if system == "Linux":
        if shutil.which("apt-get"):
            result = _install_via_apt()
            if result:
                return result
        elif shutil.which("dnf"):
            result = _install_via_dnf()
            if result:
                return result

    # Universal fallback: build from source
    return _build_from_source()


def _ensure_abc() -> Optional[str]:
    """Return the ABC binary path, installing it if necessary."""
    found = _find_abc()
    if found:
        return found
    return _try_install_abc()


# Resolve at import time (installs if needed)
ABC_BINARY: Optional[str] = _ensure_abc()


def abc_available() -> bool:
    return ABC_BINARY is not None


def _run_abc(script: str, timeout: int = 120) -> Optional[str]:
    """Run an ABC script string; return stdout or None on failure."""
    if not ABC_BINARY:
        return None
    try:
        result = subprocess.run(
            [ABC_BINARY, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def optimize_with_abc(verilog_src: str, commands: str = "strash; dc2; rewrite -z") -> Optional[str]:
    """
    Pass a Verilog netlist through ABC for optimization.
    Returns the optimized Verilog string, or None if ABC is unavailable/fails.
    """
    if not ABC_BINARY:
        return None
    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "in.v"
        out = Path(td) / "out.v"
        inp.write_text(verilog_src)
        script = f"read_verilog {inp}; {commands}; write_verilog {out}"
        if _run_abc(script) is None:
            return None
        if not out.exists():
            return None
        return out.read_text()


def check_equivalence_abc(verilog_a: str, verilog_b: str, timeout: int = 60) -> Optional[bool]:
    """
    Use ABC's `cec` command to verify functional equivalence.
    Returns True/False, or None if ABC is unavailable/fails.
    """
    if not ABC_BINARY:
        return None
    with tempfile.TemporaryDirectory() as td:
        a_path = Path(td) / "a.v"
        b_path = Path(td) / "b.v"
        a_path.write_text(verilog_a)
        b_path.write_text(verilog_b)
        script = f"read_verilog {a_path}; cec {b_path}"
        out = _run_abc(script, timeout=timeout)
        if out is None:
            return None
        lower = out.lower()
        if "equivalent" in lower and "not" not in lower:
            return True
        if "not equivalent" in lower or "mismatch" in lower:
            return False
        return None
