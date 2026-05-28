"""
Step 2: Sanity checks and equivalence verification before committing netlist changes.

Contest scoring gives zero points on functional or constraint violations — transforms
must pass these checks (or roll back) before a modification is finalized.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .dag import DesignDAG
from .graph import CircuitGraph


@dataclass
class ConstraintSpec:
    max_fanout: Optional[int] = None
    max_depth: Optional[int] = None
    max_depth_signals: Optional[List[str]] = None  # per-output depth limits
    require_equivalence: bool = True


@dataclass
class VerificationResult:
    ok: bool
    message: str
    details: List[str]

    @classmethod
    def pass_(cls, msg: str = "OK") -> "VerificationResult":
        return cls(True, msg, [])

    @classmethod
    def fail(cls, msg: str, details: Optional[List[str]] = None) -> "VerificationResult":
        return cls(False, msg, details or [])


class DesignVerifier:
    """Functional equivalence and structural constraint checks."""

    def __init__(self, reference: DesignDAG):
        self.reference = reference
        self.ref_graph = reference.graph

    def functionally_equivalent(self, candidate: DesignDAG) -> VerificationResult:
        g_cur = candidate.graph
        checks: List[str] = []

        for po in sorted(self.ref_graph.nl.po_signals()):
            if not self._signals_equivalent(self.ref_graph, g_cur, po, po):
                return VerificationResult.fail(
                    f"Primary output {po} is not functionally equivalent."
                )
            checks.append(po)

        for d in sorted(self.ref_graph.dff_d_signals):
            if not self._signals_equivalent(self.ref_graph, g_cur, d, d):
                return VerificationResult.fail(
                    f"DFF D-input logic {d} is not functionally equivalent."
                )
            checks.append(d)

        return VerificationResult.pass_(f"Equivalent on {len(checks)} observation point(s).")

    @staticmethod
    def _signals_equivalent(g1: CircuitGraph, g2: CircuitGraph, a: str, b: str) -> bool:
        return g1.functionally_equivalent(a, b)

    def check_max_fanout(self, dag: DesignDAG, limit: int) -> VerificationResult:
        violations = []
        for sig, loads in dag.graph.loads.items():
            if len(loads) > limit:
                violations.append(f"{sig}: fanout {len(loads)} > {limit}")
        if violations:
            return VerificationResult.fail(
                f"Fanout constraint violated (max {limit}).", violations[:20]
            )
        return VerificationResult.pass_(f"All signals have fanout <= {limit}.")

    def check_max_depth(
        self, dag: DesignDAG, limit: int, signals: Optional[List[str]] = None
    ) -> VerificationResult:
        targets = signals or sorted(dag.netlist.po_signals())
        violations = []
        for sig in targets:
            d = dag.graph.max_depth_in_cone(sig)
            if d > limit:
                violations.append(f"{sig}: depth {d} > {limit}")
        if violations:
            return VerificationResult.fail(
                f"Depth constraint violated (max {limit}).", violations
            )
        return VerificationResult.pass_(f"All targets have depth <= {limit}.")

    def verify_transform(
        self,
        before: DesignDAG,
        after: DesignDAG,
        constraints: Optional[ConstraintSpec] = None,
    ) -> VerificationResult:
        spec = constraints or ConstraintSpec()

        if spec.require_equivalence:
            ref = DesignVerifier(before)
            eq = ref.functionally_equivalent(after)
            if not eq.ok:
                return eq

        if spec.max_fanout is not None:
            fo = self.check_max_fanout(after, spec.max_fanout)
            if not fo.ok:
                return fo

        if spec.max_depth is not None:
            dp = self.check_max_depth(after, spec.max_depth, spec.max_depth_signals)
            if not dp.ok:
                return dp

        return VerificationResult.pass_("Transform passed all verification checks.")
