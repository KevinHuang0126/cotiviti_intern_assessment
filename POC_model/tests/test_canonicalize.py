"""Canonicalization idempotence and stability."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.canonicalize import canonical_hash, canonicalize_rule

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def rule_v1() -> dict:
    return json.loads((FIXTURES / "known_good_rule_v1.json").read_text())


def test_canonicalize_idempotent(rule_v1):
    once = canonicalize_rule(rule_v1)
    twice = canonicalize_rule(once)
    assert once == twice


def test_canonical_hash_stable(rule_v1):
    h1 = canonical_hash(rule_v1)
    h2 = canonical_hash(canonicalize_rule(rule_v1))
    assert h1 == h2
