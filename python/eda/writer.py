"""Verilog netlist writer."""

from __future__ import annotations

from pathlib import Path
from typing import List

from .netlist import Gate, GateKind, Netlist, Port


def _format_signal(sig) -> str:
    if sig.name in ("1'b0", "1'b1"):
        return sig.name
    if sig.bit is None:
        return sig.name
    return f"{sig.name}[{sig.bit}]"


def _format_port_list(ports: List[Port]) -> str:
    return ", ".join(p.name for p in ports)


def _format_wire_decl(name: str, width: tuple | None) -> str:
    if width and width != (0, 0) and abs(width[0] - width[1]) > 0 or (
        width and width[0] != width[1]
    ):
        msb, lsb = width
        return f"  wire [{msb}:{lsb}] {name};"
    if width and (width[0] != 0 or width[1] != 0):
        msb, lsb = width
        if msb != lsb:
            return f"  wire [{msb}:{lsb}] {name};"
    return f"  wire {name};"


def write_verilog(nl: Netlist, path: str | Path) -> None:
    lines: List[str] = []
    lines.append("")
    lines.append(f"module {nl.module_name}({_format_port_list(nl.ports)});")

    for p in nl.ports:
        if p.width == 1 and p.msb == p.lsb:
            lines.append(f"  {p.direction} {p.name};")
        else:
            lines.append(f"  {p.direction} [{p.msb}:{p.lsb}] {p.name};")

    # Collect wires used but not ports
    port_names = {p.name for p in nl.ports}
    extra_wires = sorted(nl.wires - port_names)
    if extra_wires:
        # Group consecutive scalar wires on one line like original style
        chunk: List[str] = []
        for w in extra_wires:
            if w in nl.wire_widths:
                if chunk:
                    lines.append(f"  wire {', '.join(chunk)};")
                    chunk = []
                lines.append(_format_wire_decl(w, nl.wire_widths[w]))
            else:
                chunk.append(w)
                if len(chunk) >= 16:
                    lines.append(f"  wire {', '.join(chunk)};")
                    chunk = []
        if chunk:
            lines.append(f"  wire {', '.join(chunk)};")

    # Re-declare port wires with bus info (matching benchmark style)
    for p in nl.ports:
        if p.width > 1:
            lines.append(f"  wire [{p.msb}:{p.lsb}] {p.name};")

    for gname in nl.gate_order:
        g = nl.gates.get(gname)
        if g is None:
            continue
        if g.kind == GateKind.DFF:
            port_strs = []
            for pname in ("RN", "SN", "CK", "D", "Q"):
                if pname in g.dff_ports:
                    port_strs.append(f".{pname}({_format_signal(g.dff_ports[pname])})")
            lines.append(f"  dff {g.name}({', '.join(port_strs)});")
        elif g.kind in (GateKind.NOT, GateKind.BUF):
            lines.append(
                f"  {g.kind.value} {g.name}({_format_signal(g.output)}, {_format_signal(g.inputs[0])});"
            )
        else:
            args = [_format_signal(g.output)] + [_format_signal(i) for i in g.inputs]
            lines.append(f"  {g.kind.value} {g.name}({', '.join(args)});")

    lines.append("endmodule")
    lines.append("")
    Path(path).write_text("\n".join(lines))
