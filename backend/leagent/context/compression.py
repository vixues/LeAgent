"""Progressive context compression strategies.

Implements multi-level compression for conversation history, replacing
the binary "compress or don't" approach with graduated levels that
preserve maximum information within budget constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import json
from typing import TYPE_CHECKING, Any

from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class CompressionLevel(IntEnum):
    """Progressive compression levels, from no compression to maximum."""
    NONE = 0
    TOOL_SUMMARY = 1
    TURN_COMPRESS = 2
    ROLLING_SUMMARY = 3


@dataclass
class CompressionConfig:
    """Configuration for progressive compression."""
    tool_result_max_chars: int = 200
    #: Larger budget for sub-agent / coding envelopes (JSON with ``changed_files``, etc.).
    tool_result_engineering_max_chars: int = 4096
    engineering_changed_files_cap: int = 128
    engineering_path_max_chars: int = 240
    engineering_text_preview_chars: int = 1200
    engineering_activity_tail: int = 12
    turn_compress_max_chars: int = 300
    summary_max_chars: int = 2000
    min_recent_turns: int = 4
    max_summary_source_turns: int = 20


@dataclass
class CompressedMessage:
    """A message after compression, with metadata about what was lost."""
    role: str
    content: str
    original_tokens: int = 0
    compressed_tokens: int = 0
    compression_level: CompressionLevel = CompressionLevel.NONE
    metadata: dict[str, Any] = field(default_factory=dict)


def _normalized_message_role(message: dict[str, Any]) -> str | None:
    r = message.get("role")
    if r is None:
        return None
    s = str(r).strip().lower()
    return s or None


def estimate_tokens(
    content: Any,
    *,
    message_role: str | None = None,
) -> int:
    """Approximate token count (text: ~4 chars/token; multimodal lists include vision allowance)."""
    if content is None or content == "":
        return 0
    from leagent.memory.compact import approximate_message_content_tokens

    n = approximate_message_content_tokens(
        content,
        chars_per_token=4.0,
        message_role=message_role,
    )
    return max(1, n) if n > 0 else 0


def _flatten_content_for_compression(content: Any) -> str:
    """Normalize ``content`` to a string so turn compression never calls ``.strip()`` on a list."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        from leagent.memory.compact import is_vision_content_block

        parts: list[str] = []
        images = 0
        for block in content:
            if isinstance(block, dict):
                if is_vision_content_block(block):
                    images += 1
                    continue
                txt = block.get("text")
                if isinstance(txt, str) and txt.strip():
                    parts.append(txt.strip())
            elif isinstance(block, str) and block.strip():
                parts.append(block.strip())
        body = "\n".join(parts)
        if images:
            tag = f"{images} attached image(s)"
            return f"{body}\n[{tag}]" if body else f"[{tag}]"
        return body
    return str(content)


def _clip_path(p: str, max_chars: int) -> str:
    p = p.strip()
    if len(p) <= max_chars:
        return p
    return p[: max_chars - 3] + "..."


def _is_engineering_tool_payload(data: dict[str, Any]) -> bool:
    """Detect coding_agent / script_agent style JSON tool envelopes."""
    if "changed_files" in data and isinstance(data.get("changed_files"), list):
        return True
    if "steps_count" in data and "text" in data and "success" in data:
        return True
    if data.get("activity") and isinstance(data.get("activity"), list):
        return True
    return False


