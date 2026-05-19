"""Extension hooks every :class:`WorkflowNode` may override.

Modelled after the reference ``_io.py`` node contract hooks
(``IS_CHANGED`` / ``check_lazy_status``). Keeping them in the ``io``
package means the runner can import them without pulling in the engine.

* :func:`default_fingerprint_inputs` produces a stable, content-based
  cache-key suffix from the resolved input payload. Nodes that need to
  bypass caching when external state changes (e.g. file mtime, API
  response) override :meth:`WorkflowNode.fingerprint_inputs` and return
  the :data:`NOT_CACHEABLE` sentinel or a volatile token.

* :func:`default_check_lazy_status` is consulted before executing a node
  that declares lazy inputs. It returns the list of input ids the runner
  must still resolve; an empty list means "I have everything I need".
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class _NotCacheableSentinel:
    """Sentinel returned by ``fingerprint_inputs`` to bypass caching."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "NOT_CACHEABLE"


NOT_CACHEABLE: _NotCacheableSentinel = _NotCacheableSentinel()
"""Return value telling the runner to skip cache lookup + insertion."""


def default_fingerprint_inputs(node: Any, /, **kwargs: Any) -> str:
    """Default fingerprint: SHA-256 of the JSON-stable kwargs dict."""
    try:
        payload = json.dumps(kwargs, sort_keys=True, default=_default_encode)
    except (TypeError, ValueError):
        payload = repr(sorted(kwargs.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def default_check_lazy_status(node: Any, /, **kwargs: Any) -> list[str]:
    """Default: no lazy inputs — everything should be resolved."""
    return []


def _default_encode(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return repr(value)


class Contract:
    """Namespace exposing the contract hook sentinels + defaults."""

    NOT_CACHEABLE = NOT_CACHEABLE
    default_fingerprint_inputs = staticmethod(default_fingerprint_inputs)
    default_check_lazy_status = staticmethod(default_check_lazy_status)
