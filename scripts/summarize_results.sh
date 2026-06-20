#!/usr/bin/env bash
# Summarize output/testNN runs into batch_status.csv
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${ROOT}/output"
CSV="${OUT_DIR}/batch_status.csv"

printf "test,log_responses,prompt_lines,has_out_v,status\n" > "$CSV"

for i in $(seq -w 1 40); do
  t="test$i"
  prompt="${ROOT}/testcase/${t}/prompt.txt"
  case_dir="${OUT_DIR}/${t}"
  pl=0
  [[ -f "$prompt" ]] && pl=$(grep -c '.' "$prompt" || echo 0)

  log="${case_dir}/stdout.log"
  [[ -f "$log" ]] || log="${case_dir}/${t}.log"

  rc=0
  if [[ -f "$log" ]]; then
    resp=$(grep -c '^#RESPONSE ' "$log" 2>/dev/null || echo 0)
  else
    resp=0
    rc=1
  fi

  out_v="N"
  if ls "${case_dir}/${t}"_out.v "${case_dir}"/*_out.v 2>/dev/null | grep -q .; then
    out_v="Y"
  fi

  status="OK"
  if [[ ! -f "$prompt" ]]; then
    status="MISSING"
  elif [[ ! -f "$log" ]]; then
    status="MISSING"
  elif grep -qE 'Error executing|Error:|Transform rejected|Traceback|LLM processing failed|Could not interpret' "$log" 2>/dev/null; then
    status="ERR"
  elif [[ "$resp" -lt "$pl" ]]; then
    status="PARTIAL"
  elif [[ "$out_v" == "N" ]] && grep -qi 'write.*out\.v' "$prompt" 2>/dev/null; then
    status="PARTIAL"
  fi

  printf "%s,%s,%s,%s,%s\n" "$t" "$resp" "$pl" "$out_v" "$status" >> "$CSV"
done

column -t -s, "$CSV" 2>/dev/null || cat "$CSV"
