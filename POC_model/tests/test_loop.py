"""Self-critique loop convergence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.llm import get_client
from src.loop import run_compile_loop

DATA = Path(__file__).resolve().parent.parent / "data"


def test_seed_defect_loop_converges():
    client = get_client("fixture")
    text = (DATA / "coverage_section_v1.md").read_text(encoding="utf-8")
    result = run_compile_loop(
        client,
        "NCD-210.14-COVERAGE-V1",
        "CAG-00439N",
        text,
        seed_defect=True,
        save_run=False,
    )
    assert result.converged or result.stopped_reason in ("converged", "no_improvement")
    assert result.transcripts[0].failure_count > 0
