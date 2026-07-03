"""Diff and behavioral impact tests for NCD 210.14."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.diff import diff_report, structural_diff
from src.fixtures_loader import load_test_suite

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def rule_v1() -> dict:
    return json.loads((FIXTURES / "known_good_rule_v1.json").read_text())


@pytest.fixture
def rule_v2() -> dict:
    return json.loads((FIXTURES / "known_good_rule_v2.json").read_text())


def test_ncd_210_14_three_modified_leaves(rule_v1, rule_v2):
    changes = structural_diff(rule_v1, rule_v2)
    modified = [c for c in changes if c["change_type"] == "Modified"]
    assert len(modified) == 3
    types = {c["leaf_type"] for c in modified}
    assert "age" in types
    assert "documentation:pack-years" in types
    assert "code_set" in types


def test_headline_claim_in_flip_set(rule_v1, rule_v2):
    report = diff_report(
        rule_v1, rule_v2, load_test_suite("v1"), load_test_suite("v2")
    )
    ids = {f["id"] for f in report["flipped_claims"]}
    assert "headline-flip-patient" in ids
    headline = next(f for f in report["flipped_claims"] if f["id"] == "headline-flip-patient")
    assert headline["decision_v1"] == "deny"
    assert headline["decision_v2"] == "approve"
