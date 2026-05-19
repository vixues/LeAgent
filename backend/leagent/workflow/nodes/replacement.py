"""Node replacement registry — deprecation/rename mapping applied at prompt-submit.

Each entry maps ``(old_class_type, optional_scope) -> new_class_type`` and
an optional ``input_transform`` callable that rewrites the node's ``inputs``
dict. The server's ``prompt_hooks`` apply the replacements before validation
so authors of old workflow JSON don't have to migrate manually.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


InputTransform = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class NodeReplacement:
    old_class: str
    new_class: str
    reason: str = ""
    input_transform: Optional[InputTransform] = None
    applies_to_users: tuple[str, ...] = field(default_factory=tuple)

    def applies_to(self, user_id: str | None) -> bool:
        if not self.applies_to_users:
            return True
        return user_id in self.applies_to_users


class NodeReplaceRegistry:
    """Thread-safe registry of ``NodeReplacement`` entries."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_old: dict[str, list[NodeReplacement]] = {}

    def register(self, replacement: NodeReplacement) -> None:
        with self._lock:
            self._by_old.setdefault(replacement.old_class, []).append(replacement)

    def unregister(self, old_class: str, new_class: str | None = None) -> int:
        removed = 0
        with self._lock:
            entries = self._by_old.get(old_class, [])
            if new_class is None:
                removed = len(entries)
                self._by_old.pop(old_class, None)
            else:
                kept = [e for e in entries if e.new_class != new_class]
                removed = len(entries) - len(kept)
                if kept:
                    self._by_old[old_class] = kept
                else:
                    self._by_old.pop(old_class, None)
        return removed

    def list_all(self) -> list[NodeReplacement]:
        with self._lock:
            out: list[NodeReplacement] = []
            for entries in self._by_old.values():
                out.extend(entries)
            return out

    def apply_to_document(
        self,
        doc: dict[str, Any],
        *,
        user_id: str | None = None,
    ) -> tuple[dict[str, Any], list[tuple[str, str, str]]]:
        """Apply replacements to a v2 workflow document. Returns the mutated
        document and a changelog of ``(node_id, old_class, new_class)``."""
        changes: list[tuple[str, str, str]] = []
        nodes = doc.get("nodes", {}) or {}
        with self._lock:
            for node_id, node_def in list(nodes.items()):
                old_class = node_def.get("class_type")
                if not old_class:
                    continue
                for entry in self._by_old.get(old_class, []):
                    if not entry.applies_to(user_id):
                        continue
                    node_def["class_type"] = entry.new_class
                    if entry.input_transform is not None:
                        node_def["inputs"] = entry.input_transform(node_def.get("inputs", {}) or {})
                    changes.append((node_id, old_class, entry.new_class))
                    break
        return doc, changes


_DEFAULT: NodeReplaceRegistry | None = None


def get_replace_registry() -> NodeReplaceRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = NodeReplaceRegistry()
    return _DEFAULT


def reset_replace_registry() -> None:
    global _DEFAULT
    _DEFAULT = NodeReplaceRegistry()
