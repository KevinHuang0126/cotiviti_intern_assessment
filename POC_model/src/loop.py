"""Compile → Adversary → Fixer loop driver."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from src.adversary import generate_test_suite
from src.canonicalize import canonical_hash
from src.compiler import compile_rule, seed_defective_rule
from src.engine import RuleEngine
from src.fixer import patch_rule
from src.llm import LLMClient

MAX_ROUNDS = 5
ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"


@dataclass
class RoundTranscript:
    round_num: int
    rule_hash: str
    failure_count: int
    failures: list[dict[str, Any]] = field(default_factory=list)
    fixer_changelog: list[dict[str, Any]] = field(default_factory=list)
    fixer_unresolved: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class LoopResult:
    rule: dict[str, Any]
    test_suite: dict[str, Any]
    transcripts: list[RoundTranscript]
    converged: bool
    stopped_reason: str
    run_dir: Path | None = None


def run_compile_loop(
    client: LLMClient,
    section_id: str,
    policy_version: str,
    policy_text: str,
    *,
    seed_defect: bool = False,
    save_run: bool = True,
) -> LoopResult:
    engine = RuleEngine()
    rule = compile_rule(client, section_id, policy_version, policy_text, validate_cites=False)

    if seed_defect:
        rule = seed_defective_rule(rule)

    transcripts: list[RoundTranscript] = []
    hash_history: list[str] = []
    prev_failure_count: int | None = None
    stopped_reason = "max_rounds"
    converged = False
    suite: dict[str, Any] = {"claims": []}

    for round_num in range(1, MAX_ROUNDS + 1):
        suite = generate_test_suite(client, section_id, policy_text, rule)
        failures = engine.run_suite(rule, suite)
        rule_hash = canonical_hash(rule)
        hash_history.append(rule_hash)

        transcript = RoundTranscript(
            round_num=round_num,
            rule_hash=rule_hash,
            failure_count=len(failures),
            failures=failures,
        )
        transcripts.append(transcript)

        if not failures:
            converged = True
            stopped_reason = "converged"
            break

        if _detect_cycle(hash_history):
            stopped_reason = "oscillation"
            rule = _earlier_on_cycle(rule, hash_history, transcripts)
            break

        if prev_failure_count is not None and len(failures) >= prev_failure_count:
            stopped_reason = "no_improvement"
            break
        prev_failure_count = len(failures)

        rule, meta = patch_rule(client, policy_text, rule, failures)
        transcript.fixer_changelog = meta.get("changelog", [])
        transcript.fixer_unresolved = meta.get("unresolved", [])

    result = LoopResult(
        rule=rule,
        test_suite=suite,
        transcripts=transcripts,
        converged=converged,
        stopped_reason=stopped_reason,
    )

    if save_run:
        result.run_dir = _persist_run(section_id, policy_version, result)

    return result


def run_compile_loop_streaming(
    client: LLMClient,
    section_id: str,
    policy_version: str,
    policy_text: str,
    *,
    seed_defect: bool = False,
) -> Iterator[tuple[str, Any]]:
    """Yield (event_type, payload) for Gradio streaming."""
    import time

    yield ("status", "Compiling initial rule...")
    time.sleep(0.05)

    result = run_compile_loop(
        client,
        section_id,
        policy_version,
        policy_text,
        seed_defect=seed_defect,
        save_run=True,
    )

    for t in result.transcripts:
        yield (
            "round",
            {
                "round": t.round_num,
                "failures": t.failures,
                "failure_count": t.failure_count,
                "rule_hash": t.rule_hash,
                "changelog": t.fixer_changelog,
            },
        )
        time.sleep(0.02)

    yield (
        "done",
        {
            "rule": result.rule,
            "converged": result.converged,
            "stopped_reason": result.stopped_reason,
            "transcripts": result.transcripts,
            "test_suite": result.test_suite,
        },
    )


def _detect_cycle(hashes: list[str]) -> bool:
    if len(hashes) < 3:
        return False
    return hashes[-1] == hashes[-3]


def _earlier_on_cycle(
    current_rule: dict[str, Any],
    hashes: list[str],
    transcripts: list[RoundTranscript],
) -> dict[str, Any]:
    return current_rule


def _persist_run(section_id: str, policy_version: str, result: LoopResult) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    run_dir = RUNS_DIR / f"{ts}_{section_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "rule.json").write_text(json.dumps(result.rule, indent=2), encoding="utf-8")
    (run_dir / "test_suite.json").write_text(
        json.dumps(result.test_suite, indent=2), encoding="utf-8"
    )
    (run_dir / "transcript.json").write_text(
        json.dumps(
            [
                {
                    "round": t.round_num,
                    "rule_hash": t.rule_hash,
                    "failure_count": t.failure_count,
                    "failures": t.failures,
                    "changelog": t.fixer_changelog,
                }
                for t in result.transcripts
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    return run_dir
