"""Stable canonical form for rules before diffing."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


def canonicalize_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Reduce rule to canonical form (idempotent)."""
    out = deepcopy(rule)
    out["condition"] = _canonicalize_condition(out.get("condition", {}))
    return _sort_keys(out)


def canonical_hash(rule: dict[str, Any]) -> str:
    canonical = canonicalize_rule(rule)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _sort_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sort_keys(obj[k]) for k in sorted(obj.keys())}
    if isinstance(obj, list):
        return [_sort_keys(x) for x in obj]
    if isinstance(obj, str):
        return obj.strip()
    return obj


def _canonicalize_condition(node: dict[str, Any]) -> dict[str, Any]:
    op = node.get("op")
    if op in ("and", "or"):
        children = [_canonicalize_condition(c) for c in node.get("of", [])]
        children = [_collapse_singletons(c) for c in children]
        children.sort(key=lambda c: json.dumps(c, sort_keys=True))
        if len(children) == 1:
            return children[0]
        return {"op": op, "of": children}
    if op == "not":
        return {"op": "not", "of": _canonicalize_condition(node.get("of", {}))}
    if op == "code_set":
        n = deepcopy(node)
        codes = n.get("codeSet", {}).get("codes", [])
        codes.sort(key=lambda c: (c.get("system", ""), c.get("code", "")))
        n["codeSet"]["codes"] = codes
        return _sort_keys(n)
    return _sort_keys(deepcopy(node))


def _collapse_singletons(node: dict[str, Any]) -> dict[str, Any]:
    if node.get("op") in ("and", "or") and len(node.get("of", [])) == 1:
        return node["of"][0]
    return node


def leaf_stable_id(node: dict[str, Any], parent_path: str = "") -> str:
    op = node.get("op", "")
    if op in ("and", "or", "not"):
        return f"{parent_path}/{op}"
    payload = json.dumps(node, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(payload.encode()).hexdigest()[:12]
    return f"{parent_path}/{op}:{h}"


def enumerate_leaves(
    condition: dict[str, Any], parent_path: str = "condition"
) -> list[tuple[str, dict[str, Any]]]:
    op = condition.get("op")
    if op in ("and", "or"):
        leaves: list[tuple[str, dict[str, Any]]] = []
        for i, child in enumerate(condition.get("of", [])):
            leaves.extend(enumerate_leaves(child, f"{parent_path}/of[{i}]"))
        return leaves
    if op == "not":
        return enumerate_leaves(condition.get("of", {}), f"{parent_path}/not")
    return [(leaf_stable_id(condition, parent_path), condition)]
