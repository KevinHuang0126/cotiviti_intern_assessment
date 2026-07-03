"""Coverage policy criterion schema and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent / "criterion_schema.json"

OPERATOR_ALLOWLIST = frozenset(
    {
        "and",
        "or",
        "not",
        "==",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "in",
        "manual_review",
        "code_in_set",
        "age_at_dos",
        "frequency_in_window",
    }
)


def load_schema() -> dict[str, Any]:
    if SCHEMA_PATH.exists():
        return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return CRITERION_JSON_SCHEMA


def validate_rule(rule: dict[str, Any]) -> None:
    jsonschema.validate(instance=rule, schema=load_schema())


def validate_test_suite(suite: dict[str, Any]) -> None:
    jsonschema.validate(instance=suite, schema=TEST_SUITE_SCHEMA)


def validate_citations_in_source(rule: dict[str, Any], source_text: str) -> list[str]:
    """Return list of citation errors (empty if all valid)."""
    errors: list[str] = []
    for leaf in iter_leaves(rule.get("condition", {})):
        for cite in leaf.get("citations", []):
            quote = cite.get("span", {}).get("text") or cite.get("quote", "")
            if not quote:
                errors.append(f"Missing cite quote on leaf op={leaf.get('op')}")
                continue
            if quote not in source_text:
                errors.append(f"Cite not verbatim in source: {quote!r}")
    return errors


def resolve_citation_offsets(rule: dict[str, Any], source_text: str) -> dict[str, Any]:
    """Fill span.start/span.end by locating each citation quote in the source.

    LLMs cannot count character offsets and emit placeholder 0s; offsets are a
    deterministic lookup, so compute them here. Citations whose quote is not
    found verbatim are left untouched (validate_citations_in_source reports
    those separately)."""
    for leaf in iter_leaves(rule.get("condition", {})):
        for cite in leaf.get("citations", []):
            _resolve_span(cite, source_text)
    for cite in rule.get("citations", []):
        _resolve_span(cite, source_text)
    for doc in rule.get("documentation", []):
        for cite in doc.get("citations", []):
            _resolve_span(cite, source_text)
    return rule


def _resolve_span(cite: dict[str, Any], source_text: str) -> None:
    span = cite.get("span") or {}
    quote = span.get("text") or cite.get("quote", "")
    if not quote:
        return
    start = source_text.find(quote)
    if start < 0:
        return
    span.update({"text": quote, "start": start, "end": start + len(quote)})
    cite["span"] = span


def iter_leaves(condition: dict[str, Any]) -> list[dict[str, Any]]:
    op = condition.get("op")
    if op in ("and", "or"):
        leaves: list[dict[str, Any]] = []
        for child in condition.get("of", []):
            leaves.extend(iter_leaves(child))
        return leaves
    if op == "not":
        return iter_leaves(condition.get("of", {}))
    if op == "at_least":
        return iter_leaves(condition.get("of", {}))
    return [condition]


CRITERION_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.org/schemas/coverage-policy-criterion.json",
    "title": "CoveragePolicyCriterion",
    "type": "object",
    "required": ["criterionId", "policy", "condition"],
    "additionalProperties": False,
    "properties": {
        "criterionId": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "policy": {"$ref": "#/$defs/PolicyMetadata"},
        "condition": {"$ref": "#/$defs/Condition"},
        "outcome": {
            "enum": ["covered", "not_covered", "covered_with_conditions", "requires_prior_auth"]
        },
        "documentation": {"type": "array", "items": {"$ref": "#/$defs/DocumentationRequirement"}},
        "citations": {"type": "array", "items": {"$ref": "#/$defs/Citation"}},
    },
    "$defs": {
        "PolicyMetadata": {
            "type": "object",
            "required": ["policyId", "policyType", "version"],
            "properties": {
                "policyId": {"type": "string"},
                "policyType": {"type": "string"},
                "version": {"type": "string"},
                "effectiveDate": {"type": "string"},
                "url": {"type": "string"},
            },
        },
        "Quantity": {
            "type": "object",
            "required": ["value", "unit"],
            "properties": {
                "value": {"type": "number"},
                "unit": {"enum": ["day", "week", "month", "year"]},
            },
        },
        "Citation": {
            "type": "object",
            "properties": {
                "sourceId": {"type": "string"},
                "section": {"type": "string"},
                "span": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "start": {"type": "integer"},
                        "end": {"type": "integer"},
                    },
                },
                "quote": {"type": "string"},
            },
        },
        "CodeRef": {
            "type": "object",
            "required": ["system", "code"],
            "properties": {
                "system": {"type": "string"},
                "code": {"type": "string"},
                "display": {"type": "string"},
            },
        },
        "Condition": {
            "oneOf": [
                {"$ref": "#/$defs/AndNode"},
                {"$ref": "#/$defs/OrNode"},
                {"$ref": "#/$defs/NotNode"},
                {"$ref": "#/$defs/LeafAge"},
                {"$ref": "#/$defs/LeafCodeSet"},
                {"$ref": "#/$defs/LeafDocumentation"},
                {"$ref": "#/$defs/LeafManualReview"},
            ]
        },
        "AndNode": {
            "type": "object",
            "required": ["op", "of"],
            "properties": {
                "op": {"const": "and"},
                "of": {"type": "array", "items": {"$ref": "#/$defs/Condition"}},
            },
        },
        "OrNode": {
            "type": "object",
            "required": ["op", "of"],
            "properties": {
                "op": {"const": "or"},
                "of": {"type": "array", "items": {"$ref": "#/$defs/Condition"}},
            },
        },
        "NotNode": {
            "type": "object",
            "required": ["op", "of"],
            "properties": {
                "op": {"const": "not"},
                "of": {"$ref": "#/$defs/Condition"},
            },
        },
        "LeafAge": {
            "type": "object",
            "required": ["op", "age"],
            "properties": {
                "op": {"const": "age"},
                "age": {
                    "type": "object",
                    "properties": {
                        "min": {"$ref": "#/$defs/Quantity"},
                        "max": {"$ref": "#/$defs/Quantity"},
                    },
                },
                "citations": {"type": "array", "items": {"$ref": "#/$defs/Citation"}},
            },
        },
        "LeafCodeSet": {
            "type": "object",
            "required": ["op", "codeSet"],
            "properties": {
                "op": {"const": "code_set"},
                "codeSet": {
                    "type": "object",
                    "required": ["kind", "codes"],
                    "properties": {
                        "kind": {
                            "enum": [
                                "procedure_covered",
                                "procedure_not_covered",
                                "diagnosis_required",
                                "diagnosis_excluded",
                            ]
                        },
                        "codes": {"type": "array", "items": {"$ref": "#/$defs/CodeRef"}},
                    },
                },
                "citations": {"type": "array", "items": {"$ref": "#/$defs/Citation"}},
            },
        },
        "LeafDocumentation": {
            "type": "object",
            "required": ["op", "documentation"],
            "properties": {
                "op": {"const": "documentation"},
                "documentation": {"$ref": "#/$defs/DocumentationRequirement"},
                "citations": {"type": "array", "items": {"$ref": "#/$defs/Citation"}},
            },
        },
        "LeafManualReview": {
            "type": "object",
            "required": ["op", "reason"],
            "properties": {
                "op": {"const": "manual_review"},
                "reason": {"type": "string"},
                "citations": {"type": "array", "items": {"$ref": "#/$defs/Citation"}},
            },
        },
        "DocumentationRequirement": {
            "type": "object",
            "required": ["id", "text", "required"],
            "properties": {
                "id": {"type": "string"},
                "text": {"type": "string"},
                "required": {"type": "boolean"},
                "citations": {"type": "array", "items": {"$ref": "#/$defs/Citation"}},
            },
        },
    },
}


# Canonical claim shape consumed by claim_context.build_context. Handing this
# to the adversary model (via the tool schema) keeps it from inventing flat
# field names (member_age, procedure_code, ...) the engine cannot read.
CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "member": {
            "type": "object",
            "properties": {
                "age_years": {"type": ["number", "null"]},
                "sex": {"type": "string"},
                "pack_years": {"type": ["number", "null"]},
                "smoker_status": {"type": ["string", "null"]},
                "years_since_quit": {"type": ["number", "null"]},
                "asymptomatic": {"type": ["boolean", "null"]},
            },
        },
        "dos": {"type": "string"},
        "px_codes": {"type": "array", "items": {"type": "string"}},
        "dx_codes": {"type": "array", "items": {"type": "string"}},
        "sdm_visit_completed": {"type": "boolean"},
        "written_order": {"type": "boolean"},
        "documentation": {"type": "object"},
    },
}


TEST_SUITE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["claims"],
    "properties": {
        "claims": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "claim", "probes", "predicted_decision", "rationale", "policy_cites"],
                "properties": {
                    "id": {"type": "string"},
                    "claim": CLAIM_SCHEMA,
                    "probes": {"type": "array", "items": {"type": "string"}},
                    "predicted_decision": {"enum": ["approve", "deny", "review"]},
                    "rationale": {"type": "string"},
                    "policy_cites": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "start": {"type": "integer"},
                                "end": {"type": "integer"},
                                "quote": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }
    },
}
