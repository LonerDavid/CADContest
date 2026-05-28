"""Extended analysis/transform formatters used by rule-based agent (beyond core dispatch)."""

from __future__ import annotations

from typing import Any, Dict

from .api import EDAEngine, TransformError
from .netlist import GateKind


def _build_bool_expr(nl: Any, g: Any, sig: str, depth: int, max_depth: int, visited: set) -> str:
    if depth > max_depth or sig in visited:
        return sig
    visited = visited | {sig}
    drv = g.driver.get(sig)
    if not drv or drv == "PI" or str(drv).startswith("DFF:"):
        return sig
    gate = nl.gates.get(drv)
    if not gate:
        return sig
    kind = gate.kind.value.upper()
    if not gate.inputs:
        return sig
    sub = [_build_bool_expr(nl, g, i.key(), depth + 1, max_depth, visited) for i in gate.inputs]
    if kind == "NOT":
        return f"NOT({sub[0]})"
    if kind == "BUF":
        return sub[0]
    return f"{kind}({', '.join(sub)})"


def dispatch_extra(engine: EDAEngine, tool: str, args: Dict[str, Any]) -> str | None:
    """Return formatted result, or None if tool is not handled here."""
    g = engine.design.graph if engine.design else None
    if g is None:
        return "Error: No design loaded."

    if tool == "fanin_cone_gate_count":
        n = len(g.fanin_cone_gates(args["signal"]))
        return f"The fanin cone of {args['signal']} contains {n} gates."

    if tool == "gates_driven_by":
        sig = args["signal"]
        if sig in engine.design.netlist.gates:
            sig = engine.design.netlist.gates[sig].output.key()
        gates = g.gates_driven_by(sig)
        return f"Gates driven by {sig}: {', '.join(gates) if gates else 'none'}."

    if tool == "immediate_successors":
        s = g.immediate_successors(args["gate"])
        return f"Immediate successors of {args['gate']}: {', '.join(s) if s else 'none'}."

    if tool == "list_primary_outputs":
        lines = ["Primary outputs:"]
        for p in engine.design.netlist.primary_outputs():
            w = p.width
            lines.append(f"  {p.name}: {w} bit(s)" if w > 1 else f"  {p.name}: 1 bit")
        return "\n".join(lines)

    if tool == "list_primary_inputs":
        lines = ["Primary inputs:"]
        for p in engine.design.netlist.primary_inputs():
            w = p.width
            lines.append(f"  {p.name}: {w} bit(s)" if w > 1 else f"  {p.name}: 1 bit")
        return "\n".join(lines)

    if tool == "list_gates_by_type":
        kind = GateKind(args["type"].lower())
        gates = g.list_gates_by_type(kind)
        lines = [f"{args['type'].upper()} gates ({len(gates)}):"]
        for gt in gates:
            ins = ", ".join(i.key() for i in gt.inputs)
            lines.append(f"  {gt.name}: out={gt.output.key()}, in=[{ins}]")
        return "\n".join(lines)

    if tool == "largest_fanin_cone_output":
        sig, c = g.largest_fanin_cone_output()
        return f"Output {sig} has the largest fanin cone ({c} gates)."

    if tool == "count_gate_type":
        k = args["type"].upper()
        return f"{k} gates: {engine.count_gates().get(k, 0)}."

    if tool == "count_not_gates":
        return f"NOT gates: {engine.count_gates()['NOT']}."

    if tool == "depends_on":
        yn = g.depends_on(args["output"], args["input"])
        return f"{'Yes' if yn else 'No'}. {args['output']} {'depends on' if yn else 'does not depend on'} {args['input']}."

    if tool == "outputs_depth_gt":
        outs = g.outputs_depth_gt(args.get("threshold", 4))
        return f"Outputs with depth > {args.get('threshold', 4)}: {', '.join(outs) or 'none'}."

    if tool == "pi_dff_depth":
        return f"Maximum PI-to-DFF D depth: {g.pi_to_dff_d_depth()}."

    if tool == "highest_fanout_pi":
        sig, fo = g.highest_fanout_pi()
        return f"Highest fanout PI: {sig} (fanout {fo})."

    if tool == "max_fanout_signal":
        return f"Maximum fanout of {args['signal']}: {g.fanout_count(args['signal'])}."

    if tool == "reg_to_reg_paths":
        paths = g.register_to_register_paths()
        if not paths:
            return "No register-to-register paths."
        lines = [f"R2R paths ({len(paths)}):"]
        for i, p in enumerate(paths[:30], 1):
            lines.append(f"  {i}. {' -> '.join(p)}")
        return "\n".join(lines)

    if tool == "dff_enable_hold":
        return f"Flip-flops with enable/hold on D: {g.dff_enable_hold_count()}."

    if tool == "dffs_on_clock":
        dffs = g.dffs_on_clock(args["clock"])
        return f"DFFs on clock {args['clock']}: {', '.join(dffs) or 'none'}."

    if tool == "zero_length_paths":
        paths = g.zero_length_paths()
        if not paths:
            return "No PI-to-PO direct connections."
        return "Direct connections:\n" + "\n".join(f"  {a} -> {b}" for a, b in paths)

    if tool == "insert_dedicated_buffers":
        try:
            n = engine._sync_transform().insert_dedicated_buffers(args["signal"])
            engine.design.refresh()
            vr = engine.verify_equivalent_to_baseline()
            if not vr.ok:
                raise TransformError(vr.message)
            return f"Inserted {n} dedicated buffer(s) on {args['signal']}."
        except TransformError as e:
            return f"Transform rejected: {e}"

    if tool == "propagate_and_const0":
        n = engine._sync_transform().propagate_and_const0()
        engine.design.refresh()
        engine._last_elim["and_const0"] = n
        return f"Eliminated {n} AND gate(s) with const-0."

    if tool == "propagate_or_const1":
        n = engine._sync_transform().propagate_or_const1()
        engine.design.refresh()
        engine._last_elim["or_const1"] = n
        return f"Eliminated {n} OR gate(s) with const-1."

    if tool == "propagate_nand_constants":
        n = engine._sync_transform().propagate_nand_constants()
        engine.design.refresh()
        engine._last_elim["nand"] = n
        return f"Eliminated {n} NAND gate(s) with constant inputs."

    if tool == "propagate_nor_constants":
        n = engine._sync_transform().propagate_nor_constants()
        engine.design.refresh()
        engine._last_elim["nor"] = n
        return f"Eliminated {n} NOR gate(s) with constant inputs."

    if tool == "replace_nand_const1":
        try:
            engine._sync_transform().replace_nand_const1_with_not()
            engine.design.refresh()
            if not engine.verify_equivalent_to_baseline().ok:
                raise TransformError("Equivalence failed")
            return "Replaced NAND(const1) with NOT."
        except TransformError as e:
            return f"Transform rejected: {e}"

    if tool == "remap_cone_nand_not":
        sig = args["signal"]
        n = engine._sync_transform().remap_cone_to_nand_not(sig)
        engine.design.refresh()
        return f"Restructured cone of {sig}; NAND count ~{n}."

    if tool == "decompose_xor_cone":
        n = engine._sync_transform().decompose_xor_in_cone(args["signal"])
        engine.design.refresh()
        return f"Decomposed XOR in cone of {args['signal']}."

    if tool == "remove_redundant":
        try:
            n = engine._sync_transform().remove_redundant_gates()
            engine.design.refresh()
            return f"Removed {n} redundant gate(s)."
        except Exception as e:
            return f"Error: {e}"

    if tool == "is_symmetric":
        yn = g.is_symmetric(args["signal"], args["a"], args["b"])
        return f"{'Yes' if yn else 'No'}. Symmetric in {args['a']}, {args['b']}."

    if tool == "is_cut":
        yn = g.is_cut_node(args["signal"])
        return f"{'Yes' if yn else 'No'}. Cut node {args['signal']}."

    if tool == "floating_signals":
        fl = g.floating_signals()
        return f"Floating signals: {len(fl)}."

    if tool == "output_always_zero":
        yn = g.output_always_zero(args["signal"])
        return f"{'Yes' if yn else 'No'}. {args['signal']} always 0."

    if tool == "shared_cone_gates":
        s = sorted(g.shared_cone_gates(args["a"], args["b"]))
        return f"Shared gates: {', '.join(s) if s else 'none'}."

    if tool == "nand_equiv_pair":
        p = g.nand_equivalent_pair_for(args["signal"])
        if p:
            return f"Yes. NAND({p[0]}, {p[1]}) equiv {args['signal']}."
        return f"No NAND pair equiv to {args['signal']}."

    if tool == "gate_on_max_depth_path":
        yn = g.on_max_depth_path(args["gate"])
        return f"{'Yes' if yn else 'No'}. {args['gate']} on max-depth path."

    if tool == "every_path_through":
        yn = g.every_path_through(args["src"], args["dst"], args["gate"])
        return f"{'Yes' if yn else 'No'}. All paths through {args['gate']}."

    if tool == "pi_po_count":
        ni = len(engine.design.netlist.primary_inputs())
        no = len(engine.design.netlist.primary_outputs())
        return f"Primary inputs: {ni}, primary outputs: {no}."

    if tool == "gates_reachable":
        gates = sorted(g.fanout_cone_gates(args["signal"]))
        return f"Reachable from {args['signal']}: {len(gates)} gates."

    if tool == "articulation_points":
        aps = g.articulation_points(args["src"], args["dst"])
        return f"Articulation points: {', '.join(aps) if aps else 'none'}."

    if tool == "reconnect_input":
        try:
            engine._sync_transform().reconnect_gate_input(
                args["gate"], args["pin"], args["signal"]
            )
            engine.design.refresh()
            if not engine.verify_equivalent_to_baseline().ok:
                raise TransformError("Equivalence failed")
            return f"Reconnected {args['gate']} input to {args['signal']}."
        except TransformError as e:
            return f"Transform rejected: {e}"

    if tool == "cone_gate_type_counts":
        c = g.gate_type_counts_in_cone(args["signal"])
        lines = [f"Cone of {args['signal']}:"]
        for k, v in c.items():
            if v:
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    if tool == "gates_with_constants":
        found = g.gates_with_constant_inputs()
        if not found:
            return "No constant-driven gates."
        return "\n".join(f"  {a} ({b}): {c}" for a, b, c in found)

    if tool == "gates_with_const1_inputs":
        from .graph import CONST1
        found = [(gobj.name, gobj.kind.value) for gobj in engine.design.netlist.gates.values()
                 if gobj.kind.value not in ("DFF",) and any(i.key() == CONST1 for i in gobj.inputs)]
        if not found:
            return "No gates with inputs tied to 1'b1."
        lines = [f"Gates with 1'b1 input: {len(found)}"]
        for gname, gkind in found[:50]:
            lines.append(f"  {gname} ({gkind})")
        if len(found) > 50:
            lines.append(f"  ... and {len(found)-50} more")
        return "\n".join(lines)

    if tool == "last_elim_count":
        key = args.get("type", "")
        count = engine._last_elim.get(key, 0)
        labels = {
            "and_const0": "AND gates eliminated by constant-0 propagation",
            "or_const1": "OR gates eliminated by constant-1 propagation",
            "nand": "NAND gates eliminated by constant propagation",
            "nor": "NOR gates eliminated by constant propagation",
            "dangling": "dangling gates removed",
        }
        label = labels.get(key, f"{key} eliminated")
        return f"{count} {label}."

    if tool == "boolean_expression":
        sig = args["signal"]
        nl = engine.design.netlist
        expr = _build_bool_expr(nl, g, sig, 0, 12, set())
        return f"Boolean expression for {sig}: {expr}"

    return None
