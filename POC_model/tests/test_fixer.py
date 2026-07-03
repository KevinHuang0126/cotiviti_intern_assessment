"""Tests for fixer output normalization."""

from __future__ import annotations

from src.fixer import _normalize_entries


def test_normalize_entries_wraps_strings():
    assert _normalize_entries(["raised age min to 50"]) == [{"change": "raised age min to 50"}]
    assert _normalize_entries(["policy silent"], key="issue") == [{"issue": "policy silent"}]


def test_normalize_entries_passes_dicts_through():
    entries = [{"change": "x", "reason": "y"}]
    assert _normalize_entries(entries) == entries


def test_normalize_entries_handles_junk():
    assert _normalize_entries("not a list") == []
    assert _normalize_entries([42]) == [{"change": "42"}]
