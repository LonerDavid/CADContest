"""Verilog netlist parser for flat gate-level designs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from .netlist import Gate, GateKind, Netlist, Port, Signal

MODULE_RE = re.compile(r"module\s+(\w+)\s*\((.*?)\)\s*;", re.DOTALL)
PORT_SCALAR_RE = re.compile(r"^\s*(input|output|inout)\s+([\w,\s]+)\s*;")
PORT_BUS_RE = re.compile(r"^\s*(input|output|inout)\s*\[(\d+):(\d+)\]\s+([\w,\s]+)\s*;")
WIRE_SCALAR_RE = re.compile(r"^\s*wire\s+([\w,\s]+)\s*;")
WIRE_BUS_RE = re.compile(r"^\s*wire\s*\[(\d+):(\d+)\]\s+([\w,\s]+)\s*;")
GATE_POS_RE = re.compile(
    r"^\s*(and|or|nand|nor|not|buf|xor|xnor)\s+(\w+)\s*\(([^)]+)\)\s*;",
    re.IGNORECASE,
)
DFF_RE = re.compile(r"^\s*dff\s+(\w+)\s*\(([^)]+)\)\s*;", re.IGNORECASE)
DFF_PORT_RE = re.compile(r"\.(\w+)\s*\(([^)]+)\)")


def _split_args(arg_str: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    cur: List[str] = []
    for ch in arg_str:
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return parts


def parse_verilog(path: str | Path) -> Netlist:
    text = Path(path).read_text()
    lines = text.splitlines()
    nl = Netlist()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("//"):
            i += 1
            continue
        m = MODULE_RE.match(line)
        if m:
            nl.module_name = m.group(1)
            port_names = [p.strip() for p in m.group(2).split(",") if p.strip()]
            nl.raw_header_lines.append(lines[i])
            i += 1
            break
        i += 1

    declared_ports: dict[str, Port] = {}
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("endmodule"):
            break
        if stripped.startswith("wire"):
            nl.raw_wire_lines.append(line.rstrip())
            bm = WIRE_BUS_RE.match(stripped)
            if bm:
                msb, lsb, names = int(bm.group(1)), int(bm.group(2)), bm.group(3)
                for name in names.split(","):
                    name = name.strip()
                    if name:
                        nl.wires.add(name)
                        nl.wire_widths[name] = (msb, lsb)
            else:
                sm = WIRE_SCALAR_RE.match(stripped)
                if sm:
                    for name in sm.group(1).split(","):
                        name = name.strip()
                        if name:
                            nl.wires.add(name)
            i += 1
            continue
        '''
        pm = PORT_BUS_RE.match(stripped)
        if pm:
            direction, msb, lsb, name = pm.group(1), int(pm.group(2)), int(pm.group(3)), pm.group(4)
            declared_ports[name] = Port(name, direction, msb, lsb)
            nl.wires.add(name)
            nl.wire_widths[name] = (msb, lsb)
            i += 1
            continue
        pm = PORT_SCALAR_RE.match(stripped)
        if pm:
            direction, name = pm.group(1), pm.group(2)
            declared_ports[name] = Port(name, direction, 0, 0)
            nl.wires.add(name)
            i += 1
            continue
        '''
        pm = PORT_BUS_RE.match(stripped)
        if pm:
            direction, msb, lsb, names = pm.group(1), int(pm.group(2)), int(pm.group(3)), pm.group(4)
            for name in names.split(","):
                name = name.strip()
                if name:
                    declared_ports[name] = Port(name, direction, msb, lsb)
                    nl.wires.add(name)
                    nl.wire_widths[name] = (msb, lsb)
            i += 1
            continue
        pm = PORT_SCALAR_RE.match(stripped)
        if pm:
            direction, names = pm.group(1), pm.group(2)
            for name in names.split(","):
                name = name.strip()
                if name:
                    declared_ports[name] = Port(name, direction, 0, 0)
                    nl.wires.add(name)
            i += 1
            continue

        gm = GATE_POS_RE.match(stripped)
        if gm:
            kind = GateKind(gm.group(1).lower())
            gname = gm.group(2)
            args = _split_args(gm.group(3))
            sigs = [Signal.parse(a) for a in args]
            gate = Gate(name=gname, kind=kind, output=sigs[0], inputs=sigs[1:])
            nl.add_gate(gate)
            i += 1
            continue

        dm = DFF_RE.match(stripped)
        if dm:
            gname = dm.group(1)
            ports_raw = dm.group(2)
            dff_ports = {}
            for pm in DFF_PORT_RE.finditer(ports_raw):
                dff_ports[pm.group(1)] = Signal.parse(pm.group(2))
            q = dff_ports.get("Q", Signal("q"))
            d = dff_ports.get("D", Signal("d"))
            gate = Gate(
                name=gname,
                kind=GateKind.DFF,
                output=q,
                inputs=[d],
                dff_ports=dff_ports,
            )
            nl.add_gate(gate)
            i += 1
            continue

        i += 1

    # Preserve port order from module header when possible
    ordered: List[Port] = []
    seen = set()
    for pname in port_names:
        if pname in declared_ports:
            ordered.append(declared_ports[pname])
            seen.add(pname)
    for pname, port in declared_ports.items():
        if pname not in seen:
            ordered.append(port)
    nl.ports = ordered
    return nl
