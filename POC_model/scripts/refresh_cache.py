#!/usr/bin/env python3
"""Refresh LLM cache from live API (requires ANTHROPIC_API_KEY)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.llm import get_client
from src.loop import run_compile_loop

DATA = ROOT / "data"


def main() -> None:
    client = get_client("live")
    for version, section_file, section_id, policy_version in (
        ("v1", "coverage_section_v1.md", "NCD-210.14-COVERAGE-V1", "CAG-00439N"),
        ("v2", "coverage_section_v2.md", "NCD-210.14-COVERAGE-V2", "CAG-00439R"),
    ):
        text = (DATA / section_file).read_text(encoding="utf-8")
        print(f"Compiling {version}...")
        run_compile_loop(client, section_id, policy_version, text, save_run=True)
    print("Cache refreshed under cache/llm/")


if __name__ == "__main__":
    main()
