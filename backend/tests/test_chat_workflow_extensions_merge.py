"""Both a DAG embed and a step card emitted in one turn must coexist in
``Message.extensions`` (otherwise the DAG would disappear on reload)."""

from __future__ import annotations

import json

from leagent.api.v1.chat import _accumulate_workflow_extensions

_FLOW = {
    "id": "x",
    "name": "x",
    "nodes": {},
    "control": {"start": "s", "end": "e", "edges": []},
}
_SPEC = {"version": 1, "title": "Card", "steps": []}


def test_embed_then_spec_keeps_both() -> None:
    after_embed = _accumulate_workflow_extensions(
        None, {"embed": {"data": _FLOW, "digest": "a" * 64}}
    )
    after_spec = _accumulate_workflow_extensions(
        after_embed, {"spec": _SPEC, "digest": "b" * 64}
    )
    merged = json.loads(after_spec or "{}")
    assert merged["workflow_embed"]["data"] == _FLOW
    assert merged["workflow_embed_digest"] == "a" * 64
    assert merged["chat_workflow"] == _SPEC
    assert merged["chat_workflow_digest"] == "b" * 64


def test_spec_then_embed_keeps_both() -> None:
    after_spec = _accumulate_workflow_extensions(
        None, {"spec": _SPEC, "digest": "b" * 64}
    )
    after_embed = _accumulate_workflow_extensions(
        after_spec, {"embed": {"data": _FLOW, "digest": "a" * 64}}
    )
    merged = json.loads(after_embed or "{}")
    assert merged["chat_workflow"] == _SPEC
    assert merged["workflow_embed"]["data"] == _FLOW


def test_unrelated_payload_is_passthrough() -> None:
    existing = json.dumps({"chat_workflow": _SPEC})
    out = _accumulate_workflow_extensions(existing, {"foo": "bar"})
    assert out == existing
