"""Step 3: Parse -config YAML for LLM provider settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


def load_config(path: str | Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg:
        raise ValueError(f"Empty config: {path}")
    provider = cfg.get("provider", "openai")
    if provider not in ("openai", "anthropic"):
        raise ValueError(f"Unsupported provider: {provider}")
    gen = cfg.get("generation", {})
    if "temperature" not in gen:
        gen["temperature"] = 0.2
    if "max_output_tokens" not in gen:
        gen["max_output_tokens"] = 4096
    cfg["generation"] = gen
    return cfg
