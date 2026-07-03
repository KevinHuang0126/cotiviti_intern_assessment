#!/usr/bin/env python3
"""Validate replay determinism (fixture mode)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def transcript_hash() -> str:
    from src.diff import diff_report
    from src.fixtures_loader import load_rule, load_test_suite

    report = diff_report(
        load_rule("v1"),
        load_rule("v2"),
        load_test_suite("v1"),
        load_test_suite("v2"),
    )
    payload = json.dumps(report, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> None:
    h = transcript_hash()
    print(f"Replay transcript hash: {h}")
    golden = ROOT / "cache" / "llm" / "golden" / "transcript_hash.txt"
    golden.parent.mkdir(parents=True, exist_ok=True)
    if golden.exists():
        expected = golden.read_text().strip()
        assert h == expected, f"Hash mismatch: {h} != {expected}"
        print("Determinism OK")
    else:
        golden.write_text(h)
        print(f"Wrote golden hash to {golden}")


if __name__ == "__main__":
    main()
