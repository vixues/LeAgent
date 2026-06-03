"""One-shot migration from tier1/tier2 config to providers.yaml v2 + task routing.

Run via::

    leagent models migrate
    # or
    uv run python scripts/migrate_to_v2.py

No runtime backward compatibility — after migration, remove all ``*_TIER*`` env vars.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from leagent.config.constants import LEAGENT_HOME, PROVIDERS_PATH
from leagent.config.tier_env_guard import detect_legacy_tier_env
from leagent.llm.model_spec import ModelSpec
from leagent.llm.providers_schema import PROVIDERS_CONFIG_VERSION, validate_v2_config

_TIER_KEY_RE = re.compile(
    r"^(?:LEAGENT|WORKAGENT)_LLM__TIER[12]_API_KEY$|^LLM_TIER[12]_API_KEY$",
    re.IGNORECASE,
)
_TIER_ENV_RE = re.compile(
    r"^(?:LEAGENT|WORKAGENT)_LLM__TIER[12]_|^LLM_TIER[12]_",
    re.IGNORECASE,
)
_WORKAGENT_LLM_RE = re.compile(r"^WORKAGENT_LLM__", re.IGNORECASE)


_OBSOLETE_LLM_ENV_RE = re.compile(
    r"^(?:LEAGENT|WORKAGENT)_LLM__(?:DASHSCOPE|DEEPSEEK)_MODEL$",
    re.IGNORECASE,
)


@dataclass
class MigrationReport:
    env_path: Path | None = None
    env_changed: bool = False
    env_removed_keys: list[str] = field(default_factory=list)
    env_added_keys: list[str] = field(default_factory=list)
    providers_path: Path | None = None
    providers_changed: bool = False
    providers_backup: Path | None = None
    routing_tasks: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _strip_quotes(value: str) -> str:
    val = value.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        return val[1:-1]
    return val


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        out[key.strip()] = _strip_quotes(val)
    return out


def migrate_env_file(
    path: Path,
    *,
    dry_run: bool = False,
) -> tuple[dict[str, str], list[str], list[str]]:
    """Rewrite dotenv: drop tier keys, rename WORKAGENT_LLM__ → LEAGENT_LLM__."""
    if not path.is_file():
        return {}, [], []

    raw_lines = path.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []
    removed: list[str] = []
    added: list[str] = []
    tier1_key = ""
    tier2_key = ""
    tier1_model = ""
    tier1_base = ""
    entries: dict[str, str] = {}

    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" not in stripped:
            new_lines.append(line)
            continue

        key, _, val = stripped.partition("=")
        key = key.strip()
        upper = key.upper()
        unquoted = _strip_quotes(val)

        if _TIER_KEY_RE.match(upper):
            removed.append(key)
            if "TIER1" in upper:
                tier1_key = tier1_key or unquoted
            else:
                tier2_key = tier2_key or unquoted
            continue

        if "TIER1_MODEL" in upper:
            removed.append(key)
            tier1_model = tier1_model or unquoted
            continue
        if "TIER1_ENDPOINT" in upper:
            removed.append(key)
            tier1_base = tier1_base or unquoted.rstrip("/")
            continue

        if _TIER_ENV_RE.match(upper) or _OBSOLETE_LLM_ENV_RE.match(upper):
            removed.append(key)
            continue

        if _WORKAGENT_LLM_RE.match(key):
            removed.append(key)
            if "DASHSCOPE_API_KEY" in upper:
                tier2_key = tier2_key or unquoted
            continue

        if key in entries:
            continue
        entries[key] = val
        new_lines.append(f"{key}={val}")

    def _ensure(key: str, value: str) -> None:
        if not value or key in entries:
            return
        entries[key] = value
        new_lines.append(f"{key}={value}")
        added.append(key)

    _ensure("DEEPSEEK_API_KEY", tier1_key)
    _ensure("DASHSCOPE_API_KEY", tier2_key)
    _ensure("DEEPSEEK_MODEL", tier1_model)
    _ensure("DEEPSEEK_BASE_URL", tier1_base)

    changed = bool(removed or added)
    if changed and not dry_run:
        path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")

    return entries, removed, added


def _task_from_tier_models(
    providers: list[dict[str, Any]],
    *,
    default_provider: str,
    default_model: str,
) -> dict[str, dict[str, str]]:
    tier1: dict[str, str] | None = None
    tier2: dict[str, str] | None = None

    for entry in providers:
        if not isinstance(entry, dict):
            continue
        provider_name = str(entry.get("name") or "").strip()
        for raw_model in entry.get("models") or []:
            if not isinstance(raw_model, dict):
                continue
            tier = str(raw_model.get("tier") or "").strip().lower()
            model_name = str(raw_model.get("name") or "").strip()
            if not provider_name or not model_name:
                continue
            binding = {"provider": provider_name, "model": model_name}
            if tier == "tier1":
                tier1 = binding
            elif tier == "tier2":
                tier2 = binding

    chat = (
        {"provider": default_provider, "model": default_model}
        if default_provider and default_model
        else tier1
    )
    tasks: dict[str, dict[str, str]] = {}
    if chat:
        tasks["chat"] = chat
    if tier2:
        tasks["fast"] = tier2
        tasks["compression"] = tier2
        tasks["title"] = tier2
    elif chat:
        tasks["fast"] = chat
        tasks["compression"] = chat
        tasks["title"] = chat
    return tasks


def migrate_providers_yaml(
    path: Path,
    *,
    dry_run: bool = False,
    in_place: bool = True,
    output: Path | None = None,
) -> tuple[dict[str, Any], bool, Path | None]:
    """Migrate providers.yaml to version 2 with routing.tasks (no tier fields)."""
    if not path.is_file():
        raise FileNotFoundError(f"providers.yaml not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("providers.yaml root must be a mapping")

    backup: Path | None = None
    version = raw.get("version")
    default_provider = str(raw.get("default_provider") or "").strip()
    default_model = str(raw.get("default_model") or "").strip()

    routing = raw.get("routing") if isinstance(raw.get("routing"), dict) else {}
    existing_tasks = routing.get("tasks") if isinstance(routing.get("tasks"), dict) else {}

    providers_out: list[dict[str, Any]] = []
    tier_tasks: dict[str, dict[str, str]] = {}

    for entry in raw.get("providers") or []:
        if not isinstance(entry, dict):
            continue
        provider_name = str(entry.get("name") or "").strip()
        models_out: list[dict[str, Any]] = []
        for raw_model in entry.get("models") or []:
            if not isinstance(raw_model, dict):
                continue
            spec = ModelSpec.from_provider_entry(provider_name, raw_model)
            model_dict = spec.to_dict()
            tier = str(raw_model.get("tier") or "").strip().lower()
            if tier == "tier1" and provider_name and spec.name:
                tier_tasks.setdefault("chat", {"provider": provider_name, "model": spec.name})
            if tier == "tier2" and provider_name and spec.name:
                tier_tasks.setdefault("fast", {"provider": provider_name, "model": spec.name})
            models_out.append(model_dict)
        item = {k: v for k, v in entry.items() if k != "models"}
        item["models"] = models_out
        providers_out.append(item)

    tasks = dict(existing_tasks) if existing_tasks else {}
    if tier_tasks:
        for key, binding in tier_tasks.items():
            tasks.setdefault(key, binding)

    if not tasks.get("chat") and default_provider and default_model:
        tasks["chat"] = {"provider": default_provider, "model": default_model}
    if not tasks:
        tasks = _task_from_tier_models(
            raw.get("providers") or [],
            default_provider=default_provider,
            default_model=default_model,
        )

    chat = tasks.get("chat")
    if isinstance(chat, dict) and chat.get("provider") and chat.get("model"):
        for slot in ("fast", "compression", "title"):
            tasks.setdefault(slot, dict(chat))

    migrated: dict[str, Any] = {
        "version": PROVIDERS_CONFIG_VERSION,
        "default_task": str(raw.get("default_task") or "chat"),
        "default_provider": default_provider,
        "default_model": default_model,
        "providers": providers_out,
        "routing": {**routing, "tasks": tasks},
    }
    if isinstance(raw.get("pricing"), dict):
        migrated["pricing"] = raw["pricing"]

    normalized = validate_v2_config(migrated)
    changed = version != PROVIDERS_CONFIG_VERSION or any(
        isinstance(m, dict) and m.get("tier") for p in raw.get("providers") or [] for m in (p.get("models") or [])
    )

    if not changed and version == PROVIDERS_CONFIG_VERSION:
        return normalized, False, None

    dest = path if in_place else (output or path.with_suffix(".v2.yaml"))
    if not dry_run:
        if in_place and path.exists():
            backup_dir = path.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            backup = backup_dir / f"providers-pre-v2-{ts}.yaml"
            shutil.copy2(path, backup)
        else:
            backup = None
        dest.write_text(
            yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    else:
        backup = None

    return normalized, True, backup


def run_migration(
    *,
    env_path: Path | None = None,
    providers_path: Path | None = None,
    migrate_env: bool = True,
    migrate_providers: bool = True,
    dry_run: bool = False,
    in_place: bool = True,
    providers_output: Path | None = None,
) -> MigrationReport:
    """Migrate ~/.leagent/.env and providers.yaml to v2 (no tier mode)."""
    report = MigrationReport()
    env_path = env_path or (LEAGENT_HOME / ".env")
    providers_path = providers_path or PROVIDERS_PATH

    if migrate_env and env_path.is_file():
        report.env_path = env_path
        _, removed, added = migrate_env_file(env_path, dry_run=dry_run)
        report.env_changed = bool(removed or added)
        report.env_removed_keys = removed
        report.env_added_keys = added
        if removed:
            report.notes.append(f"Removed {len(removed)} tier env entries from {env_path}")

    if migrate_providers and providers_path.is_file():
        report.providers_path = providers_path
        normalized, changed, backup = migrate_providers_yaml(
            providers_path,
            dry_run=dry_run,
            in_place=in_place,
            output=providers_output,
        )
        report.providers_changed = changed
        report.providers_backup = backup
        tasks = normalized.get("routing", {}).get("tasks", {})
        report.routing_tasks = tasks if isinstance(tasks, dict) else {}

    return report
