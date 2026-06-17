"""
Step 4: Main I/O loop — stdin requests, agent + EDA execution, strict response tags.

Usage: ./cada1089_alpha -config <config.yaml>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.agent.handler import NEW_CASE_RE, RequestHandler, extract_case_name
from python.agent.llm import LLMClient
from python.config import load_config
from python.eda.context import EDASession
from python.response import ResponseWriter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ICCAD 2026 Problem A — LLM-Assisted Netlist EDA"
    )
    parser.add_argument(
        "-config",
        required=True,
        dest="config_path",
        help="YAML config (provider, api_key, model, temperature, max_output_tokens)",
    )
    args = parser.parse_args()

    cfg = load_config(args.config_path)
    session = EDASession()
    llm = LLMClient(cfg)
    handler = RequestHandler(session, llm)
    writer = ResponseWriter()

    for line in sys.stdin:
        request = line.rstrip("\n")
        if not request.strip():
            continue

        if NEW_CASE_RE.search(request):
            name = extract_case_name(request)
            if name:
                writer.begin_testcase(name)

        try:
            result = handler.handle(request)
        except Exception as e:
            result = f"Error: {e}"

        writer.emit(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
