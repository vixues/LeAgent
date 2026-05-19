"""Shared fixtures for workflow tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_registry():
    """Give every test a fresh node registry so side-effects don't leak."""
    from leagent.workflow.nodes.registry import reset_registry
    reset_registry()
    yield
    reset_registry()


@pytest.fixture
async def registered_builtins():
    from leagent.workflow.nodes import bootstrap
    await bootstrap()


@pytest.fixture
def sample_canonical_document() -> dict:
    """Canonical workflow document used by multiple tests."""
    return {
        "id": "tst",
        "name": "test flow",
        "description": "",
        "inputs": [],
        "outputs": [],
        "metadata": {},
        "nodes": {
            "start": {
                "class_type": "StartNode",
                "inputs": {},
                "meta": {},
                "control": {"next": "xform"},
            },
            "xform": {
                "class_type": "TransformNode",
                "inputs": {"transform": {"name": "hello"}},
                "meta": {},
                "control": {"next": "end"},
            },
            "end": {
                "class_type": "EndNode",
                "inputs": {"result": "done"},
                "meta": {},
                "control": {},
            },
        },
        "control": {
            "start": "start",
            "end": "end",
            "edges": [],
            "timeout_sec": 3600,
            "max_retries": 3,
            "tags": [],
        },
    }
