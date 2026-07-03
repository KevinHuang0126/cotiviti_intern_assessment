#!/usr/bin/env python3
"""Pre-flight checks before demo recording."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    print("Running tests...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        return result.returncode

    print("Validating fixture replay path...")
    from src.diff import diff_report
    from src.fixtures_loader import load_rule, load_test_suite

    report = diff_report(
        load_rule("v1"),
        load_rule("v2"),
        load_test_suite("v1"),
        load_test_suite("v2"),
    )
    assert report["modified_count"] == 3
    print(f"OK: {report['modified_count']} modified leaves, {len(report['flipped_claims'])} flipped claims")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
