"""Tests for src.utils."""

from __future__ import annotations

from src.utils import greet


def test_greet_returns_name() -> None:
    assert greet("World") == "Hello, World!"


def test_greet_empty_string() -> None:
    assert greet("") == "Hello, !"
