/*
 * eda_core.cpp — pybind11 C++ extension for hot-loop EDA graph operations.
 *
 * Exposed class:  Circuit
 * Key methods:
 *   are_equivalent(a, b)          bit-parallel truth-table (≤20 PIs) or random sim
 *   max_depth(src, dst)           longest combinational path depth
 *   max_depth_in_cone(sig)        max PI→sig depth (memoised DP)
 *   max_design_depth()            max over all POs
 *   path_exists(src, dst, avoid)  BFS reachability with node avoidance
 *   fanin_cone(sig)               gate indices reachable upstream
 *   fanout_cone(sig)              gate indices reachable downstream
 *   supporting_pis(sig)           PI ids in the fanin cone
 *   enumerate_paths(src,dst,max)  DFS path list (gate indices per path)
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <limits>
#include <queue>
#include <random>
#include <stack>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace py = pybind11;

// ── gate kind ints (must match Python GateKind enum order) ─────────────────
static constexpr int K_AND  = 0;
static constexpr int K_OR   = 1;
static constexpr int K_NOT  = 2;
static constexpr int K_NAND = 3;
static constexpr int K_NOR  = 4;
static constexpr int K_XOR  = 5;
static constexpr int K_XNOR = 6;
static constexpr int K_BUF  = 7;
static constexpr int K_DFF  = 8;

// ── sentinel driver values ──────────────────────────────────────────────────
static constexpr int DRV_PI    = -1;
static constexpr int DRV_CONST0 = -2;
static constexpr int DRV_CONST1 = -3;
static constexpr int DRV_NONE  = -4;

// ── gate storage ────────────────────────────────────────────────────────────
struct Gate {
    int8_t kind;
    int output;
    std::vector<int> inputs;
};

// ───────────────────────────────────────────────────────────────────────────
class Circuit {
public:
    int n_signals;
    int const0_id, const1_id;

    std::vector<Gate>              gates;      // indexed by gate_idx
    std::vector<int>               topo;       // gate indices, topological order
    std::vector<int>               driver;     // sig_id → gate_idx / DRV_*
    std::vector<std::vector<int>>  loads;      // sig_id → [gate_idx, ...]
    std::vector<int>               pi_ids;
    std::vector<int>               po_ids;
    std::unordered_set<int>        pi_set;

    // gates_data: list of (kind_int, out_id, [in_ids]) in topological order
    Circuit(int n_sigs,
            const std::vector<std::tuple<int,int,std::vector<int>>>& gates_data,
            const std::vector<int>& pis,
            const std::vector<int>& pos,
            int c0, int c1)
        : n_signals(n_sigs), const0_id(c0), const1_id(c1),
          pi_ids(pis), po_ids(pos)
    {
        driver.assign(n_sigs, DRV_NONE);
        loads.resize(n_sigs);

        // Mark PIs first
        for (int p : pis) if (p >= 0 && p < n_sigs) driver[p] = DRV_PI;
        if (c0 >= 0 && c0 < n_sigs) driver[c0] = DRV_CONST0;
        if (c1 >= 0 && c1 < n_sigs) driver[c1] = DRV_CONST1;
        pi_set.insert(pis.begin(), pis.end());

        // Build gates, driver, loads
        gates.reserve(gates_data.size());
        for (auto& [kind, out, ins] : gates_data) {
            int gi = (int)gates.size();
            gates.push_back({(int8_t)kind, out, ins});
            if (out >= 0 && out < n_sigs && driver[out] == DRV_NONE)
                driver[out] = gi;
            for (int inp : ins)
                if (inp >= 0 && inp < n_sigs)
                    loads[inp].push_back(gi);
        }

        // Compute proper topological order via Kahn's algorithm.
        // (Input file order is not guaranteed to be topological.)
        {
            std::vector<int> fan_in(gates.size(), 0);
            for (int i = 0; i < (int)gates.size(); i++) {
                const Gate& g = gates[i];
                if (g.kind == K_DFF) continue;
                for (int inp : g.inputs)
                    if (inp >= 0 && inp < n_sigs && driver[inp] >= 0)
                        fan_in[i]++;
            }
            std::queue<int> bfs;
            for (int i = 0; i < (int)gates.size(); i++)
                if (fan_in[i] == 0) bfs.push(i);
            topo.reserve(gates.size());
            while (!bfs.empty()) {
                int gi = bfs.front(); bfs.pop();
                topo.push_back(gi);
                int out = gates[gi].output;
                if (out >= 0 && out < n_sigs)
                    for (int ngi : loads[out])
                        if (--fan_in[ngi] == 0) bfs.push(ngi);
            }
            // Append any remaining (e.g. DFFs or combinational cycles)
            if ((int)topo.size() < (int)gates.size()) {
                std::vector<bool> in_topo(gates.size(), false);
                for (int gi : topo) in_topo[gi] = true;
                for (int i = 0; i < (int)gates.size(); i++)
                    if (!in_topo[i]) topo.push_back(i);
            }
        }
    }

    // ── helper: is a signal a PI / constant? ───────────────────────────────
    bool is_primary(int sig) const {
        if (sig < 0 || sig >= n_signals) return true;
        int d = driver[sig];
        return d == DRV_PI || d == DRV_CONST0 || d == DRV_CONST1 || d == DRV_NONE;
    }

    // ── BFS upstream: collect gate indices in fanin cone of sig ────────────
    std::vector<int> fanin_cone(int sig) const {
        std::vector<int> result;
        std::vector<bool> visited_sig(n_signals, false);
        std::queue<int> q;
        q.push(sig);
        while (!q.empty()) {
            int s = q.front(); q.pop();
            if (s < 0 || s >= n_signals || visited_sig[s]) continue;
            visited_sig[s] = true;
            int d = driver[s];
            if (d < 0) continue; // PI / const / none
            result.push_back(d);
            const Gate& g = gates[d];
            if (g.kind == K_DFF) {
                // Do not cross DFF boundary
                continue;
            }
            for (int inp : g.inputs) q.push(inp);
        }
        return result;
    }

    // ── BFS downstream: collect gate indices in fanout cone of sig ─────────
    std::vector<int> fanout_cone(int sig) const {
        std::vector<int> result;
        std::vector<bool> visited_sig(n_signals, false);
        std::queue<int> q;
        q.push(sig);
        while (!q.empty()) {
            int s = q.front(); q.pop();
            if (s < 0 || s >= n_signals || visited_sig[s]) continue;
            visited_sig[s] = true;
            for (int gi : loads[s]) {
                result.push_back(gi);
                const Gate& g = gates[gi];
                q.push(g.output);
            }
        }
        return result;
    }

    // ── Supporting PIs for a signal (BFS upstream, collect PIs) ───────────
    std::vector<int> supporting_pis(int sig) const {
        std::unordered_set<int> result;
        std::vector<bool> visited(n_signals, false);
        std::queue<int> q;
        q.push(sig);
        while (!q.empty()) {
            int s = q.front(); q.pop();
            if (s < 0 || s >= n_signals || visited[s]) continue;
            visited[s] = true;
            int d = driver[s];
            if (d == DRV_PI) { result.insert(s); continue; }
            if (d == DRV_CONST0 || d == DRV_CONST1 || d == DRV_NONE) continue;
            const Gate& g = gates[d];
            if (g.kind == K_DFF) continue; // treat DFF-Q as PI
            for (int inp : g.inputs) q.push(inp);
        }
        return std::vector<int>(result.begin(), result.end());
    }

    // ── Bit-parallel truth-table simulation ────────────────────────────────
    // Returns true if a and b compute the same Boolean function.
    bool are_equivalent(int a, int b) const {
        auto pis_a = supporting_pis(a);
        auto pis_b = supporting_pis(b);

        // Union of PIs
        std::unordered_set<int> pi_union(pis_a.begin(), pis_a.end());
        pi_union.insert(pis_b.begin(), pis_b.end());
        std::vector<int> all_pis(pi_union.begin(), pi_union.end());
        std::sort(all_pis.begin(), all_pis.end());
        int n = (int)all_pis.size();

        if (n > 20) {
            // Random simulation: 2048 rounds × 64 = 131072 patterns
            return random_sim_equivalent(a, b, all_pis, 2048);
        }

        int total_pats = 1 << n;              // 2^n patterns
        int word_count = std::max(1, total_pats / 64);

        // Build PI column vectors
        std::unordered_map<int, std::vector<uint64_t>> sim;
        sim.reserve(n + 4);

        for (int i = 0; i < n; i++) {
            std::vector<uint64_t> col(word_count);
            int block = 1 << i; // half-period in patterns
            if (block >= 64) {
                // Each column word is entirely 0 or entirely 1
                int words_per_block = block / 64;
                for (int w = 0; w < word_count; w++) {
                    int block_idx = w / words_per_block;
                    col[w] = (block_idx % 2 == 1) ? ~0ULL : 0ULL;
                }
            } else {
                // Multiple blocks per word
                uint64_t period = 0ULL;
                // Build one period of 2*block bits
                for (int bit = 0; bit < 64; bit++) {
                    if ((bit / block) % 2 == 1) period |= (1ULL << bit);
                }
                for (int w = 0; w < word_count; w++) col[w] = period;
            }
            sim[all_pis[i]] = std::move(col);
        }
        if (const0_id >= 0) sim[const0_id] = std::vector<uint64_t>(word_count, 0ULL);
        if (const1_id >= 0) sim[const1_id] = std::vector<uint64_t>(word_count, ~0ULL);

        // Evaluate in topological order
        eval_topo_sim(sim, word_count);

        // Compare
        auto it_a = sim.find(a);
        auto it_b = sim.find(b);
        if (it_a == sim.end() || it_b == sim.end()) return true;

        // Mask last word for the exact pattern count
        uint64_t mask = (total_pats % 64 == 0) ? ~0ULL : ((1ULL << (total_pats % 64)) - 1);
        for (int w = 0; w < word_count; w++) {
            uint64_t m = (w == word_count - 1) ? mask : ~0ULL;
            if ((it_a->second[w] & m) != (it_b->second[w] & m)) return false;
        }
        return true;
    }

    // ── Longest path depth: src → dst (backward recursion, O(cone(dst))) ────
    // Works correctly regardless of gate insertion order.
    int max_depth(int src, int dst) const {
        if (src == dst) return 0;
        if (src < 0 || src >= n_signals || dst < 0 || dst >= n_signals) return -1;
        std::unordered_map<int, int> memo;
        return _md_backward(dst, src, memo);
    }

    // ── Max upstream depth (PI → sig), memoised ───────────────────────────
    int max_depth_in_cone(int sig) const {
        std::unordered_map<int, int> memo;
        return upstream_depth(sig, memo);
    }

    int max_design_depth() const {
        std::unordered_map<int, int> memo;
        int best = 0;
        for (int po : po_ids) best = std::max(best, upstream_depth(po, memo));
        return best;
    }

    // ── BFS path existence with node/gate avoidance ───────────────────────
    bool path_exists(int src, int dst, const std::vector<int>& avoid_sigs) const {
        std::unordered_set<int> avoid(avoid_sigs.begin(), avoid_sigs.end());
        std::queue<int> q;
        std::vector<bool> visited(n_signals, false);
        if (avoid.count(src)) return false;
        q.push(src);
        visited[src] = true;
        while (!q.empty()) {
            int s = q.front(); q.pop();
            if (s == dst) return true;
            if (s < 0 || s >= n_signals) continue;
            for (int gi : loads[s]) {
                const Gate& g = gates[gi];
                if (avoid.count(g.output)) continue;
                if (g.kind == K_DFF) {
                    if (g.output == dst) return true;
                    continue;
                }
                int nx = g.output;
                if (nx >= 0 && nx < n_signals && !visited[nx] && !avoid.count(nx)) {
                    visited[nx] = true;
                    q.push(nx);
                }
            }
        }
        return false;
    }

    // ── Enumerate paths (gate name indices per path) ───────────────────────
    std::vector<std::vector<int>> enumerate_paths(int src, int dst, int max_paths) const {
        std::vector<std::vector<int>> results;
        std::vector<int> cur_path;
        std::vector<bool> on_stack(n_signals, false);
        int steps = 0;
        const int MAX_STEPS = 200000;

        std::function<void(int)> dfs = [&](int s) {
            if ((int)results.size() >= max_paths || steps > MAX_STEPS) return;
            if (s == dst) { results.push_back(cur_path); return; }
            if (s < 0 || s >= n_signals || on_stack[s]) return;
            on_stack[s] = true;
            for (int gi : loads[s]) {
                steps++;
                if (steps > MAX_STEPS || (int)results.size() >= max_paths) break;
                const Gate& g = gates[gi];
                if (g.kind == K_DFF) {
                    if (g.output == dst) results.push_back(cur_path);
                    continue;
                }
                cur_path.push_back(gi);
                dfs(g.output);
                cur_path.pop_back();
            }
            on_stack[s] = false;
        };

        dfs(src);
        return results;
    }

private:
    // ── Evaluate gates in topological order (for bit-parallel sim) ─────────
    void eval_topo_sim(std::unordered_map<int, std::vector<uint64_t>>& sim,
                       int wc) const {
        for (int gi : topo) {
            const Gate& g = gates[gi];
            int out = g.output;
            if (out < 0 || out >= n_signals) continue;
            if (sim.count(out)) continue; // PI or already set

            std::vector<uint64_t> res(wc, 0ULL);
            bool missing = false;
            for (int inp : g.inputs) {
                if (!sim.count(inp)) { missing = true; break; }
            }
            if (missing || g.inputs.empty()) { sim[out] = res; continue; }

            switch (g.kind) {
            case K_AND: {
                res = sim[g.inputs[0]];
                for (int j = 1; j < (int)g.inputs.size(); j++) {
                    auto& v = sim[g.inputs[j]];
                    for (int w = 0; w < wc; w++) res[w] &= v[w];
                }
                break;
            }
            case K_OR: {
                res = sim[g.inputs[0]];
                for (int j = 1; j < (int)g.inputs.size(); j++) {
                    auto& v = sim[g.inputs[j]];
                    for (int w = 0; w < wc; w++) res[w] |= v[w];
                }
                break;
            }
            case K_NOT: case K_BUF: {
                auto& v = sim[g.inputs[0]];
                if (g.kind == K_NOT)
                    for (int w = 0; w < wc; w++) res[w] = ~v[w];
                else
                    res = v;
                break;
            }
            case K_NAND: {
                res = sim[g.inputs[0]];
                for (int j = 1; j < (int)g.inputs.size(); j++) {
                    auto& v = sim[g.inputs[j]];
                    for (int w = 0; w < wc; w++) res[w] &= v[w];
                }
                for (int w = 0; w < wc; w++) res[w] = ~res[w];
                break;
            }
            case K_NOR: {
                res = sim[g.inputs[0]];
                for (int j = 1; j < (int)g.inputs.size(); j++) {
                    auto& v = sim[g.inputs[j]];
                    for (int w = 0; w < wc; w++) res[w] |= v[w];
                }
                for (int w = 0; w < wc; w++) res[w] = ~res[w];
                break;
            }
            case K_XOR: {
                res = sim[g.inputs[0]];
                for (int j = 1; j < (int)g.inputs.size(); j++) {
                    auto& v = sim[g.inputs[j]];
                    for (int w = 0; w < wc; w++) res[w] ^= v[w];
                }
                break;
            }
            case K_XNOR: {
                res = sim[g.inputs[0]];
                for (int j = 1; j < (int)g.inputs.size(); j++) {
                    auto& v = sim[g.inputs[j]];
                    for (int w = 0; w < wc; w++) res[w] ^= v[w];
                }
                for (int w = 0; w < wc; w++) res[w] = ~res[w];
                break;
            }
            default: // DFF or unknown — treat output as unknown (leave 0)
                break;
            }
            sim[out] = std::move(res);
        }
    }

    // ── Random simulation equivalence check ───────────────────────────────
    bool random_sim_equivalent(int a, int b, const std::vector<int>& pis,
                               int rounds) const {
        std::mt19937_64 rng(0xdeadbeef1234ULL);
        int wc = 1;

        std::unordered_map<int, std::vector<uint64_t>> sim;
        sim.reserve(pis.size() + 4);
        if (const0_id >= 0) sim[const0_id] = {0ULL};
        if (const1_id >= 0) sim[const1_id] = {~0ULL};

        for (int r = 0; r < rounds; r++) {
            for (int p : pis) sim[p] = {rng()};
            // Reset non-PI, non-const signals each round
            // (keep only PIs and constants in sim, re-evaluate)
            std::unordered_map<int, std::vector<uint64_t>> round_sim;
            for (int p : pis) round_sim[p] = sim[p];
            if (const0_id >= 0) round_sim[const0_id] = {0ULL};
            if (const1_id >= 0) round_sim[const1_id] = {~0ULL};
            eval_topo_sim(round_sim, wc);

            auto ia = round_sim.find(a);
            auto ib = round_sim.find(b);
            if (ia == round_sim.end() || ib == round_sim.end()) continue;
            if (ia->second[0] != ib->second[0]) return false;
        }
        return true;
    }

    // ── Backward max-depth from src to sig (memoised) ────────────────────
    // Returns max gate hops from src to sig (-1 if sig not reachable from src).
    int _md_backward(int sig, int src, std::unordered_map<int,int>& memo) const {
        if (sig == src) return 0;
        if (sig < 0 || sig >= n_signals) return -1;
        auto it = memo.find(sig);
        if (it != memo.end()) return it->second;
        int d = driver[sig];
        if (d < 0) { memo[sig] = -1; return -1; }  // PI/const/none, not src
        const Gate& g = gates[d];
        if (g.kind == K_DFF) { memo[sig] = -1; return -1; }
        int best = -1;
        for (int inp : g.inputs) {
            int dep = _md_backward(inp, src, memo);
            if (dep >= 0) best = std::max(best, dep);
        }
        int result = (best >= 0) ? best + 1 : -1;
        memo[sig] = result;
        return result;
    }

    // ── Recursive upstream depth with memo ───────────────────────────────
    int upstream_depth(int sig, std::unordered_map<int,int>& memo) const {
        if (sig < 0 || sig >= n_signals) return 0;
        auto it = memo.find(sig);
        if (it != memo.end()) return it->second;

        int d = driver[sig];
        if (d == DRV_PI || d == DRV_CONST0 || d == DRV_CONST1 || d == DRV_NONE) {
            memo[sig] = 0; return 0;
        }
        const Gate& g = gates[d];
        if (g.kind == K_DFF) { memo[sig] = 0; return 0; }

        int best = 0;
        for (int inp : g.inputs)
            best = std::max(best, upstream_depth(inp, memo));
        memo[sig] = best + 1;
        return best + 1;
    }
};

// ── pybind11 module ─────────────────────────────────────────────────────────
PYBIND11_MODULE(eda_core, m) {
    m.doc() = "C++ hot-loop EDA graph operations";

    py::class_<Circuit>(m, "Circuit")
        .def(py::init<int,
                      const std::vector<std::tuple<int,int,std::vector<int>>>&,
                      const std::vector<int>&,
                      const std::vector<int>&,
                      int, int>(),
             py::arg("n_signals"),
             py::arg("gates_data"),
             py::arg("pi_ids"),
             py::arg("po_ids"),
             py::arg("const0_id"),
             py::arg("const1_id"))
        .def("are_equivalent",   &Circuit::are_equivalent,
             py::arg("a"), py::arg("b"))
        .def("max_depth",        &Circuit::max_depth,
             py::arg("src"), py::arg("dst"))
        .def("max_depth_in_cone",&Circuit::max_depth_in_cone,
             py::arg("sig"))
        .def("max_design_depth", &Circuit::max_design_depth)
        .def("path_exists",      &Circuit::path_exists,
             py::arg("src"), py::arg("dst"), py::arg("avoid_sigs"))
        .def("fanin_cone",       &Circuit::fanin_cone,  py::arg("sig"))
        .def("fanout_cone",      &Circuit::fanout_cone, py::arg("sig"))
        .def("supporting_pis",   &Circuit::supporting_pis, py::arg("sig"))
        .def("enumerate_paths",  &Circuit::enumerate_paths,
             py::arg("src"), py::arg("dst"), py::arg("max_paths") = 50)
        .def_readonly("n_signals", &Circuit::n_signals)
        .def_readonly("pi_ids",    &Circuit::pi_ids)
        .def_readonly("po_ids",    &Circuit::po_ids);
}
