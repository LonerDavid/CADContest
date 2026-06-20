"""
Step 1: Internal design representation as a directed acyclic graph (DAG).

Nodes are gate instances and primary ports; edges follow signal flow (driver -> load).
Combinational logic forms a DAG; DFF Q outputs are treated as additional primary inputs
for combinational analysis (register boundaries).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .graph import CircuitGraph
from .netlist import Gate, GateKind, Netlist, Port, Signal
from .parser import parse_verilog
from .writer import write_verilog


@dataclass
class DAGNode:
    """A node in the design DAG."""

    id: str
    kind: str  # "pi" | "po" | "gate" | "const" | "dff_q"
    gate_name: Optional[str] = None
    gate_type: Optional[str] = None
    signal: Optional[str] = None


@dataclass
class DesignDAG:
    """
    Canonical internal representation: netlist + connectivity graph (DAG).

    Built by the Verilog parser; consumed by analysis/transform APIs and the writer.
    """

    netlist: Netlist
    graph: CircuitGraph = field(repr=False)
    nodes: Dict[str, DAGNode] = field(default_factory=dict)
    edges: List[Tuple[str, str]] = field(default_factory=list)  # (from_node, to_node)

    @classmethod
    def from_verilog(cls, path: str) -> "DesignDAG":
        nl = parse_verilog(path)
        return cls.from_netlist(nl)

    @classmethod
    def from_netlist(cls, nl: Netlist) -> "DesignDAG":
        g = CircuitGraph.from_netlist(nl)
        dag = cls(netlist=nl, graph=g)
        dag._build_topology()
        return dag

    def _build_topology(self) -> None:
        self.nodes.clear()
        self.edges.clear()

        for p in self.netlist.primary_inputs():
            for bit in p.bits() if p.width > 1 else [None]:
                sig = f"{p.name}[{bit}]" if bit is not None else p.name
                nid = f"PI:{sig}"
                self.nodes[nid] = DAGNode(id=nid, kind="pi", signal=sig)

        for q in self.graph.dff_q_signals:
            nid = f"DFF_Q:{q}"
            self.nodes[nid] = DAGNode(id=nid, kind="dff_q", signal=q)

        for g in self.netlist.gates.values():
            nid = f"G:{g.name}"
            self.nodes[nid] = DAGNode(
                id=nid,
                kind="gate",
                gate_name=g.name,
                gate_type=g.kind.value,
                signal=g.output.key(),
            )

        for po in self.netlist.po_signals():
            nid = f"PO:{po}"
            self.nodes[nid] = DAGNode(id=nid, kind="po", signal=po)

        # Edges: driver signal -> gate/load
        for gate in self.netlist.gates.values():
            g_nid = f"G:{gate.name}"
            if gate.kind == GateKind.DFF:
                d_sig = gate.dff_ports.get("D", gate.inputs[0]).key()
                pred = self._signal_driver_node(d_sig)
                if pred:
                    self.edges.append((pred, g_nid))
            else:
                for inp in gate.inputs:
                    pred = self._signal_driver_node(inp.key())
                    if pred:
                        self.edges.append((pred, g_nid))

        # PO edges from their drivers
        for po in self.netlist.po_signals():
            pred = self._signal_driver_node(po)
            if pred:
                self.edges.append((pred, f"PO:{po}"))

    def _signal_driver_node(self, sig: str) -> Optional[str]:
        from .graph import is_constant

        if is_constant(sig):
            return None
        if sig in self.netlist.pi_signals():
            return f"PI:{sig}"
        if sig in self.graph.dff_q_signals:
            return f"DFF_Q:{sig}"
        drv = self.graph.driver.get(sig)
        if drv and drv not in ("PI",) and not str(drv).startswith("DFF:"):
            return f"G:{drv}"
        return None

    def clone_netlist(self) -> Netlist:
        return copy.deepcopy(self.netlist)

    def refresh(self) -> None:
        """Rebuild graph and DAG topology after netlist mutation."""
        self.netlist._compact_gate_order()
        self.graph = CircuitGraph.from_netlist(self.netlist)
        self._build_topology()

    def write_verilog(self, path: str) -> None:
        write_verilog(self.netlist, path)

    def gate_count(self) -> int:
        return len(self.netlist.gates)

    def count_by_type(self) -> Dict[str, int]:
        return self.netlist.count_by_type()
