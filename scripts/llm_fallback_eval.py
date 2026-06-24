#!/usr/bin/env python3
"""Evaluate the LLM fallback against the rule engine.

For each selected testcase we run the binary twice on the SAME prompt:
  1. rule mode (normal)            -> treated as the golden output
  2. CADCONTEST_FORCE_LLM=1 mode    -> every line goes through the LLM

Responses are aligned by order and compared. This quantifies how well the LLM
alone reproduces the rule-engine answers (i.e. how robust the system is when a
hidden testcase's phrasing misses the handcrafted rules).

Usage:
  scripts/llm_fallback_eval.py [--config config.yaml] [--bin ./cada1089_alpha]
                               [TESTS ...]

TESTS accepts names or ranges: 01  03  10-12   (default: 01 02 03 04 05)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESP_RE = re.compile(r"^#RESPONSE\s+(\d+)\s*$")
END_RE = re.compile(r"^#END\s+(\d+)\s*$")
ERROR_MARKERS = (
    "LLM processing failed",
    "LLM did not return valid JSON",
    "Invalid JSON from LLM",
    "LLM response missing",
    "Unknown tool:",
    "Could not interpret request",
    "Error executing",
)


def parse_responses(text: str) -> list[str]:
    """Return response bodies in order, keyed implicitly by appearance."""
    bodies: list[str] = []
    cur: list[str] | None = None
    for line in text.splitlines():
        if RESP_RE.match(line):
            cur = []
            continue
        if END_RE.match(line):
            if cur is not None:
                bodies.append("\n".join(cur).strip())
            cur = None
            continue
        if cur is not None:
            cur.append(line)
    return bodies


def run(binary: str, config: str, prompt: str, force_llm: bool) -> list[str]:
    env = dict(os.environ)
    if force_llm:
        env["CADCONTEST_FORCE_LLM"] = "1"
    else:
        env.pop("CADCONTEST_FORCE_LLM", None)
    proc = subprocess.run(
        [binary, "-config", config],
        input=prompt,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    return parse_responses(proc.stdout)


def expand_tests(tokens: list[str]) -> list[str]:
    names: list[str] = []
    for tok in tokens:
        if "-" in tok:
            a, b = tok.split("-", 1)
            for i in range(int(a), int(b) + 1):
                names.append(f"test{i:02d}")
        else:
            names.append(tok if tok.startswith("test") else f"test{int(tok):02d}")
    return names


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--bin", default="./cada1089_alpha", dest="binary")
    ap.add_argument("tests", nargs="*", default=["01", "02", "03", "04", "05"])
    args = ap.parse_args()

    tests = expand_tests(args.tests)
    grand_total = grand_match = grand_mismatch = grand_err = 0

    for t in tests:
        prompt_path = ROOT / "testcase" / t / "prompt.txt"
        if not prompt_path.exists():
            print(f"[{t}] SKIP (no prompt.txt)")
            continue
        prompt = prompt_path.read_text(encoding="utf-8")
        requests = [ln.strip() for ln in prompt.splitlines() if ln.strip()]

        golden = run(args.binary, args.config, prompt, force_llm=False)
        llm = run(args.binary, args.config, prompt, force_llm=True)

        n = max(len(golden), len(llm), len(requests))
        match = mismatch = err = 0
        details: list[str] = []
        for i in range(n):
            req = requests[i] if i < len(requests) else "(?)"
            g = golden[i] if i < len(golden) else "(missing)"
            l = llm[i] if i < len(llm) else "(missing)"
            is_err = any(m in l for m in ERROR_MARKERS)
            if is_err:
                err += 1
                details.append(f"    ERR  L{i+1}: {req[:70]}\n         llm: {l[:120]}")
            elif norm(g) == norm(l):
                match += 1
            else:
                mismatch += 1
                details.append(
                    f"    DIFF L{i+1}: {req[:70]}\n"
                    f"         rule: {g[:120]}\n"
                    f"         llm : {l[:120]}"
                )

        total = match + mismatch + err
        grand_total += total
        grand_match += match
        grand_mismatch += mismatch
        grand_err += err
        rate = (match / total * 100) if total else 0.0
        print(f"[{t}] {match}/{total} match ({rate:.0f}%), "
              f"mismatch={mismatch}, err={err}")
        for d in details:
            print(d)

    print("\n=== TOTAL ===")
    rate = (grand_match / grand_total * 100) if grand_total else 0.0
    print(f"match {grand_match}/{grand_total} ({rate:.0f}%), "
          f"mismatch={grand_mismatch}, err={grand_err}")
    print("(rule-engine output is treated as golden; mismatch/err = LLM diverged)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
