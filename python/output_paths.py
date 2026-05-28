"""Central paths for testcase outputs (logs and generated netlists)."""

from __future__ import annotations

import os
from pathlib import Path

# Repo root (parent of python/)
REPO_ROOT = Path(__file__).resolve().parent.parent

# Default: <repo>/output/testNN/
OUTPUT_ROOT = Path(os.environ.get("CADCONTEST_OUTPUT_DIR", REPO_ROOT / "output"))


def case_dir(case_name: str) -> Path:
    d = OUTPUT_ROOT / case_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path(case_name: str) -> Path:
    return case_dir(case_name) / f"{case_name}.log"


def resolve_netlist_output(case_name: str | None, path: str | Path) -> Path:
    """
    Map write requests like 'test01_out.v' to output/test01/test01_out.v.
    Absolute paths and explicit 'output/...' paths are preserved.
    """
    p = Path(path)
    if p.is_absolute():
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    if str(p).startswith("output/") or str(p).startswith("output\\"):
        out = REPO_ROOT / p
        out.parent.mkdir(parents=True, exist_ok=True)
        return out
    if case_name:
        return case_dir(case_name) / p.name
    dest = OUTPUT_ROOT / p.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest
