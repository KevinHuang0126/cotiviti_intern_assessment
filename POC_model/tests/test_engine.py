"""Engine soundness tests on hand-written rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.engine import RuleEngine, EngineError
from src.schema import OPERATOR_ALLOWLIST

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def engine() -> RuleEngine:
    return RuleEngine()


@pytest.fixture
def rule_v1() -> dict:
    return json.loads((FIXTURES / "known_good_rule_v1.json").read_text())


@pytest.fixture
def rule_v2() -> dict:
    return json.loads((FIXTURES / "known_good_rule_v2.json").read_text())


def test_headline_patient_denied_v1(engine, rule_v1):
    claim = {
        "member": {
            "age_years": 52,
            "pack_years": 22,
            "smoker_status": "former",
            "years_since_quit": 8,
        },
        "px_codes": ["G0297"],
        "sdm_visit_completed": True,
        "documentation": {"min_pack_years": 30},
    }
    assert engine.run_rule_on_claim(rule_v1, claim) == "deny"


def test_headline_patient_approved_v2(engine, rule_v2):
    claim = {
        "member": {
            "age_years": 52,
            "pack_years": 22,
            "smoker_status": "former",
            "years_since_quit": 8,
        },
        "px_codes": ["71271"],
        "sdm_visit_completed": True,
        "documentation": {"min_pack_years": 20},
    }
    assert engine.run_rule_on_claim(rule_v2, claim) == "approve"


def test_age_boundary_at_min_v1(engine, rule_v1):
    claim = {
        "member": {"age_years": 55, "pack_years": 35, "smoker_status": "current"},
        "px_codes": ["G0297"],
        "sdm_visit_completed": True,
        "documentation": {"min_pack_years": 30},
    }
    assert engine.run_rule_on_claim(rule_v1, claim) == "approve"


def test_undocumented_fact_routes_to_review(engine, rule_v1):
    # Smoking status entirely undocumented -> manual review, not deny.
    claim = {
        "member": {"age_years": 60, "pack_years": 40},
        "px_codes": ["G0297"],
        "sdm_visit_completed": True,
        "documentation": {"min_pack_years": 30},
    }
    assert engine.run_rule_on_claim(rule_v1, claim) == "review"


def test_documented_failure_still_denies(engine, rule_v1):
    claim = {
        "member": {
            "age_years": 60,
            "pack_years": 40,
            "smoker_status": "former",
            "years_since_quit": 16,
        },
        "px_codes": ["G0297"],
        "sdm_visit_completed": True,
        "documentation": {"min_pack_years": 30},
    }
    assert engine.run_rule_on_claim(rule_v1, claim) == "deny"


def test_or_with_manual_review_branch(engine):
    # or(failing check, manual_review) -> review, matching fixer-style
    # "fall back to manual review" branches.
    rule = {
        "criterionId": "x",
        "policy": {"policyId": "p", "policyType": "NCD", "version": "1"},
        "outcome": "covered_with_conditions",
        "condition": {
            "op": "or",
            "of": [
                {"op": "age", "age": {"min": {"value": 55, "unit": "year"}}},
                {"op": "manual_review", "reason": "age undocumented"},
            ],
        },
    }
    claim = {"member": {"age_years": 40}}
    assert engine.run_rule_on_claim(rule, claim) == "review"


def test_json_logic_disallowed_operator(engine):
    with pytest.raises(EngineError):
        engine.eval_json_logic({"exec": ["rm", "-rf", "/"]}, {})


def test_operator_allowlist_complete():
    assert "manual_review" in OPERATOR_ALLOWLIST
    assert "age_at_dos" in OPERATOR_ALLOWLIST
