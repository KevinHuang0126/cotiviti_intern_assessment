"""Structural diff and behavioral impact analysis."""

from __future__ import annotations

import json
from typing import Any

from src.canonicalize import canonicalize_rule, enumerate_leaves, leaf_stable_id
from src.engine import RuleEngine


def structural_diff(rule_v1: dict[str, Any], rule_v2: dict[str, Any]) -> list[dict[str, Any]]:
    c1 = canonicalize_rule(rule_v1)
    c2 = canonicalize_rule(rule_v2)

    leaves1 = {leaf_type_key(l): (path, l) for path, l in enumerate_leaves(c1.get("condition", {}))}
    leaves2 = {leaf_type_key(l): (path, l) for path, l in enumerate_leaves(c2.get("condition", {}))}

    changes: list[dict[str, Any]] = []
    all_keys = set(leaves1) | set(leaves2)

    for key in sorted(all_keys):
        if key in leaves1 and key in leaves2:
            path1, l1 = leaves1[key]
            path2, l2 = leaves2[key]
            if json.dumps(l1, sort_keys=True) != json.dumps(l2, sort_keys=True):
                changes.append(
                    {
                        "change_type": "Modified",
                        "leaf_type": key,
                        "path_v1": path1,
                        "path_v2": path2,
                        "before": l1,
                        "after": l2,
                        "summary": summarize_leaf_change(l1, l2),
                    }
                )
        elif key in leaves1:
            path1, l1 = leaves1[key]
            changes.append(
                {
                    "change_type": "Removed",
                    "leaf_type": key,
                    "path_v1": path1,
                    "before": l1,
                    "summary": f"Removed {key}",
                }
            )
        else:
            path2, l2 = leaves2[key]
            changes.append(
                {
                    "change_type": "Added",
                    "leaf_type": key,
                    "path_v2": path2,
                    "after": l2,
                    "summary": f"Added {key}",
                }
            )

    return changes


def leaf_type_key(leaf: dict[str, Any]) -> str:
    """Stable key for pairing leaves across versions (by type, not value)."""
    op = leaf.get("op", "")
    if op == "age":
        return "age"
    if op == "code_set":
        return "code_set"
    if op == "documentation":
        doc_id = leaf.get("documentation", {}).get("id", "")
        return f"documentation:{doc_id}"
    return op


def summarize_leaf_change(before: dict[str, Any], after: dict[str, Any]) -> str:
    if before.get("op") == "age" and after.get("op") == "age":
        bmin = before.get("age", {}).get("min", {}).get("value")
        amin = after.get("age", {}).get("min", {}).get("value")
        return f"Age minimum {bmin} → {amin}"
    if before.get("op") == "documentation" and after.get("op") == "documentation":
        bt = before.get("documentation", {}).get("text", "")
        at = after.get("documentation", {}).get("text", "")
        return f"Documentation text changed"
    if before.get("op") == "code_set" and after.get("op") == "code_set":
        bc = [c.get("code") for c in before.get("codeSet", {}).get("codes", [])]
        ac = [c.get("code") for c in after.get("codeSet", {}).get("codes", [])]
        return f"Covered codes {bc} → {ac}"
    return "Leaf modified"


def behavioral_impact(
    rule_v1: dict[str, Any],
    rule_v2: dict[str, Any],
    suite_v1: dict[str, Any],
    suite_v2: dict[str, Any],
) -> list[dict[str, Any]]:
    engine = RuleEngine()
    claims_by_id: dict[str, dict[str, Any]] = {}

    for suite in (suite_v1, suite_v2):
        for test in suite.get("claims", []):
            claims_by_id[test["id"]] = test

    flipped: list[dict[str, Any]] = []
    for test_id, test in claims_by_id.items():
        claim = test["claim"]
        d1 = engine.run_rule_on_claim(rule_v1, claim)
        d2 = engine.run_rule_on_claim(rule_v2, claim)
        if d1 != d2:
            flipped.append(
                {
                    "id": test_id,
                    "claim": claim,
                    "decision_v1": d1,
                    "decision_v2": d2,
                    "rationale": test.get("rationale", ""),
                    "demo_value": _demo_value(d1, d2),
                }
            )

    flipped.sort(key=lambda x: (-x["demo_value"], x["id"]))
    return flipped


def _demo_value(d1: str, d2: str) -> int:
    pair = {d1, d2}
    if pair == {"approve", "deny"}:
        return 3
    if "review" in pair:
        return 1
    return 0


def diff_report(
    rule_v1: dict[str, Any],
    rule_v2: dict[str, Any],
    suite_v1: dict[str, Any],
    suite_v2: dict[str, Any],
) -> dict[str, Any]:
    structural = structural_diff(rule_v1, rule_v2)
    flipped = behavioral_impact(rule_v1, rule_v2, suite_v1, suite_v2)
    modified = [c for c in structural if c["change_type"] == "Modified"]
    return {
        "structural_changes": structural,
        "modified_count": len(modified),
        "flipped_claims": flipped,
        "headline_claim": next((f for f in flipped if f["id"] == "headline-flip-patient"), flipped[0] if flipped else None),
    }


def format_diff_highlights(changes: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Format for gr.HighlightedText: list of (token, label)."""
    highlights: list[tuple[str, str]] = []
    for c in changes:
        if c["change_type"] == "Modified":
            highlights.append((c.get("summary", "Modified"), "-"))
            if "after" in c:
                highlights.append((c["summary"], "+"))
        elif c["change_type"] == "Removed":
            highlights.append((c.get("summary", "Removed"), "-"))
        elif c["change_type"] == "Added":
            highlights.append((c.get("summary", "Added"), "+"))
    return highlights
