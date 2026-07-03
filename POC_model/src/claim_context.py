"""Build claim evaluation context from synthetic claim JSON."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

# Sentinel strings LLM-generated claims use to mean "this fact is not
# documented". Normalized to None so the engine routes them to manual review.
_UNDOCUMENTED = frozenset(
    {"unknown", "undocumented", "not_documented", "missing", "unclear", "n/a", "none", ""}
)


def _norm(value: Any) -> Any:
    """Collapse undocumented-sentinel strings to None."""
    if isinstance(value, str) and value.strip().lower() in _UNDOCUMENTED:
        return None
    return value


def _pick(*sources_and_keys: tuple[dict[str, Any], tuple[str, ...]]) -> Any:
    """First non-None value across (dict, keys) lookups, sentinel-normalized."""
    for source, keys in sources_and_keys:
        for key in keys:
            if key in source:
                val = _norm(source[key])
                if val is not None:
                    return val
    return None


def _to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    value = _norm(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "yes", "present", "completed", "documented"):
            return True
        if s in ("false", "no", "absent", "not_completed"):
            return False
        return None
    return bool(value)


def parse_age_years(member: dict[str, Any], claim: dict[str, Any], dos: str | None) -> float | None:
    age = _pick(
        (member, ("age_years", "age", "member_age", "memberAge", "ageYears")),
        (claim, ("age_years", "age", "member_age", "memberAge", "ageYears")),
    )
    num = _to_number(age)
    if num is not None:
        return num
    dob = member.get("dob")
    if dob and dos:
        try:
            d_dob = date.fromisoformat(str(dob)[:10])
            d_dos = date.fromisoformat(str(dos)[:10])
            return (d_dos - d_dob).days / 365.25
        except ValueError:
            return None
    return None


def normalize_smoker_status(raw: Any) -> tuple[str | None, float | None]:
    """Map free-form smoking status labels to (status, years_since_quit).

    status is one of current/former/never, or None when undocumented."""
    raw = _norm(raw)
    if raw is None:
        return None, None
    s = str(raw).strip().lower()
    if s.startswith("never"):
        return "never", None
    if s.startswith("current"):
        return "current", None
    m = re.search(r"quit(?:_smoking)?_(\d+(?:\.\d+)?)_years?_ago", s)
    if m:
        return "former", float(m.group(1))
    if s.startswith(("former", "quit", "ex")):
        return "former", None
    return None, None


def _collect_codes(claim: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    codes: list[str] = []
    for key in keys:
        val = claim.get(key)
        if not val:
            continue
        codes.extend(val if isinstance(val, list) else [val])
    return [str(c).upper() for c in codes]


def build_context(claim: dict[str, Any]) -> dict[str, Any]:
    """Pre-compute features used by the rule engine.

    Tolerates the field-name variants LLM-generated claims use (member_age,
    packYears, procedure_code, sdm_visit, counselingVisitCompleted, ...) and
    sentinel strings for undocumented facts ("not_documented", "unclear")."""
    member = claim.get("member") or {}
    dos = claim.get("dos")

    smoker_raw = _pick(
        (member, ("smoker_status", "smoking_status", "smokingStatus", "smokerStatus")),
        (claim, ("smoker_status", "smoking_status", "smokingStatus", "smokerStatus")),
    )
    smoker_status, quit_years_from_status = normalize_smoker_status(smoker_raw)
    years_since_quit = _to_number(
        _pick(
            (member, ("years_since_quit", "yearsSinceQuit")),
            (claim, ("years_since_quit", "yearsSinceQuit")),
        )
    )
    if years_since_quit is None:
        years_since_quit = quit_years_from_status

    asymptomatic_keys = ("asymptomatic", "asymptomatic_status", "symptom_free")
    if any(k in member for k in asymptomatic_keys) or any(k in claim for k in asymptomatic_keys):
        asymptomatic = _to_bool(_pick((member, asymptomatic_keys), (claim, asymptomatic_keys)))
    else:
        asymptomatic = True

    sdm_keys = (
        "sdm_visit_completed",
        "sdm_visit",
        "sdmVisit",
        "counseling_visit_completed",
        "counselingVisitCompleted",
    )
    sdm_visit = _to_bool(_pick((claim, sdm_keys), (member, sdm_keys)))
    if sdm_visit is None and not any(k in claim or k in member for k in sdm_keys):
        sdm_visit = False

    order_keys = ("written_order", "writtenOrder", "written_order_present", "writtenOrderPresent")
    written_order = _to_bool(_pick((claim, order_keys), (member, order_keys)))
    if written_order is None and not any(k in claim or k in member for k in order_keys):
        written_order = False

    ctx: dict[str, Any] = {
        "member": member,
        "dos": dos,
        "dx_codes": _collect_codes(claim, ("dx_codes", "diagnosis_codes", "diagnosis_code", "dx_code")),
        "px_codes": _collect_codes(
            claim, ("px_codes", "procedure_codes", "procedure_code", "procedureCode", "px_code")
        ),
        "modifiers": claim.get("modifiers", []),
        "pos": claim.get("pos"),
        "documentation": claim.get("documentation", {}),
        "frequency_history": claim.get("frequency_history", []),
        "age_at_dos": parse_age_years(member, claim, dos),
        "pack_years": _to_number(
            _pick(
                (member, ("pack_years", "packYears", "pack_year_history")),
                (claim, ("pack_years", "packYears", "pack_year_history")),
            )
        ),
        "smoker_status": smoker_status,
        "years_since_quit": years_since_quit,
        "asymptomatic": asymptomatic,
        "sdm_visit_completed": sdm_visit,
        "written_order": written_order,
        "synthetic": True,
        "label": "[SYNTHETIC]",
    }
    return ctx


def normalize_code(system: str, code: str) -> tuple[str, str]:
    return system.upper(), code.upper().replace(".", "")
