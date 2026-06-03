"""Task-based model resolution for providers.yaml v2."""

from __future__ import annotations

from typing import Any

from leagent.exceptions.llm import LLMServiceError, ModelNotFoundError
from leagent.llm.base import ChatMessage
from leagent.llm.model_registry import ModelRegistry
from leagent.llm.model_spec import ModelSpec, ModelTask, ResolvedModel, TaskBinding
from leagent.llm.registry import ProviderRegistry


def messages_contain_image(messages: list[ChatMessage] | None) -> bool:
    """Return True when any message carries image/multimodal parts."""
    if not messages:
        return False
    for msg in messages:
        if _content_has_vision_block(msg.content):
            return True
    return False


def _content_has_vision_block(content: Any) -> bool:
    if isinstance(content, list):
        return any(isinstance(block, dict) and _is_vision_block(block) for block in content)
    return False


def strip_image_blocks_from_content(content: Any) -> Any:
    """Remove inline vision blocks; collapse to plain text when possible."""
    if not isinstance(content, list):
        return content
    kept: list[Any] = []
    for block in content:
        if isinstance(block, dict) and _is_vision_block(block):
            continue
        kept.append(block)
    if not kept:
        return (
            "[Image attachment omitted: selected model does not accept inline images. "
            "Use the file path from session_attachments with image_ocr, code_execution, "
            "or other file tools.]"
        )
    if len(kept) == 1 and isinstance(kept[0], dict) and kept[0].get("type") == "text":
        return str(kept[0].get("text") or "")
    return kept


