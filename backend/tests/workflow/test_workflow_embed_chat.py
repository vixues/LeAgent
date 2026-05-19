"""Tests for chat-embedded workflow (Flow.data-shaped) validation."""

from __future__ import annotations

import pytest

from leagent.chat_workflow.workflow_embed import (
    WorkflowEmbedValidationError,
    build_extensions_payload,
    validate_workflow_embed,
)


@pytest.mark.asyncio
async def test_validate_workflow_embed_accepts_canonical(
    registered_builtins,
    sample_canonical_document,
) -> None:
    from leagent.workflow.nodes import get_registry

    doc, digest = validate_workflow_embed(sample_canonical_document, node_registry=get_registry())
    assert doc.start_id == "start"
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_validate_rejects_list_nodes(registered_builtins) -> None:  # noqa: ARG001
    from leagent.workflow.nodes import get_registry

    bad = {
        "id": "x",
        "nodes": [{"id": "a", "class_type": "StartNode"}],
        "control": {},
    }
    with pytest.raises(WorkflowEmbedValidationError):
        validate_workflow_embed(bad, node_registry=get_registry())


def test_build_extensions_payload_roundtrip_keys() -> None:
    fd = {"id": "1", "name": "n", "nodes": {}, "control": {"start": "s", "end": "e", "edges": []}}
    ext = build_extensions_payload(flow_data=fd, digest="a" * 64)
    assert ext["workflow_embed"]["data"] == fd
    assert ext["workflow_embed"]["digest"] == ext["workflow_embed_digest"]
