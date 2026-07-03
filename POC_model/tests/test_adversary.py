"""Tests for adversary output normalization and schema alignment."""

from __future__ import annotations

import jsonschema
import pytest

from src.adversary import SUBMIT_TEST_SUITE_SCHEMA, _normalize_decisions, _resolve_cite_offsets
from src.fixer import SUBMIT_PATCH_SCHEMA
from src.schema import TEST_SUITE_SCHEMA, validate_test_suite


def _suite(decision: str) -> dict:
    return {
        "claims": [
            {
                "id": "c1",
                "claim": {"member": {"age_years": 55}},
                "probes": ["age_boundary"],
                "predicted_decision": decision,
                "rationale": "r",
                "policy_cites": [{"quote": "Age 50 - 77 years", "start": 0, "end": 0}],
            }
        ]
    }


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("covered", "approve"),
        ("Approved", "approve"),
        ("not_covered", "deny"),
        ("denied", "deny"),
        ("manual_review", "review"),
        ("review", "review"),
    ],
)
def test_normalize_decisions_maps_synonyms(raw, expected):
    suite = _suite(raw)
    _normalize_decisions(suite)
    assert suite["claims"][0]["predicted_decision"] == expected
    validate_test_suite(suite)


def test_normalize_decisions_leaves_unknown_values():
    suite = _suite("gibberish")
    _normalize_decisions(suite)
    assert suite["claims"][0]["predicted_decision"] == "gibberish"
    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate_test_suite(suite)


def test_resolve_cite_offsets_locates_quote():
    source = "Coverage: Age 50 - 77 years required."
    suite = _suite("approve")
    _resolve_cite_offsets(suite, source)
    cite = suite["claims"][0]["policy_cites"][0]
    assert source[cite["start"] : cite["end"]] == cite["quote"]


def test_adversary_tool_schema_matches_validation_schema():
    # The schema handed to the model must be the one we validate against,
    # so the predicted_decision enum reaches the model.
    assert SUBMIT_TEST_SUITE_SCHEMA is TEST_SUITE_SCHEMA


def test_fixer_patch_schema_accepts_known_good_rule():
    import json
    from pathlib import Path

    rule = json.loads(
        (Path(__file__).parent / "fixtures" / "known_good_rule_v1.json").read_text()
    )
    jsonschema.validate(
        instance={"patched_rule": rule, "changelog": [], "unresolved": []},
        schema=SUBMIT_PATCH_SCHEMA,
    )
