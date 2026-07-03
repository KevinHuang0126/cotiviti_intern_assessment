"""Role 1 — Policy section to executable rule."""

from __future__ import annotations

import json
from typing import Any

from src.llm import LLMClient
from src.prompts import COMPILER_SYSTEM, compiler_user_template
from src.schema import (
    load_schema,
    resolve_citation_offsets,
    validate_citations_in_source,
    validate_rule,
)

# Hand the model the SAME schema it will be validated against, so the forced
# tool call is guided to the exact condition-tree grammar (`of` not `children`,
# age.min as {value, unit}, codeSet.kind + codes[{system, code}], documentation
# as {id, text, required}, ...). A loose tool schema let the live model invent
# structurally-different-but-plausible JSON that then failed validate_rule.
# Drop JSON-Schema meta keys ($schema/$id) the Anthropic tools API may reject.
SUBMIT_RULE_SCHEMA: dict[str, Any] = {
    k: v for k, v in load_schema().items() if not k.startswith("$schema") and k != "$id"
}


def compile_rule(
    client: LLMClient,
    section_id: str,
    policy_version: str,
    policy_text: str,
    *,
    validate_cites: bool = True,
) -> dict[str, Any]:
    user = compiler_user_template(section_id, policy_version, policy_text)
    rule = client.complete_tool(
        role="compiler",
        system=COMPILER_SYSTEM,
        user=user,
        tool_name="submit_rule",
        tool_schema=SUBMIT_RULE_SCHEMA,
    )
    validate_rule(rule)
    resolve_citation_offsets(rule, policy_text)
    if validate_cites:
        errors = validate_citations_in_source(rule, policy_text)
        if errors:
            raise ValueError(f"Citation validation failed: {errors}")
    return rule


def seed_defective_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Deliberately wrong age threshold for demo loop."""
    import copy

    bad = copy.deepcopy(rule)
    for leaf in _walk(bad.get("condition", {})):
        if leaf.get("op") == "age":
            leaf["age"]["min"] = {"value": 50, "unit": "year"}
            if leaf.get("citations"):
                leaf["citations"][0]["span"] = {"text": "age 50"}
    return bad


def _walk(node: dict[str, Any]):
    op = node.get("op")
    if op in ("and", "or"):
        for c in node.get("of", []):
            yield from _walk(c)
    elif op == "not":
        yield from _walk(node.get("of", {}))
    else:
        yield node
