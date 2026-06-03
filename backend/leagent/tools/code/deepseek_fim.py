"""DeepSeek Fill-In-the-Middle (FIM) tool + session-scoped buffer protocol.

Exposes :meth:`~leagent.llm.providers.deepseek.DeepSeekProvider.fim_complete` to
agents as a first-class tool and optional **named buffers** so the model can
split work across turns: ``buffer_upsert`` → ``infill`` with ``use_buffer``,
optionally ``buffer_get`` / ``buffer_clear`` for inspection and reset.

Buffers are keyed by ``(session_id, buffer_id)`` and capped in total character
count to avoid unbounded memory in long chats.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext, ToolResult

logger = structlog.get_logger(__name__)

_MAX_BUFFER_CHARS = 200_000
_MAX_BUFFERS_GLOBAL = 2_000
_PRUNE_TARGET = 1_500


class _FimBufferStore:
    """In-process FIM buffers (per chat session)."""

    _lock = asyncio.Lock()
    #: (session_id, buffer_id) -> record
    _buffers: dict[tuple[str, str], dict[str, Any]] = {}

    @classmethod
    async def upsert(
        cls,
        *,
        session_id: str,
        buffer_id: str,
        prefix: str,
        suffix: str,
        path: str | None,
    ) -> None:
        if len(prefix) + len(suffix) > _MAX_BUFFER_CHARS:
            raise ValueError(
                f"prefix+suffix exceeds {_MAX_BUFFER_CHARS} characters; "
                "narrow the window or split across files."
            )
        key = (session_id, buffer_id)
        async with cls._lock:
            cls._buffers[key] = {
                "prefix": prefix,
                "suffix": suffix,
                "path": path,
                "updated_at": time.monotonic(),
            }
            await cls._maybe_prune_unlocked()

    @classmethod
    async def get(cls, session_id: str, buffer_id: str) -> dict[str, Any] | None:
        key = (session_id, buffer_id)
        async with cls._lock:
            rec = cls._buffers.get(key)
            return dict(rec) if rec else None

    @classmethod
    async def clear(cls, session_id: str, buffer_id: str) -> bool:
        key = (session_id, buffer_id)
        async with cls._lock:
            return cls._buffers.pop(key, None) is not None

    @classmethod
    async def _maybe_prune_unlocked(cls) -> None:
        if len(cls._buffers) <= _MAX_BUFFERS_GLOBAL:
            return
        items = sorted(
            cls._buffers.items(),
            key=lambda kv: float(kv[1].get("updated_at") or 0.0),
        )
        drop = len(items) - _PRUNE_TARGET
        for i in range(max(0, drop)):
            del cls._buffers[items[i][0]]


def _resolve_deepseek_provider(llm: Any) -> Any:
    """Return a :class:`~leagent.llm.providers.deepseek.DeepSeekProvider` if wired."""
    from leagent.llm.providers.deepseek import DeepSeekProvider
    from leagent.llm.service import LLMService

    if not isinstance(llm, LLMService):
        return None
    reg = llm.registry
    for name in reg.list_providers():
        try:
            prov = reg.get_provider(name)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(prov, DeepSeekProvider):
            return prov
    return None


class DeepSeekFimTool(BaseTool):
    """Fill-in-the-middle via DeepSeek ``/beta/completions`` + optional buffers."""

    name = "deepseek_fim"
    description = (
        "DeepSeek Fill-In-the-Middle: given text before the cursor (prefix) and "
        "text after (suffix), the model returns the missing middle. Only works "
        "when the deployment uses a DeepSeek provider. "
        "Protocol: (1) `buffer_upsert` to store prefix/suffix under `buffer_id` "
        "(scoped to this chat session); (2) `infill` with `use_buffer=true` to "
        "run FIM on that buffer, or pass `prefix`/`suffix` inline for one-shot "
        "infill; (3) `buffer_get` / `buffer_clear` to inspect or reset. "
        "Prefer small windows (hundreds of lines) to stay within API limits."
    )
    category = ToolCategory.CODE
    version = "1.0.0"
    aliases = ["fim_infill", "deepseek_fim_infill", "code_fim"]
    search_hint = "deepseek FIM fill middle prefix suffix infill beta completions buffer"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 120_000
    timeout_sec = 120

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "infill",
                        "buffer_upsert",
                        "buffer_get",
                        "buffer_clear",
                    ],
                    "description": "Operation: infill, or buffer lifecycle helpers.",
                },
                "buffer_id": {
                    "type": "string",
                    "description": "Logical buffer name within the session (default: default).",
                    "default": "default",
                },
                "prefix": {
                    "type": "string",
                    "description": "Code/text before the insertion point (FIM prompt).",
                },
                "suffix": {
                    "type": "string",
                    "description": "Code/text after the insertion point (FIM suffix).",
                },
                "use_buffer": {
                    "type": "boolean",
                    "description": (
                        "For `infill`: when true, read prefix/suffix from the session "
                        "buffer instead of from parameters."
                    ),
                    "default": False,
                },
                "path": {
                    "type": "string",
                    "description": "Optional file path label stored with the buffer (metadata only).",
                },
                "model": {
                    "type": "string",
                    "description": "DeepSeek FIM model (default: deepseek-v4-pro per API).",
                    "default": "deepseek-v4-pro",
                },
                "max_tokens": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8192,
                    "default": 256,
                    "description": "Maximum new tokens for the infill.",
                },
                "temperature": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 2.0,
                    "default": 0.2,
                    "description": "Sampling temperature for FIM (lower = more deterministic).",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        act = (params or {}).get("action")
        return f"DeepSeek FIM {act}" if act else "DeepSeek FIM"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        llm = context.llm
        prov = _resolve_deepseek_provider(llm)
        if prov is None:
            return {
                "ok": False,
                "error": (
                    "No DeepSeek provider is registered on the LLM service; "
                    "configure DEEPSEEK_API_KEY (or a DeepSeek-backed chat task) "
                    "to use FIM."
                ),
            }

        action = str(params.get("action") or "").strip().lower()
        buffer_id = str(params.get("buffer_id") or "default").strip() or "default"
        session_id = str(context.session_id or "_anon")

        if action == "buffer_clear":
            cleared = await _FimBufferStore.clear(session_id, buffer_id)
            return {"ok": True, "action": action, "buffer_id": buffer_id, "cleared": cleared}

        if action == "buffer_get":
            rec = await _FimBufferStore.get(session_id, buffer_id)
            if not rec:
                return {
                    "ok": True,
                    "action": action,
                    "buffer_id": buffer_id,
                    "exists": False,
                }
            pref = str(rec.get("prefix") or "")
            suf = str(rec.get("suffix") or "")
            head = 400
            return {
                "ok": True,
                "action": action,
                "buffer_id": buffer_id,
                "exists": True,
                "path": rec.get("path"),
                "prefix_chars": len(pref),
                "suffix_chars": len(suf),
                "prefix_preview": pref[:head],
                "suffix_preview": suf[:head],
            }

        if action == "buffer_upsert":
            prefix = params.get("prefix")
            suffix = params.get("suffix")
            if not isinstance(prefix, str) or not isinstance(suffix, str):
                raise ValueError("`buffer_upsert` requires string `prefix` and `suffix`")
            path = params.get("path")
            path_s = str(path).strip() if isinstance(path, str) else None
            await _FimBufferStore.upsert(
                session_id=session_id,
                buffer_id=buffer_id,
                prefix=prefix,
                suffix=suffix,
                path=path_s,
            )
            return {
                "ok": True,
                "action": action,
                "buffer_id": buffer_id,
                "prefix_chars": len(prefix),
                "suffix_chars": len(suffix),
                "path": path_s,
            }

        if action != "infill":
            raise ValueError(
                f"Unknown action {action!r}; use infill, buffer_upsert, buffer_get, or buffer_clear."
            )

        use_buffer = bool(params.get("use_buffer", False))
        if use_buffer:
            rec = await _FimBufferStore.get(session_id, buffer_id)
            if not rec:
                return {
                    "ok": False,
                    "error": f"No buffer {buffer_id!r} for this session; call buffer_upsert first.",
                }
            prefix = str(rec.get("prefix") or "")
            suffix = str(rec.get("suffix") or "")
        else:
            p_raw = params.get("prefix")
            s_raw = params.get("suffix")
            if not isinstance(p_raw, str) or not isinstance(s_raw, str):
                raise ValueError("`infill` requires `prefix` and `suffix`, or `use_buffer` with a filled buffer")
            prefix, suffix = p_raw, s_raw

        if not prefix.strip() and not suffix.strip():
            return {"ok": False, "error": "prefix and suffix cannot both be empty"}

        model = str(params.get("model") or "deepseek-v4-pro").strip()
        max_tokens = int(params.get("max_tokens") or 256)
        temperature = float(params.get("temperature") if params.get("temperature") is not None else 0.2)

        text = await prov.fim_complete(
            prefix,
            suffix,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        await self._track_artifact(text or "", model, buffer_id, context)

        logger.info(
            "deepseek_fim_infill",
            buffer_id=buffer_id,
            use_buffer=use_buffer,
            model=model,
            out_chars=len(text or ""),
        )
        return {
            "ok": True,
            "action": "infill",
            "buffer_id": buffer_id,
            "model": model,
            "infill": text,
            "infill_chars": len(text or ""),
        }

    @staticmethod
    async def _track_artifact(
        infill_text: str, model: str, buffer_id: str, context: ToolContext,
    ) -> None:
        try:
            from leagent.tools.code.pipeline import get_pipeline
            from leagent.tools.code.artifact import ArtifactKind

            pipeline = get_pipeline(context)
            if pipeline is None:
                return
            await pipeline.prepare(
                kind=ArtifactKind.SNIPPET,
                source=infill_text,
                language="auto",
                origin_tool="deepseek_fim",
                context=context,
                skip_validation=True,
                metadata={"model": model, "buffer_id": buffer_id},
            )
        except Exception:  # noqa: BLE001
            logger.debug("deepseek_fim_artifact_tracking_error", exc_info=True)

    def coerce_tool_result(self, raw: Any, *, duration_ms: int, attempt: int) -> ToolResult:
        if isinstance(raw, dict) and raw.get("ok") is False:
            err = str(raw.get("error") or "FIM failed")
            return ToolResult.fail(err, duration_ms=duration_ms, data=raw, attempts=attempt)
        return ToolResult.ok(raw, duration_ms=duration_ms, attempts=attempt)


__all__ = ["DeepSeekFimTool"]
