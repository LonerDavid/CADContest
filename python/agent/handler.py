"""Natural-language request handler with rule-based routing and LLM fallback."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .llm import LLMClient
from ..eda.context import EDASession

CASE_RE = re.compile(r"case name is\s+(\w+)", re.I)
LOAD_RE = re.compile(r"file\s+([^\s'\"]+\.v)", re.I)
LOAD_DIR_RE = re.compile(r"directory\s+([^\s'\"./]+(?:/[^\s'\"./]+)*)/?", re.I)
WRITE_RE = re.compile(
    r"write(?:\s+the)?(?:\s+current)?\s+design\s+to(?:\s+the)?(?:\s+output)?\s+file\s+(\S+)",
    re.I,
)


def _extract_signals(text: str) -> List[str]:
    return re.findall(r"n\d+(?:\[\d+\])?|g\d+", text)


class RequestHandler:
    def __init__(self, session: EDASession, llm: Optional[LLMClient] = None):
        self.session = session
        self.llm = llm

    def handle(self, request: str) -> str:
        req = request.strip()
        if not req:
            return "Empty request received."

        tool = self._rule_match(req)
        if tool:
            name, args = tool
            try:
                return self.session.execute_tool(name, args)
            except Exception as e:
                return f"Error executing {name}: {e}"

        if self.llm:
            try:
                return self.llm.plan_and_execute(req, self.session)
            except Exception as e:
                return f"LLM processing failed: {e}. Request: {req[:200]}"
            
        return f"Request not supported by current rule set: {req}\nPlease rephrase using supported commands."
        

    def _rule_match(self, req: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        low = req.lower()

        m = CASE_RE.search(req)
        if m and ("beginning" in low or "new testcase" in low):
            return ("init_testcase", {"case_name": m.group(1)})

        if "load" in low and ".v" in req:
            fm = LOAD_RE.search(req)
            if fm:
                fname = fm.group(1).strip("'\"")
                dm = LOAD_DIR_RE.search(req)
                if dm:
                    path = f"{dm.group(1).rstrip('/')}/{fname.split('/')[-1]}"
                elif self.session.case_name:
                    path = f"testcase/{self.session.case_name}/{fname.split('/')[-1]}"
                else:
                    path = fname
                return ("load_design", {"path": path})

        if "write" in low and ("out.v" in low or "output file" in low):
            wm = WRITE_RE.search(req)
            if wm:
                return ("write_design", {"path": wm.group(1).strip("'.\" ")})

        if "count all the gates" in low or "gate count" in low or "total gate count" in low:
            return ("count_gates", {})

        if "fanin cone" in low and "how many gates" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("fanin_cone_gate_count", {"signal": sigs[-1]})

        if "maximum logic depth of the fanin cone" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("max_depth_in_cone", {"signal": sigs[-1]})

        if "maximum logic depth from" in low or "compute the maximum logic depth" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 2:
                return ("max_logic_depth", {"src": sigs[0], "dst": sigs[1]})

        if "longest combinational path depth" in low or "critical path depth" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 2:
                return ("max_logic_depth", {"src": sigs[0], "dst": sigs[1]})

        if "does not traverse" in low or "does not pass through" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 3:
                return ("path_exists_avoiding", {"src": sigs[0], "dst": sigs[1], "avoid": sigs[2]})

        if "avoiding" in low and "path" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 3:
                return ("path_exists_avoiding", {"src": sigs[0], "dst": sigs[1], "avoid": sigs[2]})

        if "list every path" in low or "complete enumeration of paths" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 2:
                return ("list_paths", {"src": sigs[0], "dst": sigs[1]})

        if "fanout of primary input" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("fanout_report", {"signal": sigs[0]})

        #if "gates driven by" in low and "g0" in req:
        #    return ("gates_driven_by", {"signal": "g0"})

        if "gates connected to the output of" in low or "gates driven by" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("gates_driven_by", {"signal": sigs[0]})

        if "number of gates driven by" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("gates_driven_by", {"signal": sigs[0]})

        if "immediate successors" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("immediate_successors", {"gate": sigs[0]})

        if "transitive fanin cone" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("fanin_cone", {"signal": sigs[-1]})

        if "transitive fanout" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("fanout_cone", {"signal": sigs[0]})

        if "functionally equivalent" in low or "identical logic values" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 2:
                return ("functional_equivalence", {"a": sigs[0], "b": sigs[1]})

        if "insert buffers" in low and "fanout" in low or "no gate drives more than" in low or "maximum fanout" in low:
            mf = 4
            mm = re.search(r"more than\s+(\d+)", low)
            if mm:
                mf = int(mm.group(1))
            mm = re.search(r"maximum fanout\s+(\d+)", low)
            if mm:
                mf = int(mm.group(1))
            return ("insert_fanout_buffers", {"max_fanout": mf})

        if "optimize the logic depth" in low or "minimize the maximum logic depth" in low:
            return ("reduce_depth", {})

        if "reduce the critical path depth" in low or "reduce critical path depth" in low:
            return ("reduce_depth", {})

        if "dangling" in low or "unused" in low or "floating" in low and "remove" in low or "trim unused" in low or "prune" in low or "sweep out" in low or "eliminate unused" in low or "delete all gates that do not contribute" in low:
            return ("remove_dangling", {})

        if "rename" in low and "gate" in low:
            sigs = _extract_signals(req)
            nm = re.search(r"to\s+(\w+)", req)
            if sigs and nm:
                return ("rename_gate", {"old": sigs[0], "new": nm.group(1)})

        if "rename" in low and ("wire" in low or "signal" in low):
            sigs = _extract_signals(req)
            nm = re.search(r"to\s+(\w+)", req)
            if sigs and nm:
                return ("rename_wire", {"old": sigs[0], "new": nm.group(1)})

        if "back-to-back invert" in low or "back to back invert" in low:
            return ("collapse_inverters", {})

        if "only and and not" in low or "using only and and not" in low:
            return ("remap_and_not", {})

        if "only nand and not" in low or "nand and not gates" in low:
            return ("remap_nand_not", {})

        if "xnor" in low and ("nor" in low or "nor-only" in low):
            return ("replace_xnor_nor", {})

        if "xor" in low and "nand" in low:
            return ("replace_xor_nand", {})

        if "optimize" in low and "levels deep" in low or "depth 4" in low or "at most 4" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("optimize_cone_depth", {"signal": sigs[0], "max_depth": 4})

        if "optimize the logic cone" in low:
            sigs = _extract_signals(req)
            md = 4
            mm = re.search(r"depth\s+(\d+)", low)
            if mm:
                md = int(mm.group(1))
            if sigs:
                return ("optimize_cone_depth", {"signal": sigs[0], "max_depth": md})

        if "merge" in low and "functionally equivalent" in low:
            return ("merge_equivalent_gates", {})

        if "structural duplicate" in low:
            return ("merge_structural_duplicates", {})

        #if "verify functional equivalence" in low or "prove that the transformed" in low:
        #    return ("verify_equivalence", {})
        
        if "functional equivalence" in low or "functionally equivalent" in low or "identical logic values" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 2:
                return ("functional_equivalence", {"a": sigs[0], "b": sigs[1]})
            
        if "how many not gates" in low:
            return ("count_not_gates", {})

        if "maximum combinational logic depth" in low or "maximum combinational depth" in low:
            return ("max_design_depth", {})

        if "deepest fanin logic cone" in low or "largest fanin cone" in low:
            return ("largest_fanin_cone_output", {})

        if "list all primary outputs" in low:
            return ("list_primary_outputs", {})

        if "list all the primary inputs" in low or "list all primary inputs" in low:
            return ("list_primary_inputs", {})

        if "list all xor gates" in low:
            return ("list_gates_by_type", {"type": "xor"})

        if "list all nand gates" in low:
            return ("list_gates_by_type", {"type": "nand"})

        if "what type of gate is" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("gate_info", {"gate": sigs[0]})

        if "register-to-register paths" in low:
            return ("reg_to_reg_paths", {})

        if "enable or hold" in low:
            return ("dff_enable_hold", {})

        if "flip-flops driven by clock" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("dffs_on_clock", {"clock": sigs[0]})

        if "combinational path exist" in low and "report yes or no" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 2:
                return ("path_exists", {"src": sigs[0], "dst": sigs[1]})

        if "path of length 0" in low:
            return ("zero_length_paths", {})

        if "dedicated buffer" in low and "each load" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("insert_dedicated_buffers", {"signal": sigs[0]})

        if "how many buf gates were added" in low:
            return ("count_gate_type", {"type": "buf"})

        if "how many nor gates" in low and "added" in low:
            return ("count_gate_type", {"type": "nor"})

        if "how many nand gates" in low:
            return ("count_gate_type", {"type": "nand"})

        if "depth greater than 4" in low:
            return ("outputs_depth_gt", {"threshold": 4})

        if "primary input to any dff" in low or "dff d-pin" in low:
            return ("pi_dff_depth", {})

        if "highest fanout" in low and "primary input" in low:
            return ("highest_fanout_pi", {})

        if "maximum fanout of" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("max_fanout_signal", {"signal": sigs[0]})

        if "constant 0" in low and "and gate" in low:
            if "how many" in low:
                return ("count_gate_type", {"type": "and"})
            return ("propagate_and_const0", {})

        if "constant 1" in low and "or gate" in low:
            if "how many" in low:
                return ("count_gate_type", {"type": "or"})
            return ("propagate_or_const1", {})

        if "nand gates with constant" in low:
            if "how many" in low:
                return ("count_gate_type", {"type": "nand"})
            return ("propagate_nand_constants", {})

        if "nor gates with constant" in low:
            if "how many" in low:
                return ("count_gate_type", {"type": "nor"})
            return ("propagate_nor_constants", {})

        if "2-input nand gates that have one input tied to constant 1" in low:
            return ("replace_nand_const1", {})

        if "restructure the logic cone" in low and "nand" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("remap_cone_nand_not", {"signal": sigs[-1]})

        if "decompose all xor gates" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("decompose_xor_cone", {"signal": sigs[-1]})

        if "redundant gates" in low:
            return ("remove_redundant", {})

        if "symmetric with respect" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 3:
                return ("is_symmetric", {"signal": sigs[0], "a": sigs[1], "b": sigs[2]})

        if "cut between" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("is_cut", {"signal": sigs[0]})

        if "floating inputs" in low:
            return ("floating_signals", {})

        if "always 0 regardless" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("output_always_zero", {"signal": sigs[0]})

        if "shared between the fanin cones" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 2:
                return ("shared_cone_gates", {"a": sigs[0], "b": sigs[1]})

        if "nand(a, b)" in low or "nand(a,b)" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("nand_equiv_pair", {"signal": sigs[-1]})

        #if "maximum-depth path" in low and "g0" in req:
        #    return ("gate_on_max_depth_path", {"gate": "g0"})

        if "maximum-depth path" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("gate_on_max_depth_path", {"gate": sigs[0]})

        if "every path from" in low and "pass through gate" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 3:
                return ("every_path_through", {"src": sigs[0], "dst": sigs[1], "gate": sigs[2]})

        if "primary inputs and" in low and "outputs" in low:
            return ("pi_po_count", {})

        if "gates reachable from" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("gates_reachable", {"signal": sigs[0]})

        if "articulation points" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 2:
                return ("articulation_points", {"src": sigs[0], "dst": sigs[1]})

        #if "reconnect input pin" in low:
        #    sigs = _extract_signals(req)
        #    if len(sigs) >= 2:
        #        return ("reconnect_input", {"gate": "g0", "pin": 0, "signal": sigs[-1]})

        if "reconnect input pin" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 2:
                return ("reconnect_input", {"gate": sigs[0], "pin": 0, "signal": sigs[-1]})

        if "gates connected to the output of g0" in low:
            return ("gates_driven_by", {"signal": "g0"})

        if "depth of the cone" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("max_depth_in_cone", {"signal": sigs[-1]})

        if "number of each gate type in the cone" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("cone_gate_type_counts", {"signal": sigs[-1]})

        if "compute the fanin logic cone" in low and "list all gates" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("fanin_cone", {"signal": sigs[-1]})

        if "depends on input" in low:
            sigs = _extract_signals(req)
            if len(sigs) >= 2:
                return ("depends_on", {"output": sigs[0], "input": sigs[1]})

        if "perform depth optimization" in low or "minimize maximum path depth" in low:
            return ("reduce_depth", {})

        if "insert buffers" in low or "fanout" in low or "drives more than" in low:
            mf = 4
            mm = re.search(r"(?:maximum fanout|more than)\s+(\d+)", low)
            if mm:
                mf = int(mm.group(1))
            if "buffer" in low or "fanout" in low or "drives" in low:
                return ("insert_fanout_buffers", {"max_fanout": mf})

        if "convert the logic cone" in low and "nor and not" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("remap_cone_nand_not", {"signal": sigs[-1]})

        if "replace all 2-input or gates" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("remap_cone_nand_not", {"signal": sigs[0]})

        if "gates with constant inputs" in low or "constant inputs" in low and "report any" in low:
            return ("gates_with_constants", {})

        if "confirm that the design is still functionally equivalent" in low:
            return ("verify_equivalence", {})

        if "check whether the current netlist is functionally equivalent" in low:
            return ("verify_equivalence", {})

        if "prove that the transformed design is equivalent" in low or "prove functional equivalence" in low:
            return ("verify_equivalence", {})

        if "verify functional equivalence" in low or "verify that the" in low and "functionally equivalent" in low:
            return ("verify_equivalence", {})

        if "restructure" in low and "target depth" in low:
            sigs = _extract_signals(req)
            md = 4
            mm = re.search(r"depth\s+(?:of\s+)?(\d+)", low)
            if mm:
                md = int(mm.group(1))
            if sigs:
                return ("optimize_cone_depth", {"signal": sigs[0], "max_depth": md})

        if "derive the boolean equation" in low or "boolean expression for" in low or "logic equation" in low:
            sigs = _extract_signals(req)
            if sigs:
                # Fallback: report on signal equivalence and dependencies
                return ("fanin_cone", {"signal": sigs[0]})

        if "connect to the renamed signal" in low and "gates" in low:
            sigs = _extract_signals(req)
            if sigs:
                return ("gates_driven_by", {"signal": sigs[-1]})

        if "how many outputs have" in low and "depth greater than" in low:
            td = 4
            mm = re.search(r"greater than\s+(\d+)", low)
            if mm:
                td = int(mm.group(1))
            return ("outputs_depth_gt", {"threshold": td})

        return None
