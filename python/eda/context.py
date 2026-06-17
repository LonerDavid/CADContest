"""Session context: bridges agent front-end to EDAEngine (Steps 1–2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..output_paths import log_path, resolve_netlist_output
from .api import EDAEngine
from .extras import dispatch_extra


class EDASession:
    """Multi-turn design state for one contest testcase."""

    def __init__(self) -> None:
        self.engine = EDAEngine()
        self.case_name: Optional[str] = None

    @property
    def design_loaded(self) -> bool:
        return self.engine.loaded

    def init_testcase(self, case_name: str) -> str:
        self.case_name = case_name
        self.engine = EDAEngine()
        log = log_path(case_name)
        return (
            f'Acknowledged. Initialized testcase "{case_name}". '
            f"All subsequent responses will be recorded to {log}. "
            f"Design state is empty and ready for commands."
        )

    def load_design(self, path: str) -> str:
        p = Path(path)
        if not p.exists() and self.case_name:
            alt = Path("testcase") / self.case_name / p.name
            if alt.exists():
                p = alt
        if not p.exists():
            raise FileNotFoundError(f"Design file not found: {path}")
        resolved = self.engine.load(p)
        return (
            f'Loaded gate-level Verilog from "{resolved}" successfully.\n'
            f"- Detected a single top module (flat netlist).\n"
            f"- Built internal DAG ({self.engine.design.gate_count()} gates).\n"
            f"Design state has been updated."
        )

    def write_design(self, path: str) -> str:
        out = resolve_netlist_output(self.case_name, path)
        self.engine.write(out)
        return f'Wrote the modified netlist to "{out}" successfully.'

    # Common LLM aliases -> canonical tool names.
    _TOOL_ALIASES = {
        "remap_xor_nand": "replace_xor_nand",
        "remap_xnor_nor": "replace_xnor_nor",
        "replace_xor_with_nand": "replace_xor_nand",
        "replace_xnor_with_nor": "replace_xnor_nor",
        "count_gates_by_type": "count_gate_type",
        "gate_count": "count_gates",
    }

    def execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        name = self._TOOL_ALIASES.get(name, name)
        if name == "init_testcase":
            return self.init_testcase(args["case_name"])
        if name == "load_design":
            return self.load_design(args["path"])
        if name == "write_design":
            return self.write_design(args["path"])
        if not self.engine.loaded:
            return "Error: No design loaded. Please load a design first."
        result = self.engine.dispatch(name, args)
        if result.startswith("Unknown tool:"):
            extra = dispatch_extra(self.engine, name, args)
            if extra is not None:
                return extra
        return result
