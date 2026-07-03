"""Snapshot tests for compiled rules."""

from __future__ import annotations

import json
from pathlib import Path

from src.compiler import SUBMIT_RULE_SCHEMA
from src.llm import _coerce_json_strings
from src.schema import iter_leaves, resolve_citation_offsets, validate_rule

FIXTURES = Path(__file__).parent / "fixtures"


def test_known_good_rules_validate():
    for name in ("known_good_rule_v1.json", "known_good_rule_v2.json"):
        rule = json.loads((FIXTURES / name).read_text())
        validate_rule(rule)


def test_coerce_json_strings_decodes_stringified_condition():
    rule = json.loads((FIXTURES / "known_good_rule_v1.json").read_text())
    stringified = dict(rule, condition=json.dumps(rule["condition"]))

    coerced = _coerce_json_strings(stringified, SUBMIT_RULE_SCHEMA)

    assert coerced["condition"] == rule["condition"]
    validate_rule(coerced)


def test_resolve_citation_offsets_fills_start_end():
    source = "Preamble text. The beneficiary must be Age 50 - 77 years. Trailing text."
    rule = {
        "criterionId": "x",
        "policy": {"policyId": "p", "policyType": "NCD", "version": "1"},
        "condition": {
            "op": "age",
            "age": {"min": {"value": 50, "unit": "year"}},
            "citations": [
                {"span": {"text": "The beneficiary must be Age 50 - 77 years.", "start": 0, "end": 0}}
            ],
        },
    }

    resolve_citation_offsets(rule, source)

    span = rule["condition"]["citations"][0]["span"]
    assert span["start"] == source.index("The beneficiary")
    assert span["end"] == span["start"] + len(span["text"])
    assert source[span["start"] : span["end"]] == span["text"]
    validate_rule(rule)


def test_resolve_citation_offsets_ignores_missing_quotes():
    rule = {
        "criterionId": "x",
        "policy": {"policyId": "p", "policyType": "NCD", "version": "1"},
        "condition": {
            "op": "manual_review",
            "reason": "r",
            "citations": [{"span": {"text": "not in source", "start": 0, "end": 0}}],
        },
    }

    resolve_citation_offsets(rule, "completely different text")

    span = rule["condition"]["citations"][0]["span"]
    assert (span["start"], span["end"]) == (0, 0)


def test_coerce_json_strings_leaves_plain_strings_alone():
    rule = json.loads((FIXTURES / "known_good_rule_v1.json").read_text())
    # criterionId is a string-typed field; even if it happens to contain JSON,
    # it must not be decoded.
    rule["criterionId"] = '{"looks": "like json"}'

    coerced = _coerce_json_strings(dict(rule), SUBMIT_RULE_SCHEMA)

    assert coerced["criterionId"] == '{"looks": "like json"}'
