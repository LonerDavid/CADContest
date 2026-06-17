"""Step 3: LLM client (OpenAI / Anthropic) with Tool Spec system prompt."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ..eda.context import EDASession
from . import usage_log
from .tool_spec import SYSTEM_PROMPT, build_user_message


class LLMClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.provider = cfg.get("provider", "openai")
        gen = cfg.get("generation", {})
        self.temperature = gen.get("temperature", 0.2)
        self.max_tokens = gen.get("max_output_tokens", 4096)

    def _openai_client(self):
        from openai import OpenAI

        return OpenAI(api_key=self.cfg.get("openai", {}).get("api_key", ""))

    def _anthropic_client(self):
        import anthropic

        return anthropic.Anthropic(api_key=self.cfg.get("anthropic", {}).get("api_key", ""))

    def complete(
        self,
        system: str,
        user: str,
        case_name: Optional[str] = None,
        request: Optional[str] = None,
    ) -> str:
        if self.provider == "anthropic":
            acfg = self.cfg.get("anthropic", {})
            model = acfg.get("model", "claude-haiku-4-5")
            client = self._anthropic_client()
            msg = client.messages.create(
                model=model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            u = getattr(msg, "usage", None)
            prompt_tokens = getattr(u, "input_tokens", 0) or 0
            completion_tokens = getattr(u, "output_tokens", 0) or 0
            usage_log.record(
                "anthropic", model, prompt_tokens, completion_tokens,
                prompt_tokens + completion_tokens, case_name, request,
            )
            return "".join(b.text for b in msg.content if hasattr(b, "text"))

        ocfg = self.cfg.get("openai", {})
        model = ocfg.get("model", "gpt-4o-mini")
        resp = self._openai_client().chat.completions.create(
            model=model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        u = getattr(resp, "usage", None)
        usage_log.record(
            "openai", model,
            getattr(u, "prompt_tokens", 0) or 0,
            getattr(u, "completion_tokens", 0) or 0,
            getattr(u, "total_tokens", 0) or 0,
            case_name, request,
        )
        return resp.choices[0].message.content or ""

    def plan_and_execute(self, request: str, session: EDASession) -> str:
        user = build_user_message(
            request, session.case_name, session.design_loaded
        )
        raw = self.complete(SYSTEM_PROMPT, user, session.case_name, request)
        start = raw.find("{")
        if start < 0:
            return f"LLM did not return valid JSON: {raw[:500]}"
        try:
            # Decode only the FIRST complete JSON object; ignore any trailing
            # text or extra objects the model may have appended.
            data, _ = json.JSONDecoder().raw_decode(raw[start:])
        except json.JSONDecodeError as e:
            return f"Invalid JSON from LLM: {e}\n{raw[:500]}"
        tool = data.get("tool")
        args = data.get("args") or {}
        if not tool:
            return f"LLM response missing 'tool': {raw[:500]}"
        return session.execute_tool(tool, args)
