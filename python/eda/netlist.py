"""Gate-level netlist data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


GATE_TYPES = (
    "and",
    "or",
    "nand",
    "nor",
    "not",
    "buf",
    "xor",
    "xnor",
    "dff",
)


class GateKind(str, Enum):
    AND = "and"
    OR = "or"
    NAND = "nand"
    NOR = "nor"
    NOT = "not"
    BUF = "buf"
    XOR = "xor"
    XNOR = "xnor"
    DFF = "dff"


@dataclass(frozen=True)
class Signal:
    name: str
    bit: Optional[int] = None

    def key(self) -> str:
        if self.bit is None:
            return self.name
        return f"{self.name}[{self.bit}]"

    @staticmethod
    def parse(text: str) -> "Signal":
        text = text.strip()
        if text in ("1'b0", "1'b1"):
            return Signal(text)
        if "[" in text:
            base, rest = text.split("[", 1)
            bit = int(rest.rstrip("]"))
            return Signal(base, bit)
        return Signal(text)


@dataclass
class Gate:
    name: str
    kind: GateKind
    output: Signal
    inputs: List[Signal] = field(default_factory=list)
    # DFF named ports preserved for writing
    dff_ports: Dict[str, Signal] = field(default_factory=dict)

    def input_keys(self) -> List[str]:
        return [s.key() for s in self.inputs]

    def is_combinational(self) -> bool:
        return self.kind != GateKind.DFF


@dataclass
class Port:
    name: str
    direction: str  # input | output
    msb: int = 0
    lsb: int = 0

    @property
    def width(self) -> int:
        return abs(self.msb - self.lsb) + 1

    def bits(self) -> List[int]:
        if self.msb >= self.lsb:
            return list(range(self.lsb, self.msb + 1))
        return list(range(self.msb, self.lsb + 1))


@dataclass
class Netlist:
    module_name: str = "top"
    ports: List[Port] = field(default_factory=list)
    wires: Set[str] = field(default_factory=set)
    wire_widths: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    gates: Dict[str, Gate] = field(default_factory=dict)
    gate_order: List[str] = field(default_factory=list)
    raw_header_lines: List[str] = field(default_factory=list)
    raw_wire_lines: List[str] = field(default_factory=list)

    def clone(self) -> "Netlist":
        import copy

        return copy.deepcopy(self)

    def primary_inputs(self) -> List[Port]:
        return [p for p in self.ports if p.direction == "input"]

    def primary_outputs(self) -> List[Port]:
        return [p for p in self.ports if p.direction == "output"]

    def pi_signals(self) -> Set[str]:
        keys: Set[str] = set()
        for p in self.primary_inputs():
            if p.width == 1:
                keys.add(p.name)
            else:
                for b in p.bits():
                    keys.add(f"{p.name}[{b}]")
        return keys

    def po_signals(self) -> Set[str]:
        keys: Set[str] = set()
        for p in self.primary_outputs():
            if p.width == 1:
                keys.add(p.name)
            else:
                for b in p.bits():
                    keys.add(f"{p.name}[{b}]")
        return keys

    def gate_by_output(self) -> Dict[str, Gate]:
        return {g.output.key(): g for g in self.gates.values()}

    def next_gate_name(self, prefix: str = "g") -> str:
        idx = len(self.gates)
        while f"{prefix}{idx}" in self.gates:
            idx += 1
        return f"{prefix}{idx}"

    def next_wire_name(self, prefix: str = "n") -> str:
        idx = 1
        while prefix + str(idx) in self.wires:
            idx += 1
        name = prefix + str(idx)
        self.wires.add(name)
        return name

    def add_gate(self, gate: Gate) -> None:
        self.gates[gate.name] = gate
        if gate.name not in self.gate_order:
            self.gate_order.append(gate.name)

    def remove_gate(self, name: str) -> None:
        if name in self.gates:
            del self.gates[name]
        if name in self.gate_order:
            self.gate_order.remove(name)

    def count_by_type(self) -> Dict[str, int]:
        counts = {t.upper(): 0 for t in GATE_TYPES}
        for g in self.gates.values():
            counts[g.kind.value.upper()] += 1
        return counts
