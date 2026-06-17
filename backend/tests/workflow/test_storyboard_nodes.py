from __future__ import annotations

import pytest

from leagent.workflow.nodes import bootstrap as bootstrap_nodes
from leagent.workflow.nodes import get_registry
from leagent.workflow.nodes.art.storyboard import ShotNode, StoryboardNode


@pytest.fixture(scope="module")
async def registered_nodes():
    await bootstrap_nodes()
    return get_registry()


def test_shot_schema_has_controls():
    info = ShotNode.get_schema().get_info_dict()
    optional = info["input"]["optional"]
    assert "name" in optional
    assert "image" in optional
    assert "camera" in optional
    assert "control" in optional


@pytest.mark.asyncio
async def test_storyboard_runs_offline_placeholder():
    node = StoryboardNode()
    shots = [
        {"type": "shot", "prompt": "turntable of a red cube", "duration": 2, "fps": 12},
        {"type": "shot", "prompt": "turntable of a blue cube", "duration": 2, "fps": 12},
    ]
    hidden = type("H", (), {"workflow_state": None, "session_id": None, "user_id": None, "unique_id": "sb"})()
    out = await node.execute(hidden=hidden, shots=shots, provider="offline")
    assert out.error is None
    videos, ok = out.values
    assert ok is True
    assert isinstance(videos, list) and len(videos) == 2
    assert all(isinstance(v, dict) and v.get("kind") == "video" for v in videos)

