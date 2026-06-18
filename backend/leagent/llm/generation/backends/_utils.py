"""Shared helpers for generation backends."""

from __future__ import annotations

from typing import Any

from leagent.llm.generation.config import get_image_gen_config


def http_creds(name: str) -> tuple[str, str]:
    """Resolved ``(url, key)`` for an external HTTP generation backend."""
    creds = get_image_gen_config().backend_credentials(name)
    return creds.get("url", "").strip(), creds.get("key", "").strip()


def parse_size(size: Any, default: tuple[int, int] = (512, 512)) -> tuple[int, int]:
    if isinstance(size, str):
        sep = "x" if "x" in size else ("*" if "*" in size else None)
        if sep:
            try:
                w, h = size.split(sep)
                return int(w), int(h)
            except (ValueError, TypeError):
                return default
    return default


def blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Linearly interpolate two RGB colours by ``t`` in ``[0, 1]``."""
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] * (1.0 - t) + b[i] * t) for i in range(3))  # type: ignore[return-value]