def strip_image_blocks_from_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Drop inline image blocks from every message (for text-only models)."""
    out: list[ChatMessage] = []
    for msg in messages:
        if _content_has_vision_block(msg.content):
            out.append(msg.model_copy(update={"content": strip_image_blocks_from_content(msg.content)}))
        else:
            out.append(msg)
    return out


def _is_vision_block(block: dict[str, Any]) -> bool:
    btype = str(block.get("type") or "").lower()
    if btype in ("image_url", "image", "input_image", "image_file"):
        return True
    if "image_url" in block:
        return True
    src = block.get("source")
    if isinstance(src, dict):
        st = str(src.get("type") or "").lower()
        if st in ("base64", "url") and (btype == "image" or bool(src.get("media_type"))):
            return True
    return False


class TaskResolver:
    """Resolve provider/model for a logical task with capability checks."""

    DEFAULT_MAX_TOKENS = 8192
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_TIMEOUT = 120.0
    FAST_MAX_TOKENS = 2048

    def __init__(
        self,
        registry: ProviderRegistry,
        catalog: ModelRegistry,
    ) -> None:
        self.registry = registry
        self.catalog = catalog

    def resolve(
        self,
        task: ModelTask,
        *,
        messages: list[ChatMessage] | None = None,
        user_provider: str | None = None,
        user_model: str | None = None,
    ) -> ResolvedModel:
        """Resolve the model to use for *task*."""
        effective_task = task
        reason = "task_binding"

        if task == ModelTask.CHAT and messages_contain_image(messages):
            chat_provider, chat_model = self._try_resolve_task(ModelTask.CHAT)
            chat_spec = self.catalog.get_spec(chat_provider, chat_model)
            if chat_spec and not chat_spec.capabilities.supports_input("image"):
                if user_provider and user_model:
                    user_spec = self.catalog.get_spec(user_provider, user_model)
                    if user_spec is None:
                        raise ModelNotFoundError(
                            f"Model '{user_model}' not found for provider '{user_provider}'"
                        )
                    if user_spec.capabilities.supports_input("image"):
                        return self._build_resolved(
                            ModelTask.CHAT,
                            user_provider,
                            user_model,
                            user_spec,
                            reason="user_explicit_vision",
                        )
                    # Honor the user's text-only model; image paths stay in message text / tools.
                    return self._build_resolved(
                        ModelTask.CHAT,
                        user_provider,
                        user_model,
                        user_spec,
                        reason="user_explicit_text_only",
                    )
                vision = self._try_usable_vision_binding()
                if vision is not None:
                    v_provider, v_model, v_spec = vision
                    return self._build_resolved(
                        ModelTask.VISION,
                        v_provider,
                        v_model,
                        v_spec,
                        reason="vision_upgrade",
                    )
                # Keep chat binding; inline images are stripped and file paths stay in the prompt.
                reason = "vision_unavailable_use_tools"

        if user_provider and user_model:
            spec = self.catalog.get_spec(user_provider, user_model)
            if spec is None:
                raise ModelNotFoundError(
                    f"Model '{user_model}' not found for provider '{user_provider}'"
                )
            self._validate_task_capabilities(effective_task, spec, requested_task=task)
            if not self.registry.has_provider(user_provider):
                raise ModelNotFoundError(f"Provider '{user_provider}' not registered")
            return self._build_resolved(
                effective_task,
                user_provider,
                user_model,
                spec,
                reason=reason,
            )

        try:
            provider, model = self._try_resolve_task(effective_task)
        except ValueError:
            if effective_task == ModelTask.VISION:
                effective_task = ModelTask.CHAT
                reason = "vision_unavailable_use_tools"
                provider, model = self._try_resolve_task(ModelTask.CHAT)
            else:
                raise
        spec = self.catalog.get_spec(provider, model)
        if spec is None and effective_task == ModelTask.VISION and task == ModelTask.CHAT:
            effective_task = ModelTask.CHAT
            reason = "vision_unavailable_use_tools"
            provider, model = self._try_resolve_task(ModelTask.CHAT)
            spec = self.catalog.get_spec(provider, model)
        if spec is None:
            raise ModelNotFoundError(f"Model '{model}' not found for provider '{provider}'")
        self._validate_task_capabilities(effective_task, spec, requested_task=task)
        if not self.registry.has_provider(provider):
            raise ModelNotFoundError(f"Provider '{provider}' not registered")
        return self._build_resolved(effective_task, provider, model, spec, reason=reason)

    def _try_usable_vision_binding(self) -> tuple[str, str, ModelSpec] | None:
        """Return vision task binding only when the model is enabled and image-capable."""
        try:
            provider, model = self.catalog.resolve_task_binding(ModelTask.VISION)
        except ValueError:
            return None
        spec = self.catalog.get_spec(provider, model)
        if spec is None or not spec.enabled or not spec.capabilities.supports_input("image"):
            return None
        if not self.registry.has_provider(provider):
            return None
        return provider, model, spec

    def _try_resolve_task(self, task: ModelTask) -> tuple[str, str]:
        try:
            return self.catalog.resolve_task_binding(task)
        except ValueError:
            if task == ModelTask.VISION:
                raise
            if task != ModelTask.CHAT:
                return self.catalog.resolve_task_binding(ModelTask.CHAT)
            raise

    def _validate_task_capabilities(
        self,
        task: ModelTask,
        spec: ModelSpec,
        *,
        requested_task: ModelTask | None = None,
    ) -> None:
        if task in (ModelTask.CHAT, ModelTask.VISION, ModelTask.FAST) and spec.kind != "chat":
            raise LLMServiceError(
                f"Task '{task.value}' requires a chat model, got kind={spec.kind}"
            )
        if task == ModelTask.VISION and not spec.capabilities.supports_input("image"):
            if requested_task == ModelTask.VISION:
                raise LLMServiceError(
                    f"Task 'vision' requires a model with image input; "
                    f"{spec.provider}/{spec.name} lacks image capability"
                )
            # Chat requests with images may fall back to a text model; inline images are stripped.
            return
        if task == ModelTask.CHAT and spec.kind == "chat" and not spec.capabilities.tool_call:
            # Allow non-tool models for direct completion calls but agent layer should filter
            pass
        if task == ModelTask.EMBEDDING and spec.kind != "embedding":
            raise LLMServiceError(
                f"Task 'embedding' requires kind=embedding, got {spec.kind}"
            )
        if task == ModelTask.IMAGE_GEN and spec.kind != "image_gen":
            raise LLMServiceError(
                f"Task 'image_gen' requires kind=image_gen, got {spec.kind}"
            )

    def _build_resolved(
        self,
        task: ModelTask,
        provider: str,
        model: str,
        spec: ModelSpec,
        *,
        reason: str,
    ) -> ResolvedModel:
        binding = TaskBinding.from_dict(self.catalog.task_binding(task))
        max_tokens = binding.max_tokens or (
            self.FAST_MAX_TOKENS
            if task in (ModelTask.FAST, ModelTask.COMPRESSION, ModelTask.TITLE)
            else self.DEFAULT_MAX_TOKENS
        )
        temperature = binding.temperature or self.DEFAULT_TEMPERATURE
        timeout = binding.timeout or self.DEFAULT_TIMEOUT
        return ResolvedModel(
            task=task,
            provider=provider,
            model=model,
            spec=spec,
            reason=reason,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )

    def candidate_providers(self, resolved: ResolvedModel) -> list[tuple[str, str]]:
        """Primary provider/model followed by task fallback chain."""
        candidates = [(resolved.provider, resolved.model)]
        if not self.catalog.failover_enabled:
            return candidates
        for item in self.catalog.fallbacks_for(resolved.task):
            pair = (item["provider"], item["model"])
            if pair not in candidates:
                candidates.append(pair)
        return candidates[: self.catalog.failover_max_retries + 1]

    def clamp_max_tokens(
        self,
        messages: list[ChatMessage],
        *,
        spec: ModelSpec,
        requested: int,
    ) -> int:
        """Reduce completion tokens when prompt + output would exceed context window."""
        if requested <= 0 or spec.context_window <= 0:
            return requested
        try:
            import tiktoken

            enc = tiktoken.get_encoding("cl100k_base")
            prompt_tokens = sum(
                len(enc.encode(str(m.content or "")))
                for m in messages
            )
        except Exception:
            prompt_tokens = sum(len(str(m.content or "")) // 4 for m in messages)
        budget = spec.context_window - prompt_tokens - 64
        if budget < 256:
            return max(256, min(requested, budget))
        return min(requested, budget)
