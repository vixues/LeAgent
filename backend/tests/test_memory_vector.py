from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from leagent.memory.vector import MilvusCollection, MilvusConnectionConfig


@pytest.mark.asyncio
async def test_milvus_collection_suppresses_retry_during_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"connect": 0, "upsert": 0}

    class _Connections:
        def has_connection(self, alias: str) -> bool:  # noqa: ARG002
            return attempts["connect"] > 1

        def connect(self, **kwargs: object) -> None:  # noqa: ARG002
            attempts["connect"] += 1
            if attempts["connect"] == 1:
                raise RuntimeError("milvus unavailable")

    class _Collection:
        def __init__(self, **kwargs: object) -> None:  # noqa: ARG002
            pass

        def create_index(self, **kwargs: object) -> None:  # noqa: ARG002
            return None

        def load(self) -> None:
            return None

        def upsert(self, rows: list[list[object]]) -> None:  # noqa: ARG002
            attempts["upsert"] += 1

    pymilvus = SimpleNamespace(
        Collection=_Collection,
        CollectionSchema=lambda **kwargs: kwargs,
        DataType=SimpleNamespace(VARCHAR="varchar", FLOAT_VECTOR="float_vector"),
        FieldSchema=lambda **kwargs: kwargs,
        connections=_Connections(),
        utility=SimpleNamespace(has_collection=lambda *args, **kwargs: False),
    )
    monkeypatch.setitem(sys.modules, "pymilvus", pymilvus)

    collection = MilvusCollection(
        name="agent_memory_test",
        dimension=8,
        connection=MilvusConnectionConfig(
            host="milvus",
            port=19530,
            enabled=True,
            retry_interval_seconds=60,
        ),
    )

    failed = await collection.upsert(row_id="1", vector=[0.0] * 8)
    assert failed.written is False
    assert failed.degraded is True

    suppressed = await collection.upsert(row_id="1", vector=[0.0] * 8)
    assert suppressed.written is False
    assert attempts == {"connect": 1, "upsert": 0}

    collection._next_retry_at = 0.0  # noqa: SLF001 - exercise recovery window
    recovered = await collection.upsert(row_id="1", vector=[0.0] * 8)
    assert recovered.written is True
    assert attempts == {"connect": 2, "upsert": 1}


@pytest.mark.asyncio
async def test_milvus_collection_optional_off_never_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"connect": 0}

    class _Connections:
        def has_connection(self, alias: str) -> bool:  # noqa: ARG002
            return False

        def connect(self, **kwargs: object) -> None:  # noqa: ARG002
            attempts["connect"] += 1

    pymilvus = SimpleNamespace(
        connections=_Connections(),
    )
    monkeypatch.setitem(sys.modules, "pymilvus", pymilvus)

    collection = MilvusCollection(
        name="agent_memory_test",
        dimension=8,
        connection=MilvusConnectionConfig(enabled=False),
    )

    result = await collection.upsert(row_id="1", vector=[0.0] * 8)
    assert result.written is False
    assert result.error == "milvus_optional_off"
    assert await collection.search(vector=[0.0] * 8, limit=1) == []
    assert attempts == {"connect": 0}
