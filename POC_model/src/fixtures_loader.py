"""Load golden fixtures for offline demo without LLM calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures"


def load_rule(version: str) -> dict[str, Any]:
    path = FIXTURES_DIR / f"known_good_rule_{version}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_test_suite(version: str) -> dict[str, Any]:
    path = FIXTURES_DIR / f"test_suite_{version}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return _default_test_suite(version)


def get_fixture_response(role: str, user: str, tool_name: str) -> dict[str, Any]:
    if role == "compiler":
        if "V2" in user or "2022" in user or "v2" in user.lower():
            return load_rule("v2")
        return load_rule("v1")
    if role == "adversary":
        if "V2" in user or "2022" in user:
            return load_test_suite("v2")
        return load_test_suite("v1")
    if role == "fixer":
        if "age ≥ 50" in user or "age min 50" in user.lower() or "deliberately" in user.lower():
            return {
                "patched_rule": load_rule("v1"),
                "changelog": [
                    {
                        "test_id": "age-boundary-under",
                        "change": "Restored age.min to 55 per policy span '55 – 77 years'",
                        "cite": {"quote": "55 – 77 years"},
                        "rationale": "Policy requires age 55-77, not 50",
                    }
                ],
                "unresolved": [],
            }
        return {"patched_rule": load_rule("v1"), "changelog": [], "unresolved": []}
    raise KeyError(f"No fixture for role={role}")


def _default_test_suite(version: str) -> dict[str, Any]:
    rule = load_rule(version)
    age_min = 55 if version == "v1" else 50
    pack_min = 30 if version == "v1" else 20
    ldct = "G0297" if version == "v1" else "71271"

    return {
        "claims": [
            {
                "id": "headline-flip-patient",
                "claim": {
                    "member": {
                        "age_years": 52,
                        "sex": "F",
                        "pack_years": 22,
                        "smoker_status": "former",
                        "years_since_quit": 8,
                        "asymptomatic": True,
                    },
                    "dos": "2026-01-15",
                    "px_codes": [ldct],
                    "sdm_visit_completed": True,
                    "written_order": True,
                    "documentation": {"min_pack_years": pack_min},
                },
                "probes": ["age_boundary", "pack_years"],
                "predicted_decision": "approve" if version == "v2" else "deny",
                "rationale": f"52yo with 22 pack-years fails v1 thresholds ({age_min}/{pack_min})",
                "policy_cites": [{"quote": f"at least {pack_min} pack-years"}],
            },
            {
                "id": "age-boundary-under",
                "claim": {
                    "member": {"age_years": age_min - 1, "pack_years": 40, "smoker_status": "current"},
                    "px_codes": [ldct],
                    "sdm_visit_completed": True,
                    "documentation": {"min_pack_years": pack_min},
                },
                "probes": ["age_boundary"],
                "predicted_decision": "deny",
                "rationale": "Just under age minimum",
                "policy_cites": [{"quote": "55 – 77 years" if version == "v1" else "Age 50 - 77 years"}],
            },
            {
                "id": "age-boundary-at-min",
                "claim": {
                    "member": {"age_years": age_min, "pack_years": 40, "smoker_status": "current"},
                    "px_codes": [ldct],
                    "sdm_visit_completed": True,
                    "documentation": {"min_pack_years": pack_min},
                },
                "probes": ["age_boundary"],
                "predicted_decision": "approve",
                "rationale": "Exactly at age minimum with all other criteria met",
                "policy_cites": [{"quote": "55 – 77 years" if version == "v1" else "Age 50 - 77 years"}],
            },
            {
                "id": "pack-years-under",
                "claim": {
                    "member": {"age_years": 60, "pack_years": pack_min - 1, "smoker_status": "current"},
                    "px_codes": [ldct],
                    "sdm_visit_completed": True,
                    "documentation": {"min_pack_years": pack_min},
                },
                "probes": ["pack_years"],
                "predicted_decision": "deny",
                "rationale": "Just under pack-year threshold",
                "policy_cites": [{"quote": f"at least {pack_min} pack-years"}],
            },
            {
                "id": "missing-sdm",
                "claim": {
                    "member": {"age_years": 60, "pack_years": 40, "smoker_status": "current"},
                    "px_codes": [ldct],
                    "sdm_visit_completed": False,
                    "documentation": {"min_pack_years": pack_min},
                },
                "probes": ["missing_documentation"],
                "predicted_decision": "deny",
                "rationale": "SDM visit required before first screening",
                "policy_cites": [{"quote": "G0296"}],
            },
            {
                "id": "quit-too-long-ago",
                "claim": {
                    "member": {
                        "age_years": 60,
                        "pack_years": 40,
                        "smoker_status": "former",
                        "years_since_quit": 16,
                    },
                    "px_codes": [ldct],
                    "sdm_visit_completed": True,
                    "documentation": {"min_pack_years": pack_min},
                },
                "probes": ["smoker_status"],
                "predicted_decision": "deny",
                "rationale": "Former smoker quit more than 15 years ago",
                "policy_cites": [{"quote": "quit smoking within the last 15 years"}],
            },
            {
                "id": "wrong-ldct-code",
                "claim": {
                    "member": {"age_years": 60, "pack_years": 40, "smoker_status": "current"},
                    "px_codes": ["99999"],
                    "sdm_visit_completed": True,
                    "documentation": {"min_pack_years": pack_min},
                },
                "probes": ["code_boundary"],
                "predicted_decision": "deny",
                "rationale": "Procedure code not in covered set",
                "policy_cites": [{"quote": ldct}],
            },
            {
                "id": "valid-full-claim",
                "claim": {
                    "member": {"age_years": 65, "pack_years": 35, "smoker_status": "current"},
                    "px_codes": [ldct],
                    "sdm_visit_completed": True,
                    "written_order": True,
                    "documentation": {"min_pack_years": pack_min},
                },
                "probes": ["happy_path"],
                "predicted_decision": "approve",
                "rationale": "Meets all criteria",
                "policy_cites": [{"quote": f"at least {pack_min} pack-years"}],
            },
        ]
    }
