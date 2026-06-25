# cadcontest — ICCAD 2026 Problem A

**LLM-Assisted Netlist Exploration and Transformation.**

A two-layer system that reads natural-language requests from stdin, maps each
to a single gate-level EDA operation, and executes it on a flat Verilog netlist
with functional-equivalence verification. Common requests are handled by a
deterministic rule engine; unseen phrasings fall back to a cloud LLM
(GPT-4o mini or Claude 4.5 Haiku).

---

## A. Contents of this submission

| Path | Description |
|------|-------------|
| `cada1089_alpha` | Executable launcher (selects a Python ≥3.7 / project `.venv`, runs `python/main.py`). |
| `python/main.py` | Entry point: stdin loop, response tagging, component wiring. |
| `python/eda/` | **EDA back-end**: `parser`, `netlist`, `dag`, `graph` (representation); `api`, `transform`, `verify` (engine + equivalence/rollback); `extras` (extra tools); `writer`; `abc_bridge` (optional ABC integration). |
| `python/agent/` | **Agent front-end**: `handler` (rule router), `llm` (OpenAI/Anthropic client), `tool_spec` (tool schema / system prompt), `usage_log` (token logging). |
| `python/config.py`, `python/response.py`, `python/output_paths.py` | Config loader, response writer, output path helpers. |
| `cpp/eda_core/eda_core.cpp` | C++ (`pybind11`) acceleration for graph hot loops; optional. |
| `setup.py` | Build script for the C++ extension. |
| `config.example.yaml` | Template LLM config (copy to `config.yaml`; gitignored). |
| `requirements.txt` | Python dependencies. |
| `testcase/test01..40/` | Sample testcases (`*.v` netlist + `prompt.txt` requests). |
| `scripts/` | Batch runners and the LLM-fallback evaluation harness. |
| `docs/report.tex` | Project report (IEEE format, LaTeX source). |
| `docs/` | Problem statement, submission guidelines, and `DEPLOY.md`. |
| `output/` | Generated logs and netlists (gitignored). |

---

## B. System dependencies

- **Python ≥ 3.7** (3.12 recommended; the C++ extension requires a Python with
  development headers).
- Python packages in `requirements.txt`: `pyyaml`, `openai`, `anthropic`.
- **Optional (for C++ acceleration):** a C++17 compiler (`g++` ≥ 7) and
  `pybind11`. Without it the system runs in pure Python with identical results.
- **Optional (logic synthesis):** Berkeley **ABC** is auto-installed on first
  use if not found; it is not on the default execution path.

---

## C. Setup and compilation

```bash
# 1. Create an environment and install dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Provide an LLM config (gitignored; the evaluator supplies its own)
cp config.example.yaml config.yaml      # then edit api_key

# 3. (Optional) Build the C++ acceleration extension
pip install pybind11 setuptools wheel
python setup.py build_ext --inplace     # produces eda_core*.so

# 4. Make the launcher executable
chmod +x cada1089_alpha
```

The launcher prefers a project-local `.venv`; otherwise it selects the newest
available Python ≥ 3.7.

### Configuring `config.yaml`

`config.yaml` selects the cloud LLM provider used when a request does not match
the deterministic rule engine. Start from the checked-in template:

```bash
cp config.example.yaml config.yaml
```

For OpenAI, keep `provider: "openai"` and set `openai.api_key`:

```yaml
provider: "openai"

openai:
  api_key: "YOUR_OPENAI_API_KEY"
  model: "gpt-4o-mini"

anthropic:
  api_key: "YOUR_ANTHROPIC_API_KEY"
  model: "claude-haiku-4-5"

generation:
  temperature: 0.2
  max_output_tokens: 4096
```

For Anthropic, change the first line to `provider: "anthropic"` and set
`anthropic.api_key`. The inactive provider block may remain in the file. Quote
API keys if they contain special characters. `config.yaml` is gitignored and
must not be committed; for course evaluation, the evaluator can provide its own
config file and pass it with `./cada1089_alpha -config <path>`.

---

## D. Running

The executable follows the contest convention `./cada1089_alpha -config <config>`
and reads requests from stdin, one per line.

```bash
# Single testcase
./cada1089_alpha -config config.yaml < testcase/test01/prompt.txt

# All 40 sample testcases
./scripts/run_all_tests.sh config.yaml
```

Outputs are written under `output/<case>/`:

```
output/testNN/
  testNN.log       # agent responses, tagged #RESPONSE <id> ... #END <id>
  testNN_out.v     # written netlist
```

---

## E. Architecture (overview)

```
stdin → RequestHandler
           ├─ rule match (deterministic) ─┐
           └─ else LLM plan (JSON) ───────┤→ EDASession → EDAEngine
                                               ├─ Netlist (source of truth)
                                               ├─ CircuitGraph / C++ eda_core
                                               └─ DesignVerifier (equivalence)
        → ResponseWriter → stdout + output/testNN/testNN.log
```

Every transform snapshots the netlist, applies the edit, refreshes the derived
graph, and verifies functional equivalence plus any structural constraint —
**rolling back automatically on any violation**.

See `docs/report.tex` for the full design and evaluation, and `docs/DEPLOY.md`
for contest-VM deployment.

---

## F. Reproducing the evaluation

```bash
# Coverage on all sample testcases (responses + output netlist per case)
./scripts/run_all_tests.sh config.yaml
./scripts/summarize_results.sh

# Forced-LLM ablation (every request bypasses the rule engine; 01-40 = all cases)
python scripts/llm_fallback_eval.py 01-40
```

On the 40 sample testcases the system completes every request and writes a valid
output netlist for each case; the forced-LLM path agrees with the rule engine on
89% of requests.

---

## Notes

- `config.yaml` is **gitignored**; never commit API keys. The evaluation
  environment provides its own LLM configuration.
- AI-assistance and per-author contributions are disclosed in `docs/report.tex`.
