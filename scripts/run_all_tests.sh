#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CONFIG="${1:-config.yaml}"
BIN="./cada1089_alpha"
OUT_DIR="${ROOT}/output"
mkdir -p "$OUT_DIR"

# Fresh run: remove prior logs and generated netlists
rm -rf "${OUT_DIR}"/test[0-9]* "${OUT_DIR}"/test[0-9][0-9]*
touch "${OUT_DIR}/.gitkeep"

passed=0
failed=0
errors=0

printf "%-8s %-8s %-6s %s\n" "TEST" "STATUS" "RESP" "NOTES"
printf "%-8s %-8s %-6s %s\n" "----" "------" "----" "-----"

for i in $(seq -w 1 40); do
  t="test$i"
  prompt="testcase/${t}/prompt.txt"
  case_dir="${OUT_DIR}/${t}"
  mkdir -p "$case_dir"
  outlog="${case_dir}/stdout.log"
  if [[ ! -f "$prompt" ]]; then
    printf "%-8s %-8s %-6s %s\n" "$t" "MISSING" "-" "no prompt.txt"
    failed=$((failed + 1))
    continue
  fi

  start=$(date +%s)
  # 300s per testcase (gtimeout on macOS Homebrew coreutils, else timeout on Linux)
  TIMEOUT_CMD=""
  if command -v gtimeout >/dev/null 2>&1; then
    TIMEOUT_CMD="gtimeout 600"
  elif command -v timeout >/dev/null 2>&1; then
    TIMEOUT_CMD="timeout 600"
  fi
  if [[ -n "$TIMEOUT_CMD" ]]; then
    if $TIMEOUT_CMD "$BIN" -config "$CONFIG" < "$prompt" > "$outlog" 2>&1; then
      rc=0
    else
      rc=$?
    fi
  elif "$BIN" -config "$CONFIG" < "$prompt" > "$outlog" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  end=$(date +%s)
  elapsed=$((end - start))

  agent_log="${case_dir}/${t}.log"
  resp_count=$(grep -c '^#RESPONSE ' "$agent_log" 2>/dev/null || grep -c '^#RESPONSE ' "$outlog" 2>/dev/null || echo 0)
  prompt_lines=$(grep -c '.' "$prompt" || echo 0)
  has_err=0
  if grep -qE 'Error executing|Error:|Transform rejected|Traceback|LLM processing failed|Could not interpret' "$outlog" "$agent_log" 2>/dev/null; then
    has_err=1
  fi

  status="OK"
  notes="${elapsed}s, ${resp_count}/${prompt_lines} responses"
  if [[ $rc -eq 124 ]]; then
    status="TIMEOUT"
    failed=$((failed + 1))
    notes=">300s"
  elif [[ $rc -ne 0 ]]; then
    status="CRASH"
    errors=$((errors + 1))
    notes="exit $rc"
  elif [[ $has_err -eq 1 ]]; then
    status="ERR"
    failed=$((failed + 1))
    notes=$(grep -m1 -E 'Error|Transform rejected|Traceback' "$outlog" | head -c 60)
  elif [[ "$resp_count" -lt "$prompt_lines" ]]; then
    status="PARTIAL"
    failed=$((failed + 1))
    notes="only ${resp_count}/${prompt_lines} responses"
  else
    passed=$((passed + 1))
  fi

  printf "%-8s %-8s %-6s %s\n" "$t" "$status" "$resp_count" "$notes"
done

echo ""
echo "Summary: OK=$passed, ERR/PARTIAL=$failed, CRASH=$errors (total 40)"
echo "Outputs: ${OUT_DIR}/<testNN>/"
echo "  - <testNN>.log     (agent responses)"
echo "  - <testNN>_out.v   (written netlists)"
echo "  - stdout.log       (batch run capture)"
