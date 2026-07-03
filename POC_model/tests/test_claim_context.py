"""Tests for claim context normalization of LLM-generated claim shapes."""

from __future__ import annotations

from src.claim_context import build_context, normalize_smoker_status


def test_canonical_claim_shape_unchanged():
    ctx = build_context(
        {
            "member": {
                "age_years": 52,
                "pack_years": 22,
                "smoker_status": "former",
                "years_since_quit": 8,
            },
            "px_codes": ["g0297"],
            "sdm_visit_completed": True,
            "documentation": {"min_pack_years": 30},
        }
    )
    assert ctx["age_at_dos"] == 52
    assert ctx["pack_years"] == 22
    assert ctx["smoker_status"] == "former"
    assert ctx["years_since_quit"] == 8
    assert ctx["px_codes"] == ["G0297"]
    assert ctx["sdm_visit_completed"] is True


def test_flat_snake_case_aliases():
    ctx = build_context(
        {
            "member_id": "SYN-M004",
            "member_age": 65,
            "pack_years": 30.0,
            "smoking_status": "current_smoker",
            "asymptomatic": True,
            "sdm_visit": True,
            "written_order": True,
            "procedure_code": "G0297",
        }
    )
    assert ctx["age_at_dos"] == 65
    assert ctx["pack_years"] == 30.0
    assert ctx["smoker_status"] == "current"
    assert ctx["px_codes"] == ["G0297"]
    assert ctx["sdm_visit_completed"] is True
    assert ctx["written_order"] is True


def test_flat_camel_case_aliases():
    ctx = build_context(
        {
            "memberId": "SYN-2024-010",
            "age": 55,
            "packYears": 30,
            "smokingStatus": "current_smoker",
            "asymptomatic": True,
            "counselingVisitCompleted": True,
            "writtenOrderPresent": True,
            "procedureCode": "G0297",
        }
    )
    assert ctx["age_at_dos"] == 55
    assert ctx["pack_years"] == 30
    assert ctx["smoker_status"] == "current"
    assert ctx["px_codes"] == ["G0297"]
    assert ctx["sdm_visit_completed"] is True
    assert ctx["written_order"] is True


def test_undocumented_sentinels_become_none():
    ctx = build_context(
        {
            "member_age": 72,
            "pack_years": "not_documented",
            "smoking_status": "undocumented",
            "asymptomatic": "unclear",
            "sdm_visit": True,
            "written_order": "unclear",
            "procedure_code": "G0297",
        }
    )
    assert ctx["pack_years"] is None
    assert ctx["smoker_status"] is None
    assert ctx["asymptomatic"] is None
    assert ctx["written_order"] is None


def test_quit_n_years_ago_status():
    assert normalize_smoker_status("quit_15_years_ago") == ("former", 15.0)
    assert normalize_smoker_status("quit_smoking_16_years_ago") == ("former", 16.0)
    assert normalize_smoker_status("current_smoker") == ("current", None)
    assert normalize_smoker_status("never_smoker") == ("never", None)
    assert normalize_smoker_status("not_documented") == (None, None)


def test_absent_fields_keep_legacy_defaults():
    ctx = build_context({"member": {"age_years": 60}})
    # Absent asymptomatic defaults True; absent sdm/order default False.
    assert ctx["asymptomatic"] is True
    assert ctx["sdm_visit_completed"] is False
    assert ctx["written_order"] is False
