"""Combinational circuit graph and analysis."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .netlist import Gate, GateKind, Netlist, Signal  # noqa: F401


CONST0 = "1'b0"
CONST1 = "1'b1"
CONSTANTS = {CONST0, CONST1}


def is_constant(sig_key: str) -> bool:
    return sig_key in CONSTANTS


@dataclass
class CircuitGraph:
    nl: Netlist
    driver: Dict[str, str] = field(default_factory=dict)  # signal -> gate name or "PI"
    loads: Dict[str, List[Tuple[str, str]]] = field(default_factory=dict)  # signal -> [(gate, pin_role)]
    gate_outputs: Dict[str, str] = field(default_factory=dict)
    dff_q_signals: Set[str] = field(default_factory=set)
    dff_d_signals: Set[str] = field(default_factory=set)

    @classmethod
    def from_netlist(cls, nl: Netlist) -> "CircuitGraph":
        g = cls(nl=nl)
        for pi in nl.pi_signals():
            g.driver[pi] = "PI"
        for gate in nl.gates.values():
            out = gate.output.key()
            g.driver[out] = gate.name
            g.gate_outputs[gate.name] = out
            if gate.kind == GateKind.DFF:
                g.dff_q_signals.add(out)
                d_key = gate.dff_ports.get("D", gate.inputs[0]).key()
                g.dff_d_signals.add(d_key)
                g._add_load(d_key, gate.name, "D")
                for pname, sig in gate.dff_ports.items():
                    if pname in ("RN", "SN", "CK"):
                        g._add_load(sig.key(), gate.name, pname)
            else:
                for inp in gate.inputs:
                    g._add_load(inp.key(), gate.name, "in")
        # DFF Q outputs behave like additional PIs for combinational analysis
        for q in g.dff_q_signals:
            g.driver[q] = f"DFF:{q}"
        return g

    def _add_load(self, sig: str, gate: str, role: str) -> None:
        self.loads.setdefault(sig, []).append((gate, role))

    def gate(self, name: str) -> Gate:
        return self.nl.gates[name]

    def fanout_count(self, sig: str) -> int:
        return len(self.loads.get(sig, []))

    def direct_fanout_gates(self, sig: str) -> List[str]:
        return [g for g, _ in self.loads.get(sig, [])]

    def resolve_signal(self, name: str) -> str:
        if "[" in name:
            return name
        # scalar or whole bus reference - return as-is
        return name

    def driver_gate(self, sig: str) -> Optional[str]:
        d = self.driver.get(sig)
        if d in (None, "PI") or (d and d.startswith("DFF:")):
            return None
        return d

    def is_pi(self, sig: str) -> bool:
        return sig in self.nl.pi_signals() or sig in self.dff_q_signals

    def is_po(self, sig: str) -> bool:
        return sig in self.nl.po_signals() or sig in self.dff_d_signals

    def combinational_successors(self, node: str) -> List[str]:
        """Return signals/gates reachable forward through combinational logic."""
        result: List[str] = []
        for gate_name, _ in self.loads.get(node, []):
            g = self.gate(gate_name)
            if g.kind == GateKind.DFF:
                result.append(g.output.key())
            else:
                result.append(g.output.key())
        return result

    def combinational_predecessors(self, sig: str) -> List[str]:
        d = self.driver.get(sig)
        if d is None or d == "PI" or d.startswith("DFF:"):
            if sig in self.nl.pi_signals():
                return []
            return []
        g = self.gate(d)
        if g.kind == GateKind.DFF:
            return [g.dff_ports.get("D", g.inputs[0]).key()]
        return [i.key() for i in g.inputs]

    def fanin_cone_gates(self, target: str) -> Set[str]:
        seen_gates: Set[str] = set()
        q = deque([target])
        visited: Set[str] = set()
        while q:
            sig = q.popleft()
            if sig in visited:
                continue
            visited.add(sig)
            drv = self.driver.get(sig)
            if drv and drv not in ("PI",) and not str(drv).startswith("DFF:"):
                seen_gates.add(drv)
                g = self.gate(drv)
                if g.kind == GateKind.DFF:
                    q.append(g.dff_ports.get("D", g.inputs[0]).key())
                else:
                    for inp in g.inputs:
                        q.append(inp.key())
            elif sig in self.dff_q_signals:
                continue
            else:
                for pred in self.combinational_predecessors(sig):
                    q.append(pred)
        return seen_gates

    def fanin_cone_signals(self, target: str) -> Set[str]:
        signals: Set[str] = set()
        q = deque([target])
        while q:
            sig = q.popleft()
            if sig in signals:
                continue
            signals.add(sig)
            drv = self.driver.get(sig)
            if drv and drv not in ("PI",) and not str(drv).startswith("DFF:"):
                g = self.gate(drv)
                if g.kind == GateKind.DFF:
                    q.append(g.dff_ports.get("D", g.inputs[0]).key())
                else:
                    for inp in g.inputs:
                        q.append(inp.key())
        return signals

    def fanout_cone_gates(self, source: str) -> Set[str]:
        seen: Set[str] = set()
        q = deque([source])
        visited: Set[str] = set()
        while q:
            sig = q.popleft()
            if sig in visited:
                continue
            visited.add(sig)
            for gate_name, _ in self.loads.get(sig, []):
                seen.add(gate_name)
                g = self.gate(gate_name)
                q.append(g.output.key())
        return seen

    def _gate_depth_label(self, gate: Gate) -> int:
        if gate.kind == GateKind.DFF:
            return 0
        return 1

    def max_combinational_depth(self, src: str, dst: str) -> int:
        """Longest path through gates from src to dst."""
        best = -1

        def dfs(cur: str, depth: int, visited: Set[str]) -> None:
            nonlocal best
            if cur == dst:
                best = max(best, depth)
                return
            if cur in visited:
                return
            visited.add(cur)
            for gate_name, _ in self.loads.get(cur, []):
                g = self.gate(gate_name)
                if g.kind == GateKind.DFF:
                    if g.output.key() == dst:
                        best = max(best, depth)
                    continue
                dfs(g.output.key(), depth + 1, set(visited))
            visited.remove(cur)

        dfs(src, 0, set())
        return best

    def all_combinational_paths(
        self,
        src: str,
        dst: str,
        max_paths: int = 50,
        max_steps: int = 50_000,
    ) -> Tuple[List[List[str]], bool]:
        """
        Enumerate combinational paths (gate names).
        Returns (paths, truncated) where truncated=True if search hit limits.
        """
        paths: List[List[str]] = []
        steps = 0
        truncated = False

        def dfs(cur: str, visited: Set[str], path: List[str]) -> None:
            nonlocal steps, truncated
            if truncated:
                return
            steps += 1
            if steps > max_steps or len(paths) >= max_paths:
                truncated = True
                return
            if cur == dst:
                paths.append(list(path))
                return
            if cur in visited:
                return
            visited.add(cur)
            for gate_name, _ in self.loads.get(cur, []):
                g = self.gate(gate_name)
                if g.kind == GateKind.DFF:
                    if g.output.key() == dst:
                        paths.append(list(path))
                    continue
                path.append(gate_name)
                dfs(g.output.key(), visited, path)
                path.pop()
            visited.remove(cur)

        dfs(src, set(), [])
        return paths, truncated

    def has_combinational_path(self, src: str, dst: str) -> bool:
        """BFS reachability (fast; use instead of path enumeration for existence)."""
        q = deque([src])
        visited: Set[str] = set()
        while q:
            cur = q.popleft()
            if cur == dst:
                return True
            if cur in visited:
                continue
            visited.add(cur)
            for gate_name, _ in self.loads.get(cur, []):
                g = self.gate(gate_name)
                if g.kind == GateKind.DFF:
                    if g.output.key() == dst:
                        return True
                    continue
                q.append(g.output.key())
        return False

    def path_exists_avoiding(self, src: str, dst: str, avoid: Set[str]) -> bool:
        q = deque([src])
        visited: Set[str] = set()
        while q:
            cur = q.popleft()
            if cur in avoid:
                continue
            if cur == dst:
                return True
            if cur in visited:
                continue
            visited.add(cur)
            for gate_name, _ in self.loads.get(cur, []):
                g = self.gate(gate_name)
                if g.name in avoid or g.output.key() in avoid:
                    continue
                if g.kind == GateKind.DFF:
                    if g.output.key() == dst and g.output.key() not in avoid:
                        return True
                    continue
                q.append(g.output.key())
        return False

    def max_depth_in_cone(self, target: str) -> int:
        """Max logic depth from any PI to target."""
        best = 0
        pis = self.nl.pi_signals() | self.dff_q_signals

        def upstream_depth(sig: str, memo: Dict[str, int]) -> int:
            if sig in memo:
                return memo[sig]
            if sig in pis or is_constant(sig):
                memo[sig] = 0
                return 0
            drv = self.driver.get(sig)
            if not drv or drv == "PI" or str(drv).startswith("DFF:"):
                memo[sig] = 0
                return 0
            g = self.gate(drv)
            if g.kind == GateKind.DFF:
                d = g.dff_ports.get("D", g.inputs[0]).key()
                memo[sig] = upstream_depth(d, memo)
                return memo[sig]
            pred_depths = [upstream_depth(i.key(), memo) for i in g.inputs]
            memo[sig] = max(pred_depths, default=0) + 1
            return memo[sig]

        memo: Dict[str, int] = {}
        return upstream_depth(target, memo)

    def evaluate_signal(self, sig: str, values: Dict[str, int]) -> int:
        if sig == CONST0:
            return 0
        if sig == CONST1:
            return 1
        if sig in values:
            return values[sig]
        drv = self.driver.get(sig)
        if drv is None or drv == "PI" or str(drv).startswith("DFF:"):
            return values.get(sig, 0)
        g = self.gate(drv)
        if g.kind == GateKind.DFF:
            return values.get(sig, 0)
        ins = [self.evaluate_signal(i.key(), values) for i in g.inputs]
        k = g.kind
        if k == GateKind.AND:
            return ins[0] & ins[1]
        if k == GateKind.OR:
            return ins[0] | ins[1]
        if k == GateKind.NAND:
            return 1 - (ins[0] & ins[1])
        if k == GateKind.NOR:
            return 1 - (ins[0] | ins[1])
        if k == GateKind.NOT:
            return 1 - ins[0]
        if k == GateKind.BUF:
            return ins[0]
        if k == GateKind.XOR:
            return ins[0] ^ ins[1]
        if k == GateKind.XNOR:
            return 1 - (ins[0] ^ ins[1])
        raise ValueError(f"Unknown gate {k}")

    def supporting_pis(self, sig: str) -> List[str]:
        result: Set[str] = set()

        def dfs(s: str) -> None:
            if s in result:
                return
            if s in self.nl.pi_signals() or s in self.dff_q_signals:
                result.add(s)
                return
            if is_constant(s):
                return
            drv = self.driver.get(s)
            if not drv or drv == "PI" or str(drv).startswith("DFF:"):
                if s in self.nl.pi_signals():
                    result.add(s)
                return
            g = self.gate(drv)
            if g.kind == GateKind.DFF:
                dfs(g.dff_ports.get("D", g.inputs[0]).key())
            else:
                for inp in g.inputs:
                    dfs(inp.key())

        dfs(sig)
        return sorted(result)

    def functionally_equivalent(self, a: str, b: str, max_inputs: int = 18) -> bool:
        pis = sorted(set(self.supporting_pis(a)) | set(self.supporting_pis(b)))
        if len(pis) > max_inputs:
            # fallback: compare structural simulation on sample
            import random

            for _ in range(512):
                vals = {pi: random.randint(0, 1) for pi in pis}
                if self.evaluate_signal(a, vals) != self.evaluate_signal(b, vals):
                    return False
            return True
        n = len(pis)
        for mask in range(1 << n):
            vals = {pis[i]: (mask >> i) & 1 for i in range(n)}
            if self.evaluate_signal(a, vals) != self.evaluate_signal(b, vals):
                return False
        return True

    def gate_type_counts_in_cone(self, target: str) -> Dict[str, int]:
        counts = {t.upper(): 0 for t in ("and", "or", "nand", "nor", "not", "buf", "xor", "xnor", "dff")}
        for gname in self.fanin_cone_gates(target):
            g = self.gate(gname)
            counts[g.kind.value.upper()] += 1
        return counts

    def immediate_successors(self, gate_name: str) -> List[str]:
        g = self.gate(gate_name)
        out = g.output.key()
        return [self.gate(gn).name for gn, _ in self.loads.get(out, [])]

    def gates_driven_by(self, sig: str) -> List[str]:
        return [gn for gn, _ in self.loads.get(sig, [])]

    def max_design_depth(self) -> int:
        depths = []
        for po in self.nl.po_signals():
            depths.append(self.max_depth_in_cone(po))
        for d in self.dff_d_signals:
            depths.append(self.max_depth_in_cone(d))
        return max(depths) if depths else 0

    def register_to_register_paths(self, max_paths: int = 1000) -> List[List[str]]:
        paths: List[List[str]] = []
        for q in sorted(self.dff_q_signals):
            for d in sorted(self.dff_d_signals):
                p_list, _ = self.all_combinational_paths(q, d, max_paths=max_paths)
                for p in p_list:
                    if p:
                        paths.append([q] + p + [d])
                    if len(paths) >= max_paths:
                        return paths
        return paths

    def pi_to_dff_d_depth(self) -> int:
        best = 0
        for d in self.dff_d_signals:
            best = max(best, self.max_depth_in_cone(d))
        return best

    def outputs_depth_gt(self, threshold: int) -> List[str]:
        result = []
        for po in sorted(self.nl.po_signals()):
            if self.max_depth_in_cone(po) > threshold:
                result.append(po)
        return result

    def deepest_output(self) -> str:
        best_sig = ""
        best_depth = -1
        for po in self.nl.po_signals():
            d = self.max_depth_in_cone(po)
            if d > best_depth:
                best_depth = d
                best_sig = po
        return best_sig

    def largest_fanin_cone_output(self) -> Tuple[str, int]:
        best_sig = ""
        best_count = -1
        for po in self.nl.po_signals():
            c = len(self.fanin_cone_gates(po))
            if c > best_count:
                best_count = c
                best_sig = po
        return best_sig, best_count

    def depends_on(self, output: str, inp: str) -> bool:
        return inp in self.fanin_cone_signals(output)

    def is_cut_node(self, sig: str) -> bool:
        """Check if removing sig disconnects some PI-PO pair."""
        if sig in self.nl.pi_signals() or sig in self.nl.po_signals():
            return False
        for pi in self.nl.pi_signals():
            for po in self.nl.po_signals():
                if self.path_exists_avoiding(pi, po, set()) and not self.path_exists_avoiding(
                    pi, po, {sig}
                ):
                    return True
        return False

    def zero_length_paths(self) -> List[Tuple[str, str]]:
        result = []
        for pi in self.nl.pi_signals():
            for po in self.nl.po_signals():
                if pi == po:
                    result.append((pi, po))
        return result

    def articulation_points(self, src: str, dst: str) -> List[str]:
        """Nodes that lie on all paths from src to dst (combinational)."""
        all_paths, _ = self.all_combinational_paths(src, dst, max_paths=500)
        if not all_paths:
            return []
        common = set(all_paths[0])
        for p in all_paths[1:]:
            common &= set(p)
        return sorted(common)

    def on_max_depth_path(self, gate_name: str) -> bool:
        max_d = self.max_design_depth()
        for po in self.nl.po_signals():
            if self.max_depth_in_cone(po) < max_d:
                continue
            for pi in self.nl.pi_signals():
                paths, _ = self.all_combinational_paths(pi, po, max_paths=500)
                for path in paths:
                    if len(path) == max_d and gate_name in path:
                        return True
        return False

    def every_path_through(self, src: str, dst: str, gate: str) -> bool:
        paths, truncated = self.all_combinational_paths(src, dst, max_paths=500)
        if not paths:
            return False
        if truncated:
            return False
        return all(gate in p for p in paths)

    def shared_cone_gates(self, a: str, b: str) -> Set[str]:
        return self.fanin_cone_gates(a) & self.fanin_cone_gates(b)

    def output_always_zero(self, po: str) -> bool:
        pis = self.supporting_pis(po)
        if len(pis) > 18:
            return False
        for mask in range(1 << len(pis)):
            vals = {pis[i]: (mask >> i) & 1 for i in range(len(pis))}
            if self.evaluate_signal(po, vals) != 0:
                return False
        return True

    def highest_fanout_pi(self) -> Tuple[str, int]:
        best = ("", 0)
        for p in self.nl.primary_inputs():
            if p.width == 1:
                fo = self.fanout_count(p.name)
                if fo > best[1]:
                    best = (p.name, fo)
            else:
                for b in p.bits():
                    key = f"{p.name}[{b}]"
                    fo = self.fanout_count(key)
                    if fo > best[1]:
                        best = (key, fo)
        return best

    def gates_with_constant_inputs(self) -> List[Tuple[str, str, str]]:
        result = []
        for g in self.nl.gates.values():
            if g.kind == GateKind.DFF:
                continue
            for inp in g.inputs:
                if is_constant(inp.key()):
                    result.append((g.name, g.kind.value, inp.key()))
        return result

    def find_nand_const1(self) -> List[str]:
        found = []
        for g in self.nl.gates.values():
            if g.kind == GateKind.NAND:
                for inp in g.inputs:
                    if inp.key() == CONST1:
                        found.append(g.name)
        return found

    def find_and_const0(self) -> List[str]:
        found = []
        for g in self.nl.gates.values():
            if g.kind == GateKind.AND:
                for inp in g.inputs:
                    if inp.key() == CONST0:
                        found.append(g.name)
        return found

    def find_or_const1(self) -> List[str]:
        found = []
        for g in self.nl.gates.values():
            if g.kind == GateKind.OR:
                for inp in g.inputs:
                    if inp.key() == CONST1:
                        found.append(g.name)
        return found

    def dffs_on_clock(self, clk: str) -> List[str]:
        result = []
        for g in self.nl.gates.values():
            if g.kind == GateKind.DFF:
                ck = g.dff_ports.get("CK", Signal("clk")).key()
                if ck == clk:
                    result.append(g.name)
        return result

    def list_gates_by_type(self, kind: GateKind) -> List[Gate]:
        return [g for g in self.nl.gates.values() if g.kind == kind]

    def gate_info(self, name: str) -> Gate:
        return self.nl.gates[name]

    def dff_enable_hold_count(self) -> int:
        """Heuristic: DFFs whose D input cone contains mux-like AND/OR patterns."""
        count = 0
        for g in self.nl.gates.values():
            if g.kind != GateKind.DFF:
                continue
            d = g.dff_ports.get("D", g.inputs[0]).key()
            cone = self.fanin_cone_gates(d)
            has_and = any(self.gate(cn).kind == GateKind.AND for cn in cone)
            has_or = any(self.gate(cn).kind == GateKind.OR for cn in cone)
            if has_and and has_or:
                count += 1
        return count

    def is_symmetric(self, sig: str, a: str, b: str) -> bool:
        """Check if function at sig is symmetric in inputs a and b."""
        pis = self.supporting_pis(sig)
        if a not in pis or b not in pis:
            return False
        if len(pis) > 16:
            return False
        n = len(pis)
        ia, ib = pis.index(a), pis.index(b)
        for mask in range(1 << n):
            vals = {pis[i]: (mask >> i) & 1 for i in range(n)}
            v1 = self.evaluate_signal(sig, vals)
            vals[a], vals[b] = vals[b], vals[a]
            v2 = self.evaluate_signal(sig, vals)
            if v1 != v2:
                return False
        return True

    def nand_equivalent_pair_for(self, target: str) -> Optional[Tuple[str, str]]:
        """Find existing signals a,b where NAND(a,b) equiv target."""
        sigs = list(self.fanin_cone_signals(target))
        candidates = [s for s in sigs if not is_constant(s)]
        for i, a in enumerate(candidates):
            for b in candidates[i + 1 :]:
                # compute NAND(a,b) virtually
                pis = sorted(set(self.supporting_pis(a)) | set(self.supporting_pis(b)) | set(self.supporting_pis(target)))
                if len(pis) > 16:
                    continue
                ok = True
                for mask in range(1 << len(pis)):
                    vals = {pis[j]: (mask >> j) & 1 for j in range(len(pis))}
                    na = self.evaluate_signal(a, vals)
                    nb = self.evaluate_signal(b, vals)
                    nt = self.evaluate_signal(target, vals)
                    if (1 - (na & nb)) != nt:
                        ok = False
                        break
                if ok:
                    return (a, b)
        return None

    def floating_signals(self) -> List[str]:
        driven = set(self.driver.keys())
        used: Set[str] = set()
        for g in self.nl.gates.values():
            if g.kind == GateKind.DFF:
                for s in g.dff_ports.values():
                    used.add(s.key())
            else:
                used.add(g.output.key())
                for i in g.inputs:
                    used.add(i.key())
        for po in self.nl.po_signals():
            used.add(po)
        return sorted(driven - used - self.nl.pi_signals())
