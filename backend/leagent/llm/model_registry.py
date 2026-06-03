"""In-memory catalog of model specs built from providers.yaml v2."""

from __future__ import annotations

from typing import Any

from leagent.llm.model_spec import ModelKind, ModelSpec, ModelTask


class ModelRegistry:
    """Index of all enabled models across providers."""

    def __init__(self) -> None:
        self._specs: dict[tuple[str, str], ModelSpec] = {}
        self._default_task: ModelTask = ModelTask.CHAT
        self._task_bindings: dict[str, dict[str, Any]] = {}
        self._fallbacks: dict[str, list[dict[str, str]]] = {}
        self._failover_enabled: bool = False
        self._failover_max_retries: int = 2

    def load_from_config(self, config: dict[str, Any]) -> None:
        """Rebuild catalog from a validated providers.yaml v2 dict."""
        self._specs.clear()
        default_task_raw = str(config.get("default_task") or "chat").strip().lower()
        try:
            self._default_task = ModelTask(default_task_raw)
        except ValueError:
            self._default_task = ModelTask.CHAT

        for entry in config.get("providers", []):
            if not isinstance(entry, dict):
                continue
            if entry.get("enabled", True) is False:
                continue
            provider_name = str(entry.get("name") or "").strip()
            if not provider_name:
                continue
            for raw_model in entry.get("models") or []:
                if not isinstance(raw_model, dict):
                    continue
                spec = ModelSpec.from_provider_entry(provider_name, raw_model)
                if not spec.name or not spec.enabled:
                    continue
                self._specs[(provider_name, spec.name)] = spec

        routing = config.get("routing") if isinstance(config.get("routing"), dict) else {}
        tasks = routing.get("tasks") if isinstance(routing.get("tasks"), dict) else {}
        self._task_bindings = {str(k): v for k, v in tasks.items() if isinstance(v, dict)}

        fallbacks = routing.get("fallbacks") if isinstance(routing.get("fallbacks"), dict) else {}
        self._fallbacks = {}
        for task_name, chain in fallbacks.items():
            if not isinstance(chain, list):
                continue
            parsed: list[dict[str, str]] = []
            for item in chain:
                if isinstance(item, dict):
                    p = str(item.get("provider") or "").strip()
                    m = str(item.get("model") or "").strip()
                    if p and m:
                        parsed.append({"provider": p, "model": m})
            if parsed:
                self._fallbacks[str(task_name)] = parsed

        failover = routing.get("failover") if isinstance(routing.get("failover"), dict) else {}
        self._failover_enabled = bool(failover.get("enabled", False))
        self._failover_max_retries = int(failover.get("max_retries") or 2)

    @property
    def default_task(self) -> ModelTask:
        return self._default_task

    @property
    def failover_enabled(self) -> bool:
        return self._failover_enabled

    @property
    def failover_max_retries(self) -> int:
        return self._failover_max_retries

    def get_spec(self, provider: str, model: str) -> ModelSpec | None:
        return self._specs.get((provider.strip(), model.strip()))

    def list_specs(self) -> list[ModelSpec]:
        return list(self._specs.values())

    def list_by_kind(self, kind: ModelKind) -> list[ModelSpec]:
        return [s for s in self._specs.values() if s.kind == kind]

    def list_agent_models(self) -> list[ModelSpec]:
        return [
            s for s in self._specs.values()
            if s.kind == "chat" and s.capabilities.tool_call
        ]

    def list_vision_models(self) -> list[ModelSpec]:
        return [
            s for s in self._specs.values()
            if s.kind == "chat" and s.capabilities.supports_input("image")
        ]

    def list_image_gen_models(self) -> list[ModelSpec]:
        return [s for s in self._specs.values() if s.kind == "image_gen"]

    def task_binding(self, task: ModelTask | str) -> dict[str, Any]:
        key = task.value if isinstance(task, ModelTask) else str(task)
        raw = self._task_bindings.get(key)
        return raw if isinstance(raw, dict) else {}

    def fallbacks_for(self, task: ModelTask) -> list[dict[str, str]]:
        return list(self._fallbacks.get(task.value, []))

    def resolve_task_binding(
        self,
        task: ModelTask,
        *,
        _seen: frozenset[str] | None = None,
    ) -> tuple[str, str]:
        """Resolve provider/model for a task, following inherit chain."""
        seen = _seen or frozenset()
        if task.value in seen:
            raise ValueError(f"Circular inherit in routing.tasks: {task.value}")
        seen = frozenset(set(seen) | {task.value})

        binding = self.task_binding(task)
        provider = str(binding.get("provider") or "").strip()
        model = str(binding.get("model") or "").strip()
        if provider and model:
            return provider, model

        inherit_raw = str(binding.get("inherit") or "").strip()
        if inherit_raw:
            try:
                parent = ModelTask(inherit_raw)
            except ValueError as exc:
                raise ValueError(f"Unknown inherit task '{inherit_raw}' for {task.value}") from exc
            return self.resolve_task_binding(parent, _seen=seen)

        raise ValueError(f"routing.tasks.{task.value} is not configured")
