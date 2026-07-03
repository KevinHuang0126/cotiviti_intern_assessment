"""Thin Anthropic SDK wrapper with disk cache and fixture replay."""

from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache" / "llm"
GOLDEN_DIR = CACHE_DIR / "golden"

MODEL_COMPILER = "claude-sonnet-5"
MODEL_FIXER = "claude-sonnet-5"
MODEL_ADVERSARY = "claude-haiku-4-5"

ROLE_MODELS = {
    "compiler": MODEL_COMPILER,
    "fixer": MODEL_FIXER,
    "adversary": MODEL_ADVERSARY,
}


def _hash_payload(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode())
    return h.hexdigest()[:24]


def _coerce_json_strings(result: dict[str, Any], tool_schema: dict[str, Any]) -> dict[str, Any]:
    """Anthropic tool use sometimes returns a nested object/array param (e.g.
    `condition`) as a JSON-encoded string when the schema is deeply nested.
    Decode any such field whose schema type is not plain string."""
    props = tool_schema.get("properties", {})
    for key, value in list(result.items()):
        if not isinstance(value, str):
            continue
        prop = props.get(key, {})
        if prop.get("type") == "string" or "enum" in prop:
            continue
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, (dict, list)):
            result[key] = decoded
    return result


class LLMClient(ABC):
    @abstractmethod
    def complete_tool(
        self,
        role: str,
        system: str,
        user: str,
        tool_name: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class CachedAnthropicClient(LLMClient):
    def __init__(self, mode: str = "live") -> None:
        self.mode = mode
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        self._live: LLMClient | None = None
        if mode == "live":
            self._live = AnthropicClient()

    def _cache_path(self, role: str, key: str) -> Path:
        return CACHE_DIR / f"{role}_{key}.json"

    def _golden_path(self, role: str, key: str) -> Path:
        return GOLDEN_DIR / f"{role}_{key}.json"

    def complete_tool(
        self,
        role: str,
        system: str,
        user: str,
        tool_name: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        model = ROLE_MODELS.get(role, MODEL_COMPILER)
        key = _hash_payload(model, system, user, tool_name, json.dumps(tool_schema, sort_keys=True))

        if self.mode == "replay":
            for path in (self._golden_path(role, key), self._cache_path(role, key)):
                if path.exists():
                    cached = json.loads(path.read_text(encoding="utf-8"))
                    return _coerce_json_strings(cached, tool_schema)

        if self.mode == "replay":
            raise FileNotFoundError(
                f"No cached response for role={role} key={key}. Run with --demo-mode live first."
            )

        assert self._live is not None
        result = self._live.complete_tool(role, system, user, tool_name, tool_schema)
        payload = json.dumps(result, indent=2)
        self._cache_path(role, key).write_text(payload, encoding="utf-8")
        return result


class AnthropicClient(LLMClient):
    def complete_tool(
        self,
        role: str,
        system: str,
        user: str,
        tool_name: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        import anthropic
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY required for live mode")

        client = anthropic.Anthropic(api_key=api_key)
        model = ROLE_MODELS.get(role, MODEL_COMPILER)

        response = client.messages.create(
            model=model,
            # Large enough for the adversary's 10-15 claim suite (~10k+ tokens).
            # A truncated tool call parses as input={} and fails validation.
            max_tokens=16384,
            temperature=1,
            # Forced tool_choice is incompatible with adaptive thinking, which is
            # ON by default on Sonnet 5. Disable thinking so the structured tool
            # call is deterministic and legal. (No-op on Haiku 4.5, thinking-off.)
            thinking={"type": "disabled"},
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[
                {
                    "name": tool_name,
                    "description": f"Submit {role} output",
                    "input_schema": tool_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )

        if response.stop_reason == "max_tokens":
            raise RuntimeError(
                f"{role} response truncated at max_tokens; tool input would be "
                "incomplete. Increase max_tokens."
            )

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                if not block.input:
                    raise RuntimeError(f"Empty tool input from {role}")
                return _coerce_json_strings(dict(block.input), tool_schema)

        raise RuntimeError(f"No tool output from {role}")


class FixtureClient(LLMClient):
    """Returns pre-built fixtures keyed by role for offline demo."""

    FIXTURES: dict[str, dict[str, Any]] = {}

    def complete_tool(
        self,
        role: str,
        system: str,
        user: str,
        tool_name: str,
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        from src.fixtures_loader import get_fixture_response

        return get_fixture_response(role, user, tool_name)


def get_client(mode: str = "replay") -> LLMClient:
    if mode == "fixture":
        return FixtureClient()
    if mode in ("replay", "live"):
        return CachedAnthropicClient(mode=mode)
    raise ValueError(f"Unknown demo mode: {mode}")
