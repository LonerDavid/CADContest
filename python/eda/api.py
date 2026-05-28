"""
Step 2: EDA engine API — analysis and validated transformation operations.

All mutating operations run verification (functional equivalence + optional constraints)
and roll back on failure to avoid unintended netlist changes.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .dag import DesignDAG
from .graph import CircuitGraph
from .netlist import Gate, GateKind, Netlist, Signal
from .transform import TransformEngine
from .verify import ConstraintSpec, DesignVerifier, VerificationResult


class TransformError(Exception):
    """Raised when a transform fails verification and is rolled back."""

    def __init__(self, message: str, result: Optional[VerificationResult] = None):
        super().__init__(message)
        self.result = result


@dataclass
class TransformReport:
    success: bool
    message: str
    metric: int = 0
    verification: Optional[str] = None


class EDAEngine:
    """
    High-level EDA API over DesignDAG.

    Analysis methods are read-only. Transform methods mutate with verification.
    """

    def __init__(self) -> None:
        self.design: Optional[DesignDAG] = None
        self.baseline: Optional[DesignDAG] = None  # netlist at last load
        self._transform: Optional[TransformEngine] = None
        self._last_elim: Dict[str, int] = {}

    @property
    def loaded(self) -> bool:
        return self.design is not None

    def _require_design(self) -> DesignDAG:
        if not self.design:
            raise RuntimeError("No design loaded")
        return self.design

    def _sync_transform(self) -> TransformEngine:
        d = self._require_design()
        self._transform = TransformEngine(d.netlist)
        return self._transform

    # --- Step 1: load / write ---

    def load(self, path: str | Path) -> str:
        p = Path(path)
        self.design = DesignDAG.from_verilog(p)
        self.baseline = DesignDAG.from_netlist(self.design.clone_netlist())
        return str(p.resolve())

    def write(self, path: str | Path) -> None:
        self._require_design().write_verilog(path)

    # --- Analysis API ---

    def count_gates(self) -> Dict[str, int]:
        return self._require_design().count_by_type()

    def max_logic_depth(self, src: str, dst: str) -> int:
        g = self._require_design().graph
        d = g.max_combinational_depth(src, dst)
        return d if d >= 0 else g.max_depth_in_cone(dst)

    def max_depth_in_cone(self, signal: str) -> int:
        return self._require_design().graph.max_depth_in_cone(signal)

    def max_design_depth(self) -> int:
        return self._require_design().graph.max_design_depth()

    def fanout(self, signal: str) -> int:
        return self._require_design().graph.fanout_count(signal)

    def fanout_gates(self, signal: str) -> List[str]:
        return self._require_design().graph.gates_driven_by(signal)

    def fanin_cone_gates(self, signal: str) -> List[str]:
        return sorted(self._require_design().graph.fanin_cone_gates(signal))

    def fanout_cone_gates(self, signal: str) -> List[str]:
        return sorted(self._require_design().graph.fanout_cone_gates(signal))

    def path_exists(self, src: str, dst: str, avoid: Optional[Set[str]] = None) -> bool:
        g = self._require_design().graph
        if avoid:
            return g.path_exists_avoiding(src, dst, avoid)
        return g.has_combinational_path(src, dst)

    def list_paths(
        self, src: str, dst: str, max_paths: int = 100
    ) -> tuple[List[List[str]], bool]:
        return self._require_design().graph.all_combinational_paths(
            src, dst, max_paths=max_paths
        )

    def signals_equivalent(self, a: str, b: str) -> bool:
        return self._require_design().graph.functionally_equivalent(a, b)

    def verify_equivalent_to_baseline(self) -> VerificationResult:
        if not self.baseline or not self.design:
            return VerificationResult.fail("No baseline design.")
        return DesignVerifier(self.baseline).functionally_equivalent(self.design)

    def gate_info(self, gate_name: str) -> Gate:
        return self._require_design().netlist.gates[gate_name]

    # --- Validated transform wrapper ---

    def _apply_validated(
        self,
        mutate: Callable[[], Any],
        constraints: Optional[ConstraintSpec] = None,
        metric_fn: Optional[Callable[[], int]] = None,
    ) -> TransformReport:
        before_nl = self._require_design().clone_netlist()
        before_dag = DesignDAG.from_netlist(before_nl)

        try:
            result = mutate()
        except Exception as e:
            self.design = before_dag
            raise TransformError(f"Transform aborted: {e}") from e

        self.design.refresh()
        spec = constraints or ConstraintSpec(require_equivalence=True)
        vr = DesignVerifier(before_dag).verify_transform(before_dag, self.design, spec)

        if not vr.ok:
            self.design = before_dag
            self._sync_transform()
            raise TransformError(vr.message, vr)

        metric = metric_fn() if metric_fn else (result if isinstance(result, int) else 0)
        return TransformReport(
            success=True,
            message="Transform applied and verified.",
            metric=metric,
            verification=vr.message,
        )

    def insert_fanout_buffers(self, max_fanout: int = 4) -> TransformReport:
        def run():
            t = self._sync_transform()
            return t.insert_fanout_buffers(max_fanout)

        return self._apply_validated(
            run,
            ConstraintSpec(max_fanout=max_fanout, require_equivalence=True),
            metric_fn=lambda: self._sync_transform().nl.count_by_type().get("BUF", 0),
        )

    def remove_dangling(self) -> TransformReport:
        def run():
            return self._sync_transform().remove_dangling()

        return self._apply_validated(run)

    def rename_gate(self, old: str, new: str) -> TransformReport:
        def run():
            self._sync_transform().rename_gate(old, new)

        return self._apply_validated(
            run, ConstraintSpec(require_equivalence=True)
        )

    def rename_wire(self, old: str, new: str) -> TransformReport:
        def run():
            self._sync_transform().rename_wire(old, new)

        return self._apply_validated(
            run, ConstraintSpec(require_equivalence=True)
        )

    def collapse_back_to_back_inverters(self) -> TransformReport:
        def run():
            return self._sync_transform().collapse_back_to_back_inverters()

        return self._apply_validated(run)

    def remap_to_and_not(self) -> TransformReport:
        def run():
            self._sync_transform().remap_to_and_not()

        return self._apply_validated(run)

    def remap_to_nand_not(self) -> TransformReport:
        def run():
            self._sync_transform().remap_to_nand_not()

        return self._apply_validated(run)

    def replace_xnor_with_nor(self) -> TransformReport:
        def run():
            return self._sync_transform().replace_xnor_with_nor()

        return self._apply_validated(run)

    def replace_xor_with_nand(self) -> TransformReport:
        def run():
            return self._sync_transform().replace_xor_with_nand()

        return self._apply_validated(run)

    def optimize_cone_depth(self, signal: str, max_depth: int = 4) -> TransformReport:
        def run():
            return self._sync_transform().optimize_cone_depth(signal, max_depth)

        return self._apply_validated(
            run,
            ConstraintSpec(
                max_depth=max_depth,
                max_depth_signals=[signal],
                require_equivalence=True,
            ),
        )

    def reduce_critical_path_depth(self) -> TransformReport:
        def run():
            return self._sync_transform().reduce_critical_path_depth()

        return self._apply_validated(run)

    def merge_equivalent_gates(self) -> TransformReport:
        def run():
            return self._sync_transform().merge_functionally_equivalent_gates()

        return self._apply_validated(run)

    def merge_structural_duplicates(self) -> TransformReport:
        def run():
            return self._sync_transform().merge_structural_duplicates()

        return self._apply_validated(run)

    def insert_gate_before_buffers(
        self,
        gate_kind: GateKind,
        buffer_name_pattern: str,
        extra_input: str,
    ) -> TransformReport:
        """
        Insert gate_kind before each BUF whose name contains buffer_name_pattern.
        Example contest task: AND before buffers matching '_gc__', extra input _gc_ctrl.
        """

        def run() -> int:
            t = self._sync_transform()
            nl = t.nl
            added = 0
            for g in list(nl.gates.values()):
                if g.kind != GateKind.BUF or buffer_name_pattern not in g.name:
                    continue
                in_sig = g.inputs[0].key()
                out_sig = g.output.key()
                new_out = nl.next_wire_name()
                and_name = nl.next_gate_name()
                nl.add_gate(
                    Gate(
                        name=and_name,
                        kind=gate_kind,
                        output=Signal.parse(new_out),
                        inputs=[Signal.parse(in_sig), Signal.parse(extra_input)],
                    )
                )
                g.inputs = [Signal.parse(new_out)]
                added += 1
            t.refresh()
            return added

        return self._apply_validated(run)

    # Tool dispatch for agent
    def dispatch(self, tool: str, args: Dict[str, Any]) -> str:
        """Execute a named tool; used by agent front-end."""
        handlers = {
            "count_gates": self._fmt_count_gates,
            "max_logic_depth": self._fmt_max_logic_depth,
            "max_depth_in_cone": self._fmt_max_depth_in_cone,
            "max_design_depth": self._fmt_max_design_depth,
            "fanout_report": self._fmt_fanout,
            "path_exists_avoiding": self._fmt_path_avoid,
            "path_exists": self._fmt_path_exists,
            "list_paths": self._fmt_list_paths,
            "fanin_cone": self._fmt_fanin,
            "fanout_cone": self._fmt_fanout_cone,
            "functional_equivalence": self._fmt_equiv,
            "verify_equivalence": self._fmt_verify,
            "gate_info": self._fmt_gate_info,
            "insert_fanout_buffers": self._fmt_insert_buffers,
            "remove_dangling": self._fmt_remove_dangling,
            "rename_gate": self._fmt_rename_gate,
            "rename_wire": self._fmt_rename_wire,
            "collapse_inverters": self._fmt_collapse_inv,
            "remap_and_not": self._fmt_remap_and,
            "remap_nand_not": self._fmt_remap_nand,
            "replace_xnor_nor": self._fmt_xnor_nor,
            "replace_xor_nand": self._fmt_xor_nand,
            "optimize_cone_depth": self._fmt_opt_cone,
            "reduce_depth": self._fmt_reduce_depth,
            "merge_equivalent_gates": self._fmt_merge_eq,
            "merge_structural_duplicates": self._fmt_merge_dup,
            "insert_and_before_buffers": self._fmt_insert_and_bufs,
        }
        fn = handlers.get(tool)
        if not fn:
            return f"Unknown tool: {tool}"
        try:
            return fn(args)
        except TransformError as e:
            return f"Transform rejected (rolled back): {e}"
        except Exception as e:
            return f"Error: {e}"

    def _fmt_count_gates(self, _: Dict) -> str:
        c = self.count_gates()
        lines = ["Gate counts by type:"]
        total = 0
        for t in ("AND", "OR", "NOT", "NAND", "NOR", "XOR", "XNOR", "BUF", "DFF"):
            lines.append(f"  {t}: {c[t]}")
            total += c[t]
        lines.append(f"Total gates: {total}")
        return "\n".join(lines)

    def _fmt_max_logic_depth(self, a: Dict) -> str:
        d = self.max_logic_depth(a["src"], a["dst"])
        return f"The maximum logic depth from {a['src']} to {a['dst']} is {d}."

    def _fmt_max_depth_in_cone(self, a: Dict) -> str:
        d = self.max_depth_in_cone(a["signal"])
        return f"The maximum logic depth of the fanin cone of {a['signal']} is {d}."

    def _fmt_max_design_depth(self, _: Dict) -> str:
        return f"Maximum combinational logic depth: {self.max_design_depth()}."

    def _fmt_fanout(self, a: Dict) -> str:
        sig = a["signal"]
        gates = self.fanout_gates(sig)
        return (
            f"The fanout of {sig} is {len(gates)}.\n"
            f"Gates driven directly by {sig}: {', '.join(gates) if gates else 'none'}."
        )

    def _fmt_path_avoid(self, a: Dict) -> str:
        exists = self.path_exists(a["src"], a["dst"], {a.get("avoid", "")})
        yn = "Yes" if exists else "No"
        avoid = a.get("avoid", "")
        return f"{yn}. Path from {a['src']} to {a['dst']} avoiding {avoid} {'exists' if exists else 'does not exist'}."

    def _fmt_path_exists(self, a: Dict) -> str:
        exists = self.path_exists(a["src"], a["dst"])
        return f"{'Yes' if exists else 'No'}. Combinational path from {a['src']} to {a['dst']} {'exists' if exists else 'does not exist'}."

    def _fmt_list_paths(self, a: Dict) -> str:
        src, dst = a["src"], a["dst"]
        g = self._require_design().graph
        if self.design.gate_count() > 15_000:
            if g.has_combinational_path(src, dst):
                return (
                    f"At least one combinational path exists from {src} to {dst}. "
                    f"Full path enumeration skipped for large netlist "
                    f"({self.design.gate_count()} gates)."
                )
            return f"No combinational path from {src} to {dst}."
        paths, truncated = self.list_paths(src, dst)
        if not paths:
            return f"No paths from {src} to {dst}."
        lines = [f"Found {len(paths)} path(s):"]
        if truncated:
            lines.append("  (enumeration truncated at safety limit)")
        for i, p in enumerate(paths, 1):
            lines.append(f"  Path {i}: {' -> '.join(p)}")
        return "\n".join(lines)

    def _fmt_fanin(self, a: Dict) -> str:
        gates = self.fanin_cone_gates(a["signal"])
        return f"Fanin cone of {a['signal']} ({len(gates)} gates): {', '.join(gates)}."

    def _fmt_fanout_cone(self, a: Dict) -> str:
        gates = self.fanout_cone_gates(a["signal"])
        return f"Fanout cone of {a['signal']} ({len(gates)} gates): {', '.join(gates)}."

    def _fmt_equiv(self, a: Dict) -> str:
        eq = self.signals_equivalent(a["a"], a["b"])
        return f"{'Yes' if eq else 'No'}. {a['a']} and {a['b']} are{' ' if eq else ' NOT '}equivalent."

    def _fmt_verify(self, _: Dict) -> str:
        vr = self.verify_equivalent_to_baseline()
        if vr.ok:
            return "Yes. Current design is functionally equivalent to the loaded netlist."
        return f"No. {vr.message}"

    def _fmt_gate_info(self, a: Dict) -> str:
        g = self.gate_info(a["gate"])
        if g.kind == GateKind.DFF:
            ports = ", ".join(f"{k}={v.key()}" for k, v in g.dff_ports.items())
            return f"{a['gate']}: DFF, ports={ports}"
        ins = ", ".join(i.key() for i in g.inputs)
        return f"{a['gate']}: {g.kind.value.upper()}, out={g.output.key()}, in=[{ins}]"

    def _fmt_insert_buffers(self, a: Dict) -> str:
        r = self.insert_fanout_buffers(a.get("max_fanout", 4))
        return f"Inserted buffers for fanout <= {a.get('max_fanout', 4)}. Verified: {r.verification}"

    def _fmt_remove_dangling(self, _: Dict) -> str:
        r = self.remove_dangling()
        self._last_elim["dangling"] = r.metric
        return f"Removed {r.metric} dangling gate(s). Verified: {r.verification}"

    def _fmt_rename_gate(self, a: Dict) -> str:
        self.rename_gate(a["old"], a["new"])
        return f"Renamed gate {a['old']} to {a['new']}."

    def _fmt_rename_wire(self, a: Dict) -> str:
        self.rename_wire(a["old"], a["new"])
        return f"Renamed wire {a['old']} to {a['new']}."

    def _fmt_collapse_inv(self, _: Dict) -> str:
        r = self.collapse_back_to_back_inverters()
        return f"Collapsed inverter pairs. Verified: {r.verification}"

    def _fmt_remap_and(self, _: Dict) -> str:
        self.remap_to_and_not()
        return "Remapped to AND/NOT. Verified equivalent."

    def _fmt_remap_nand(self, _: Dict) -> str:
        self.remap_to_nand_not()
        return "Remapped to NAND/NOT. Verified equivalent."

    def _fmt_xnor_nor(self, _: Dict) -> str:
        self.replace_xnor_with_nor()
        return "Replaced XNOR with NOR implementations. Verified equivalent."

    def _fmt_xor_nand(self, _: Dict) -> str:
        self.replace_xor_with_nand()
        return "Replaced XOR with NAND implementations. Verified equivalent."

    def _fmt_opt_cone(self, a: Dict) -> str:
        sig, md = a["signal"], a.get("max_depth", 4)
        before = self.max_depth_in_cone(sig)
        if before <= md:
            return f"Cone of {sig} already at depth {before} (target {md})."
        self.optimize_cone_depth(sig, md)
        after = self.max_depth_in_cone(sig)
        return f"Optimized cone of {sig}: depth {before} -> {after}."

    def _fmt_reduce_depth(self, _: Dict) -> str:
        self.reduce_critical_path_depth()
        return "Applied critical-path depth reduction. Verified equivalent."

    def _fmt_merge_eq(self, _: Dict) -> str:
        self.merge_equivalent_gates()
        return "Merged functionally equivalent gates. Verified."

    def _fmt_merge_dup(self, _: Dict) -> str:
        self.merge_structural_duplicates()
        return "Merged structural duplicates. Verified."

    def _fmt_insert_and_bufs(self, a: Dict) -> str:
        r = self.insert_gate_before_buffers(
            GateKind.AND,
            a.get("pattern", "_gc__"),
            a.get("extra_input", "_gc_ctrl"),
        )
        return f"Inserted AND gates before matching buffers. Verified: {r.verification}"
