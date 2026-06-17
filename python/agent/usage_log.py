"""Local token-usage logging for LLM calls.

Each LLM call appends one row to a CSV and updates a cumulative JSON summary,
so token consumption can be inspected locally without waiting for the provider
dashboard. Override the location with CADCONTEST_TOKEN_LOG (CSV path); the JSON
summary lives next to it as <name>.summary.json.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..output_paths import OUTPUT_ROOT

_CSV_HEADER = [
    "timestamp",
    "provider",
    "model",
    "case",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "request",
]


def _csv_path() -> Path:
    env = os.environ.get("CADCONTEST_TOKEN_LOG")
    if env:
        return Path(env)
    return OUTPUT_ROOT / "token_usage.csv"


def _summary_path(csv_path: Path) -> Path:
    return csv_path.with_suffix(csv_path.suffix + ".summary.json")


def record(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    case_name: Optional[str] = None,
    request: Optional[str] = None,
) -> None:
    """Append a usage row and update the cumulative summary. Never raises."""
    try:
        csv_path = _csv_path()
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        write_header = not csv_path.exists() or csv_path.stat().st_size == 0
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(csv_path, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_CSV_HEADER)
            writer.writerow([
                ts,
                provider,
                model,
                case_name or "",
                prompt_tokens,
                completion_tokens,
                total_tokens,
                (request or "")[:120].replace("\n", " "),
            ])

        _update_summary(_summary_path(csv_path), provider, model,
                        prompt_tokens, completion_tokens, total_tokens)
    except Exception:
        # Usage logging must never break a real request.
        pass


def _update_summary(
    path: Path,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    data = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
            "total_tokens": 0, "by_model": {}}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    data["calls"] = data.get("calls", 0) + 1
    data["prompt_tokens"] = data.get("prompt_tokens", 0) + prompt_tokens
    data["completion_tokens"] = data.get("completion_tokens", 0) + completion_tokens
    data["total_tokens"] = data.get("total_tokens", 0) + total_tokens

    key = f"{provider}/{model}"
    bucket = data.setdefault("by_model", {}).get(
        key, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    )
    bucket["calls"] += 1
    bucket["prompt_tokens"] += prompt_tokens
    bucket["completion_tokens"] += completion_tokens
    bucket["total_tokens"] += total_tokens
    data["by_model"][key] = bucket
    data["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