def _compress_engineering_tool_json(
    data: dict[str, Any],
    *,
    max_chars: int,
    changed_files_cap: int,
    path_max_chars: int,
    text_preview_chars: int,
    activity_tail: int,
) -> str:
    """Shrink sub-agent JSON while keeping paths and outcome signals."""
    slim: dict[str, Any] = {}
    for key in ("success", "partial", "error", "steps_count"):
        if key in data:
            slim[key] = data[key]

    err = data.get("error")
    if isinstance(err, str) and err.strip():
        slim["error"] = err.strip()[:800]

    cf = data.get("changed_files")
    if isinstance(cf, list):
        paths = []
        for item in cf[:changed_files_cap]:
            if isinstance(item, str) and item.strip():
                paths.append(_clip_path(item, path_max_chars))
        if paths:
            slim["changed_files"] = paths

    pf = data.get("produced_files")
    if isinstance(pf, list):
        kept: list[Any] = []
        for item in pf[:32]:
            if isinstance(item, dict):
                entry = {
                    k: item[k]
                    for k in ("path", "file_path", "name")
                    if k in item
                }
                if entry:
                    kept.append(entry)
            elif isinstance(item, str):
                kept.append(_clip_path(item, path_max_chars))
        if kept:
            slim["produced_files"] = kept

    txt = data.get("text")
    if isinstance(txt, str) and txt.strip():
        t = txt.strip()
        if len(t) > text_preview_chars:
            slim["text"] = t[:text_preview_chars] + "..."
        else:
            slim["text"] = t

    act = data.get("activity")
    if isinstance(act, list) and act:
        slim["activity"] = act[-activity_tail:]

    out = json.dumps(slim, ensure_ascii=False)
    if len(out) <= max_chars:
        return out

    # Hard-shrink: drop activity / trim text further / cap paths.
    slim.pop("activity", None)
    if isinstance(slim.get("text"), str) and len(slim["text"]) > 400:
        slim["text"] = slim["text"][:400] + "..."
    out = json.dumps(slim, ensure_ascii=False)
    if len(out) <= max_chars:
        return out

    cf2 = slim.get("changed_files")
    if isinstance(cf2, list) and len(cf2) > 24:
        slim["changed_files"] = cf2[:24]
    out = json.dumps(slim, ensure_ascii=False)
    if len(out) <= max_chars:
        return out

    return out[:max_chars] + "..."


def compress_tool_result(
    content: Any,
    max_chars: int = 200,
    *,
    engineering_max_chars: int = 4096,
    changed_files_cap: int = 128,
    path_max_chars: int = 240,
    text_preview_chars: int = 1200,
    activity_tail: int = 12,
) -> str:
    """Level 1: Truncate tool results to status + short excerpt.

    JSON payloads from ``coding_agent`` / ``script_agent`` keep structured
    fields (especially ``changed_files``) within ``engineering_max_chars``.
    """
    if not isinstance(content, str):
        try:
            content = json.dumps(content, ensure_ascii=False)
        except (TypeError, ValueError):
            content = str(content)
    if len(content) <= max_chars:
        return content

    try:
        data = json.loads(content)
        if isinstance(data, dict) and _is_engineering_tool_payload(data):
            compressed = _compress_engineering_tool_json(
                data,
                max_chars=engineering_max_chars,
                changed_files_cap=changed_files_cap,
                path_max_chars=path_max_chars,
                text_preview_chars=text_preview_chars,
                activity_tail=activity_tail,
            )
            if len(compressed) <= engineering_max_chars:
                return compressed
            return compressed[:engineering_max_chars] + "..."
        if isinstance(data, dict):
            status = data.get("status", "")
            error = data.get("error", "")
            summary_parts = []
            if status:
                summary_parts.append(f"status={status}")
            if error:
                summary_parts.append(f"error={str(error)[:100]}")
            if not summary_parts:
                for key in ("stdout", "result", "data"):
                    val = data.get(key)
                    if val:
                        summary_parts.append(f"{key}={str(val)[:80]}")
                        break
            source_echo = data.get("source_echo")
            if source_echo:
                summary_parts.append(f"source_echo={str(source_echo)[:2000]}")
            if summary_parts:
                return "[tool result] " + "; ".join(summary_parts)
    except (json.JSONDecodeError, TypeError):
        pass

    return content[:max_chars] + "..."


def compress_turn(role: str, content: Any, max_chars: int = 300) -> str:
    """Level 2: Compress a conversation turn to intent + action."""
    flat = _flatten_content_for_compression(content)
    if not flat or len(flat) <= max_chars:
        return flat

    lines = flat.strip().splitlines()
    if role == "user":
        return f"[user intent] {lines[0][:max_chars]}"
    elif role == "assistant":
        first_meaningful = ""
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith(("[", "```", "---")):
                first_meaningful = stripped
                break
        return f"[assistant action] {first_meaningful[:max_chars]}"
    return flat[:max_chars]


