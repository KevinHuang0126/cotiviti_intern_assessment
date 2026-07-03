"""Role 3 — Minimal rule patch from failing tests."""

from __future__ import annotations

import json
from typing import Any

from src.llm import LLMClient
from src.prompts import FIXER_SYSTEM, fixer_user_template
from src.schema import load_schema, resolve_citation_offsets, validate_rule

# Embed the full criterion schema for patched_rule (mirrors the compiler's
# strict tool schema) so the fixer can't emit a structurally different rule
# that then fails validate_rule. The criterion schema's $refs point at
# "#/$defs/...", so its $defs must be hoisted to this schema's root.
_criterion = load_schema()
SUBMIT_PATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["patched_rule"],
    "properties": {
        "patched_rule": {
            k: v for k, v in _criterion.items() if k not in ("$schema", "$id", "$defs")
        },
        "changelog": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["change"],
                "properties": {
                    "change": {"type": "string"},
                    "reason": {"type": "string"},
                    "cite": {"type": "string"},
                },
            },
        },
        "unresolved": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["issue"],
                "properties": {
                    "issue": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
    },
    "$defs": _criterion["$defs"],
}


def patch_rule(
    client: LLMClient,
    policy_text: str,
    rule: dict[str, Any],
    failures: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    user = fixer_user_template(
        policy_text, json.dumps(rule, indent=2), json.dumps(failures, indent=2)
    )
    result = client.complete_tool(
        role="fixer",
        system=FIXER_SYSTEM,
        user=user,
        tool_name="submit_patch",
        tool_schema=SUBMIT_PATCH_SCHEMA,
    )
    patched = result["patched_rule"]
    if isinstance(patched, str):
        patched = json.loads(patched)
    validate_rule(patched)
    resolve_citation_offsets(patched, policy_text)
    meta = {
        "changelog": _normalize_entries(result.get("changelog", [])),
        "unresolved": _normalize_entries(result.get("unresolved", []), key="issue"),
    }
    return patched, meta


def _normalize_entries(entries: Any, key: str = "change") -> list[dict[str, Any]]:
    """The changelog/unresolved arrays have no item schema, so the model may
    return strings or dicts. Normalize to dicts so the UI can render them."""
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for e in entries:
        if isinstance(e, dict):
            out.append(e)
        elif isinstance(e, str):
            out.append({key: e})
        else:
            out.append({key: str(e)})
    return out
