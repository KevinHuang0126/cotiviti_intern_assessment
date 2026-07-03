"""Role 2 — Adversarial test suite generator."""

from __future__ import annotations

import json
from typing import Any

from src.llm import LLMClient
from src.prompts import ADVERSARY_SYSTEM, adversary_user_template
from src.schema import TEST_SUITE_SCHEMA, validate_test_suite

# Hand the model the SAME schema it will be validated against (mirrors the
# compiler). The earlier loose copy typed predicted_decision as a bare string,
# so the live model emitted values like "covered" that failed the
# approve/deny/review enum in validate_test_suite.
SUBMIT_TEST_SUITE_SCHEMA: dict[str, Any] = TEST_SUITE_SCHEMA

# Safety net for near-miss decision labels the model may still emit at
# temperature 1 despite the enum in the tool schema.
_DECISION_SYNONYMS = {
    "approve": "approve",
    "approved": "approve",
    "covered": "approve",
    "deny": "deny",
    "denied": "deny",
    "not_covered": "deny",
    "review": "review",
    "manual_review": "review",
    "requires_review": "review",
}


def _normalize_decisions(suite: dict[str, Any]) -> None:
    for claim in suite.get("claims", []):
        decision = claim.get("predicted_decision")
        if isinstance(decision, str):
            mapped = _DECISION_SYNONYMS.get(decision.strip().lower())
            if mapped:
                claim["predicted_decision"] = mapped


def _resolve_cite_offsets(suite: dict[str, Any], policy_text: str) -> None:
    for claim in suite.get("claims", []):
        for cite in claim.get("policy_cites", []):
            quote = cite.get("quote", "")
            if not quote:
                continue
            start = policy_text.find(quote)
            if start >= 0:
                cite["start"] = start
                cite["end"] = start + len(quote)


def generate_test_suite(
    client: LLMClient,
    section_id: str,
    policy_text: str,
    rule: dict[str, Any],
) -> dict[str, Any]:
    user = adversary_user_template(section_id, policy_text, json.dumps(rule, indent=2))
    suite = client.complete_tool(
        role="adversary",
        system=ADVERSARY_SYSTEM,
        user=user,
        tool_name="submit_test_suite",
        tool_schema=SUBMIT_TEST_SUITE_SCHEMA,
    )
    _normalize_decisions(suite)
    _resolve_cite_offsets(suite, policy_text)
    validate_test_suite(suite)
    return suite