class ProgressiveCompressor:
    """Applies graduated compression to conversation history.

    Starting from the oldest messages, applies increasing compression
    levels until the total estimated token count fits within the budget.
    Recent messages (within ``min_recent_turns``) are never compressed.
    """

    def __init__(self, config: CompressionConfig | None = None) -> None:
        self._config = config or CompressionConfig()

    def compress(
        self,
        messages: list[dict[str, Any]],
        *,
        budget_tokens: int,
    ) -> list[CompressedMessage]:
        """Compress messages to fit within budget_tokens."""
        if not messages:
            return []

        total_tokens = sum(
            estimate_tokens(
                m.get("content", ""),
                message_role=_normalized_message_role(m),
            )
            for m in messages
        )
        if total_tokens <= budget_tokens:
            return [
                CompressedMessage(
                    role=m.get("role", ""),
                    content=m.get("content", ""),
                    original_tokens=estimate_tokens(
                        m.get("content", ""),
                        message_role=_normalized_message_role(m),
                    ),
                    compressed_tokens=estimate_tokens(
                        m.get("content", ""),
                        message_role=_normalized_message_role(m),
                    ),
                )
                for m in messages
            ]

        # Snap so the protected suffix never starts mid tool-block (orphan
        # ``tool`` rows after a rolled summary → OpenAI/DeepSeek HTTP 400).
        from leagent.memory.compact import snap_autocompact_split

        raw_split = (
            len(messages) - self._config.min_recent_turns * 2
            if len(messages) > self._config.min_recent_turns * 2
            else 0
        )
        split = snap_autocompact_split(messages, raw_split)
        old_messages = messages[:split]
        recent_messages = messages[split:]

        result: list[CompressedMessage] = []

        for level in CompressionLevel:
            if level == CompressionLevel.NONE:
                continue

            compressed_old = self._apply_level(old_messages, level)
            combined = compressed_old + [
                CompressedMessage(
                    role=m.get("role", ""),
                    content=m.get("content", ""),
                    original_tokens=estimate_tokens(
                        m.get("content", ""),
                        message_role=_normalized_message_role(m),
                    ),
                    compressed_tokens=estimate_tokens(
                        m.get("content", ""),
                        message_role=_normalized_message_role(m),
                    ),
                )
                for m in recent_messages
            ]

            total = sum(cm.compressed_tokens for cm in combined)
            if total <= budget_tokens:
                return combined
            result = combined

        return result or [
            CompressedMessage(
                role=m.get("role", ""),
                content=m.get("content", ""),
                original_tokens=estimate_tokens(
                    m.get("content", ""),
                    message_role=_normalized_message_role(m),
                ),
                compressed_tokens=estimate_tokens(
                    m.get("content", ""),
                    message_role=_normalized_message_role(m),
                ),
            )
            for m in recent_messages
        ]

    def _apply_level(
        self,
        messages: list[dict[str, Any]],
        level: CompressionLevel,
    ) -> list[CompressedMessage]:
        result: list[CompressedMessage] = []

        if level == CompressionLevel.ROLLING_SUMMARY:
            all_text = []
            for m in messages:
                role = m.get("role", "")
                raw_content = m.get("content", "")
                preview = _flatten_content_for_compression(raw_content)
                if preview:
                    all_text.append(f"{role}: {preview[:200]}")
            summary = "\n".join(all_text)[:self._config.summary_max_chars]
            total_orig = sum(
                estimate_tokens(
                    m.get("content", ""),
                    message_role=_normalized_message_role(m),
                )
                for m in messages
            )
            result.append(CompressedMessage(
                role="system",
                content=f"[Summary of {len(messages)} earlier messages]\n{summary}",
                original_tokens=total_orig,
                compressed_tokens=estimate_tokens(summary),
                compression_level=level,
            ))
            return result

        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            orig_tokens = estimate_tokens(
                content,
                message_role=_normalized_message_role(m),
            )

            if level == CompressionLevel.TOOL_SUMMARY and role == "tool":
                compressed = compress_tool_result(
                    content,
                    self._config.tool_result_max_chars,
                    engineering_max_chars=self._config.tool_result_engineering_max_chars,
                    changed_files_cap=self._config.engineering_changed_files_cap,
                    path_max_chars=self._config.engineering_path_max_chars,
                    text_preview_chars=self._config.engineering_text_preview_chars,
                    activity_tail=self._config.engineering_activity_tail,
                )
            elif level == CompressionLevel.TURN_COMPRESS:
                compressed = compress_turn(
                    role, content, self._config.turn_compress_max_chars,
                )
            else:
                compressed = content

            result.append(CompressedMessage(
                role=role,
                content=compressed,
                original_tokens=orig_tokens,
                compressed_tokens=estimate_tokens(compressed),
                compression_level=level,
            ))

        return result
