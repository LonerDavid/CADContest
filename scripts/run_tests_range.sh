#!/usr/bin/env bash
# Run testcases START..END (inclusive), e.g. ./scripts/run_tests_range.sh 12 40
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
START=${1:-1}
END=${2:-40}
CONFIG="${3:-config.yaml}"
export CADCONTEST_NO_LLM=1
BIN="./cada1089_alpha"
OUT_DIR="${ROOT}/output"

for i in $(seq -w "$START" "$END"); do
  t="test$i"
  prompt="testcase/${t}/prompt.txt"
  [[ -f "$prompt" ]] || continue
  case_dir="${OUT_DIR}/${t}"
  mkdir -p "$case_dir"
  echo "=== $t ==="
  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout 600 "$BIN" -config "$CONFIG" < "$prompt" > "${case_dir}/stdout.log" 2>&1 || echo "exit $?"
  else
    "$BIN" -config "$CONFIG" < "$prompt" > "${case_dir}/stdout.log" 2>&1 || echo "exit $?"
  fi
  grep -c '^#RESPONSE ' "${case_dir}/${t}.log" 2>/dev/null || echo "0 responses"
done
