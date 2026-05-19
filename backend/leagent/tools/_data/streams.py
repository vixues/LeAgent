"""Chunked iteration helpers.

These are pure, stateless generators. Tools use them to stream work
over big inputs so (1) progress can be reported at sub-dataset
granularity and (2) memory use stays bounded when operating on data
already loaded from an artifact.
"""

from __future__ import annotations

from typing import Any, Iterator, Sequence

__all__ = ["iter_chunks", "iter_chunks_df"]


def iter_chunks(
    items: Sequence[Any] | Iterator[Any],
    chunk_size: int = 5_000,
) -> Iterator[list[Any]]:
    """Yield lists of up to ``chunk_size`` items from ``items``.

    Accepts either a sized sequence or an arbitrary iterator.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if isinstance(items, list):
        for start in range(0, len(items), chunk_size):
            yield items[start:start + chunk_size]
        return

    buffer: list[Any] = []
    for item in items:
        buffer.append(item)
        if len(buffer) >= chunk_size:
            yield buffer
            buffer = []
    if buffer:
        yield buffer


def iter_chunks_df(df: Any, chunk_size: int = 5_000) -> Iterator[Any]:
    """Yield DataFrame slices of at most ``chunk_size`` rows.

    ``df`` is duck-typed to avoid a hard pandas import.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    total = len(df)
    for start in range(0, total, chunk_size):
        yield df.iloc[start:start + chunk_size]
