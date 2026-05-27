# cadcontest — ICCAD 2026 Problem A

LLM-Assisted Netlist Exploration and Transformation system.

## Phased architecture

| Step | Module | Description |
|------|--------|-------------|
| **1** | `python/eda/parser.py`, `dag.py`, `writer.py` | Parse flat gate-level Verilog → `DesignDAG` (netlist + directed graph) → write Verilog |
| **2** | `python/eda/api.py`, `verify.py`, `transform.py` | Analysis API (depth, fanout, paths) + validated transforms with equivalence rollback |
| **3** | `python/config.py`, `python/agent/tool_spec.py`, `llm.py` | `-config` YAML, LLM client, system prompt describing all EDA tools |
| **4** | `python/main.py`, `response.py` | Stdin loop, `#RESPONSE <id>` / `#END <id>`, stdout + `output/<case>.log` |

```
stdin (NL requests)
    → RequestHandler (rules + LLM)
        → EDASession
            → EDAEngine
                → DesignDAG / CircuitGraph
                → DesignVerifier (equivalence, fanout, depth)
    → ResponseWriter → stdout + output/testNN/testNN.log
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # add API key (gitignored)
chmod +x cada1089_alpha
```

## Output layout

```
output/
  test01/
    test01.log          # agent responses (same as stdout tags)
    test01_out.v        # final netlist from write request
  test02/
    ...
```

Override directory: `CADCONTEST_OUTPUT_DIR=/path/to/out ./cada1089_alpha ...`

## Run

```bash
./cada1089_alpha -config config.yaml < testcase/test01/prompt.txt
```

Batch run all 40 testcases:

```bash
./scripts/run_all_tests.sh config.yaml
```

## Correctness guarantees (Step 2)

Every mutating API in `EDAEngine` snapshots the netlist, applies the change, then runs `DesignVerifier`:

- **Functional equivalence** vs. pre-transform state (required by default)
- **Structural constraints** when specified (`max_fanout`, `max_depth`)

Failed verification **rolls back** the netlist and returns an error — avoiding zero-score functional violations.

## Documentation

- `docs/A_20260212.pdf` — contest specification
- `docs/Problem A_QA_0417.pdf` — Q&A
- `testcase/test01` … `test40` — sample benchmarks
