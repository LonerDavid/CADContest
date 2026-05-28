"""
ABC (Berkeley Logic Synthesis) subprocess bridge.

Wraps the `abc` CLI for heavy logic optimizations:
  - remap_to_and_not (abc -c 'strash; dc2; write_verilog')
  - remap_to_nand_not
  - combinational equivalence check (cec)

Falls back gracefully to the Python implementation when abc is not found.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

ABC_BINARY: Optional[str] = shutil.which("abc") or shutil.which("berkeley-abc")


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
