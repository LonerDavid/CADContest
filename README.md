# cadcontest — ICCAD 2026 Problem A

LLM-Assisted Netlist Exploration and Transformation system.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # add API key (gitignored)
chmod +x cada1089_alpha
```

ABC (Berkeley Logic Synthesis) is auto-installed on first run if not present.

## Run

```bash
# Single test
./cada1089_alpha -config config.yaml < testcase/test01/prompt.txt

# All 40 tests
./scripts/run_all_tests.sh
```

## Architecture

```
stdin → RequestHandler (rules + LLM)
           → EDASession → EDAEngine
                → CircuitGraph / C++ eda_core (hot paths)
                → DesignVerifier (equivalence, rollback on failure)
        → ResponseWriter → stdout + output/testNN/testNN.log
```

Every transform snapshots the netlist, applies the change, then verifies functional equivalence — rolling back on failure.

## Output

```
output/testNN/
  testNN.log       # agent responses
  testNN_out.v     # written netlist
```
