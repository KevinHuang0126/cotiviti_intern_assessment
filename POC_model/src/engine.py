"""Hand-rolled JSON Logic executor + condition-tree evaluator."""

from __future__ import annotations

import re
from typing import Any

from src.claim_context import build_context, normalize_code
from src.schema import OPERATOR_ALLOWLIST

Decision = str  # approve | deny | review


class EngineError(Exception):
    pass


class RuleEngine:
    """Evaluates coverage rules against synthetic claims."""

    TIMEOUT_SECONDS = 1.0

    def __init__(self) -> None:
        self._json_logic_ops = self._build_json_logic_ops()

    def run_rule_on_claim(self, rule: dict[str, Any], claim: dict[str, Any]) -> Decision:
        ctx = build_context(claim)
        condition = rule.get("condition", {})
        result = self._eval_condition(condition, ctx)
        if result == "manual_review":
            return "review"
        if result is False:
            return "deny"
        if result is True:
            return self._outcome_to_decision(rule.get("outcome", "covered"))
        return "review"

    def run_suite(
        self, rule: dict[str, Any], suite: dict[str, Any]
    ) -> list[dict[str, Any]]:
        failures: list[dict[str, Any]] = []
        for test in suite.get("claims", []):
            actual = self.run_rule_on_claim(rule, test["claim"])
            predicted = test.get("predicted_decision", "review")
            if actual != predicted:
                failures.append(
                    {
                        "test_id": test["id"],
                        "claim": test["claim"],
                        "predicted_decision": predicted,
                        "actual_decision": actual,
                        "rationale": test.get("rationale", ""),
                        "policy_cites": test.get("policy_cites", []),
                        "probes": test.get("probes", []),
                    }
                )
        return failures

    def eval_json_logic(self, logic: Any, data: dict[str, Any]) -> Any:
        if logic is None:
            return None
        if not isinstance(logic, dict):
            return logic
        if len(logic) != 1:
            raise EngineError(f"Invalid JSON Logic node: {logic}")
        op, args = next(iter(logic.items()))
        if op not in OPERATOR_ALLOWLIST:
            raise EngineError(f"Operator not allowed: {op}")
        return self._json_logic_ops[op](args, data)

    def _outcome_to_decision(self, outcome: str) -> Decision:
        if outcome in ("covered", "covered_with_conditions"):
            return "approve"
        if outcome == "not_covered":
            return "deny"
        return "review"

    def _eval_condition(self, node: dict[str, Any], ctx: dict[str, Any]) -> Any:
        op = node.get("op")
        # Tri-state logic: children may return True / False / "manual_review".
        # manual_review must propagate (not collapse to deny) so that claims
        # with undocumented facts surface as review decisions.
        if op == "and":
            results = [self._eval_condition(c, ctx) for c in node.get("of", [])]
            if any(r is False for r in results):
                return False
            if any(r == "manual_review" for r in results):
                return "manual_review"
            return True
        if op == "or":
            results = [self._eval_condition(c, ctx) for c in node.get("of", [])]
            if any(r is True for r in results):
                return True
            if any(r == "manual_review" for r in results):
                return "manual_review"
            return False
        if op == "not":
            child = node.get("of", {})
            val = self._eval_condition(child, ctx)
            if val == "manual_review":
                return "manual_review"
            return val is not True
        if op == "manual_review":
            return "manual_review"
        if op == "age":
            return self._eval_age(node.get("age", {}), ctx)
        if op == "code_set":
            return self._eval_code_set(node.get("codeSet", {}), ctx)
        if op == "documentation":
            return self._eval_documentation(node.get("documentation", {}), ctx)
        raise EngineError(f"Unknown condition op: {op}")

    def _eval_age(self, age_spec: dict[str, Any], ctx: dict[str, Any]) -> Any:
        age = ctx.get("age_at_dos")
        if age is None:
            return "manual_review"
        min_q = age_spec.get("min")
        max_q = age_spec.get("max")
        if min_q and age < min_q["value"]:
            return False
        if max_q and age > max_q["value"]:
            return False
        return True

    def _eval_code_set(self, code_set: dict[str, Any], ctx: dict[str, Any]) -> bool:
        kind = code_set.get("kind", "procedure_covered")
        codes = code_set.get("codes", [])
        normalized = {normalize_code(c["system"], c["code"]) for c in codes}

        if kind == "procedure_covered":
            px = ctx.get("px_codes", [])
            for px_code in px:
                for sys in ("HCPCS", "CPT"):
                    if (sys, px_code.upper()) in normalized:
                        return True
            return False
        if kind == "diagnosis_required":
            dx = ctx.get("dx_codes", [])
            return any(("ICD10", d) in normalized or ("ICD10CM", d) in normalized for d in dx)
        return True

    def _eval_documentation(self, doc: dict[str, Any], ctx: dict[str, Any]) -> Any:
        """Tri-state: True (documented, satisfied), False (documented, not
        satisfied), "manual_review" (fact undocumented on the claim).

        Doc ids come from the LLM compiler and vary between runs
        ("pack-years", "pack-years-history", "smoking-status",
        "sdm-visit-order", ...), so dispatch on keywords, not exact ids."""
        doc_id = (doc.get("id") or "").lower()
        documentation = ctx.get("documentation", {})

        if "pack" in doc_id:
            pack_years = ctx.get("pack_years")
            if pack_years is None:
                pack_years = documentation.get("pack_years")
            min_pack = documentation.get("min_pack_years")
            if min_pack is None:
                m = re.search(r"at least (\d+(?:\.\d+)?)\s*pack", doc.get("text", "").lower())
                if m:
                    min_pack = float(m.group(1))
            if pack_years is None or min_pack is None:
                return "manual_review"
            return float(pack_years) >= float(min_pack)

        if "smok" in doc_id:
            status = ctx.get("smoker_status") or documentation.get("smoker_status")
            years_quit = ctx.get("years_since_quit")
            if years_quit is None:
                years_quit = documentation.get("years_since_quit")
            if status is None:
                return "manual_review"
            if status == "current":
                return True
            if status == "former":
                if years_quit is None:
                    return "manual_review"
                return float(years_quit) <= 15
            return False

        if "asymptomatic" in doc_id or "symptom" in doc_id:
            val = ctx.get("asymptomatic", True)
            if val is None:
                return "manual_review"
            return bool(val)

        if any(k in doc_id for k in ("sdm", "counsel", "visit", "order", "written")):
            checks: list[Any] = []
            if any(k in doc_id for k in ("sdm", "counsel", "visit")):
                v = ctx.get("sdm_visit_completed")
                if v is None:
                    v = documentation.get("sdm_visit")
                checks.append(v)
            if any(k in doc_id for k in ("order", "written")):
                v = ctx.get("written_order")
                if v is None:
                    v = documentation.get("written_order")
                checks.append(v)
            if any(c is False for c in checks):
                return False
            if any(c is None for c in checks):
                return "manual_review"
            return all(bool(c) for c in checks)

        if doc_id in documentation:
            return bool(documentation[doc_id])
        if doc.get("required"):
            return "manual_review"
        return True

    def _build_json_logic_ops(self) -> dict[str, Any]:
        def apply_binary(op: str, args: Any, data: dict[str, Any]) -> bool:
            if not isinstance(args, list) or len(args) != 2:
                raise EngineError(f"{op} requires two args")
            left = self._resolve(args[0], data)
            right = self._resolve(args[1], data)
            return {
                "==": lambda a, b: a == b,
                "!=": lambda a, b: a != b,
                "<": lambda a, b: a < b,
                "<=": lambda a, b: a <= b,
                ">": lambda a, b: a > b,
                ">=": lambda a, b: a >= b,
            }[op](left, right)

        return {
            "and": lambda args, data: all(
                self.eval_json_logic(a, data) for a in (args if isinstance(args, list) else [args])
            ),
            "or": lambda args, data: any(
                self.eval_json_logic(a, data) for a in (args if isinstance(args, list) else [args])
            ),
            "!": lambda args, data: not self.eval_json_logic(
                args[0] if isinstance(args, list) else args, data
            ),
            "==": lambda args, data: apply_binary("==", args, data),
            "!=": lambda args, data: apply_binary("!=", args, data),
            "<": lambda args, data: apply_binary("<", args, data),
            "<=": lambda args, data: apply_binary("<=", args, data),
            ">": lambda args, data: apply_binary(">", args, data),
            ">=": lambda args, data: apply_binary(">=", args, data),
            "in": lambda args, data: self._resolve(args[0], data)
            in self._resolve(args[1], data),
            "manual_review": lambda args, data: "manual_review",
            "code_in_set": lambda args, data: self._op_code_in_set(args, data),
            "age_at_dos": lambda args, data: self._op_age_at_dos(args, data),
            "frequency_in_window": lambda args, data: self._op_frequency(args, data),
        }

    def _resolve(self, arg: Any, data: dict[str, Any]) -> Any:
        if isinstance(arg, dict) and "var" in arg:
            path = arg["var"]
            if isinstance(path, list):
                cur: Any = data
                for key in path:
                    cur = cur[key] if isinstance(cur, dict) else None
                return cur
            return data.get(path)
        if isinstance(arg, dict):
            return self.eval_json_logic(arg, data)
        return arg

    def _op_code_in_set(self, args: Any, data: dict[str, Any]) -> bool:
        if not isinstance(args, list) or len(args) < 2:
            return False
        field = args[0]
        code_list = args[1]
        values = self._resolve({"var": field}, data) if isinstance(field, str) else field
        if not isinstance(values, list):
            values = [values]
        targets = {str(c).upper() for c in code_list}
        return any(str(v).upper() in targets for v in values)

    def _op_age_at_dos(self, args: Any, data: dict[str, Any]) -> float | None:
        return data.get("age_at_dos")

    def _op_frequency(self, args: Any, data: dict[str, Any]) -> bool:
        if not isinstance(args, list) or len(args) < 2:
            return False
        max_count = args[0]
        window_days = args[1]
        history = data.get("frequency_history", [])
        if not history:
            return int(max_count) >= 1
        recent = [h for h in history if h.get("days_ago", 9999) <= window_days]
        return len(recent) <= int(max_count)
