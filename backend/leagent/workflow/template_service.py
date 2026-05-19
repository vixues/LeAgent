"""Template service — loads, lists, and serves workflow templates.

Unifies YAML templates under ``config/workflows/templates/`` and the
built-in Python templates from :mod:`leagent.workflow.templates` into
a single catalog. Every template exposes the **canonical** workflow
document shape that :func:`leagent.workflow.io.load` expects — the
YAML authoring DSL (flat nodes list, ``on_error``, mustache placeholders)
is converted via :func:`leagent.workflow.io.authoring.to_canonical`
at load time. There is no runtime version migration.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
import yaml

from leagent.workflow.io.authoring import to_canonical

logger = structlog.get_logger(__name__)

CATEGORY_LABELS = {
    "finance": "Finance & Accounting",
    "productivity": "Productivity",
    "hr": "Human Resources",
    "procurement": "Procurement",
    "compliance": "Compliance & Audit",
    "customer": "Customer Service",
    "customer_service": "Customer Service",
    "data": "Data Processing",
    "data_management": "Data Management",
    "approval": "Approvals",
    "document": "Document Processing",
    "document_management": "Document Management",
    "communication": "Communication",
    "legal": "Legal",
    "analytics": "Analytics",
    "quality": "Quality Assurance",
    "inventory": "Inventory Management",
    "audit": "Audit & Compliance",
    "general": "General",
}

CATEGORY_ICONS = {
    "finance": "💰",
    "productivity": "📋",
    "hr": "👥",
    "procurement": "🛒",
    "compliance": "🔍",
    "customer": "🎧",
    "customer_service": "🎧",
    "data": "📊",
    "data_management": "📊",
    "approval": "✅",
    "document": "📄",
    "document_management": "📄",
    "communication": "✉️",
    "legal": "⚖️",
    "analytics": "📈",
    "quality": "🔬",
    "inventory": "📦",
    "audit": "🔍",
    "general": "📋",
}

CATEGORY_ALIASES: dict[str, str] = {
    "customer_service": "customer",
    "data_management": "data",
    "document_management": "document",
    "audit": "compliance",
}


def _convert_mustache_to_dollar(text: str) -> str:
    """Convert ``{{expr}}`` placeholders to ``${expr}`` for the executor."""
    if not isinstance(text, str):
        return text
    return re.sub(r"\{\{(.+?)\}\}", r"${\1}", text)


def _deep_convert_placeholders(obj: Any) -> Any:
    if isinstance(obj, str):
        return _convert_mustache_to_dollar(obj)
    if isinstance(obj, dict):
        return {k: _deep_convert_placeholders(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_convert_placeholders(item) for item in obj]
    return obj


def _flatten_branch_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten inline node definitions embedded inside parallel branches.

    Authors may embed full node dicts inside a ``branches[].nodes`` list
    for readability. The canonical shape expects branch nodes to be
    ID references only, so we hoist the embedded dicts to the top-level
    list and replace each entry with its ``id``.
    """
    extra_nodes: list[dict[str, Any]] = []
    for node in nodes:
        for branch in node.get("branches", []) or []:
            raw_nodes = branch.get("nodes", []) or []
            flat_ids: list[str] = []
            for item in raw_nodes:
                if isinstance(item, dict):
                    extra_nodes.append(item)
                    if "branches" in item:
                        extra_nodes.extend(_flatten_branch_nodes([item]))
                    flat_ids.append(item["id"])
                else:
                    flat_ids.append(str(item))
            branch["nodes"] = flat_ids
    return extra_nodes


def _normalize_conditions(node: dict[str, Any]) -> None:
    """Pull ``- else: target`` out of a conditions list into ``else_node``."""
    conditions = node.get("conditions")
    if not isinstance(conditions, list):
        return
    cleaned: list[dict[str, Any]] = []
    for cond in conditions:
        if not isinstance(cond, dict):
            cleaned.append(cond)
            continue
        if "else" in cond and "if" not in cond and "if_expr" not in cond:
            if "else_node" not in node and "else" not in node:
                node["else_node"] = cond["else"]
        else:
            cleaned.append(cond)
    node["conditions"] = cleaned


def _normalize_node(node: dict[str, Any]) -> dict[str, Any]:
    """Map YAML convenience fields onto the authoring-shape fields."""
    if "on_error" in node and "error_handler" not in node:
        node["error_handler"] = node.pop("on_error")

    _normalize_conditions(node)

    if "reviewer_role" in node and "reviewer" not in node:
        node["reviewer"] = node["reviewer_role"]

    if node.get("type") == "end" and isinstance(node.get("output"), dict):
        node.setdefault("metadata", {})["end_output"] = node.pop("output")
    elif isinstance(node.get("output"), str) and node.get("type") == "end":
        node.setdefault("metadata", {})["end_output"] = node.pop("output")

    for extra_key in (
        "display_data",
        "actions",
        "reviewer_role",
        "reviewer_department",
        "reviewer_id",
        "timeout_action",
        "resume_condition",
        "timeout",
        "input_fields",
        "system_prompt",
    ):
        if extra_key in node:
            node.setdefault("metadata", {})[extra_key] = node.pop(extra_key)

    return node


def _yaml_to_canonical(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a YAML template (or already-canonical dict) to the canonical shape."""
    data = raw.get("workflow", raw) if isinstance(raw, dict) else raw
    data = _deep_convert_placeholders(data)

    nodes = data.get("nodes", [])
    if isinstance(nodes, list):
        extra = _flatten_branch_nodes(nodes)
        nodes.extend(extra)
        nodes = [_normalize_node(n) for n in nodes]
        data["nodes"] = nodes

    # Outputs: if author wrote schema-like entries without value_expr,
    # auto-generate them from the end node's output mapping or a ${name}
    # placeholder so the executor can resolve them.
    end_output_map: dict[str, Any] = {}
    if isinstance(nodes, list):
        for n in nodes:
            if n.get("type") == "end":
                end_meta = n.get("metadata", {}).get("end_output")
                if isinstance(end_meta, dict):
                    end_output_map = end_meta
                break
    outputs = []
    for out in data.get("outputs", []) or []:
        out = dict(out)
        if not out.get("value") and not out.get("value_expr"):
            name = out.get("name", "")
            if name in end_output_map:
                out["value"] = end_output_map[name]
            elif name:
                out["value"] = f"${{{name}}}"
        outputs.append(out)
    data["outputs"] = outputs

    tags = list(data.get("tags", []) or [])
    metadata = dict(data.get("metadata", {}) or {})
    if "category" in data:
        raw_category = data["category"]
        canonical_category = CATEGORY_ALIASES.get(raw_category, raw_category)
        metadata["category"] = canonical_category
        metadata["original_category"] = raw_category
        if canonical_category not in tags:
            tags.append(canonical_category)
    if "trigger" in data:
        metadata["trigger"] = data["trigger"]
    data["metadata"] = metadata
    data["tags"] = tags

    canonical = to_canonical(data)
    canonical.setdefault("metadata", {})
    canonical["metadata"].update(metadata)
    canonical.setdefault("control", {})
    canonical["control"]["tags"] = tags
    return canonical


class TemplateInfo:
    """Lightweight template summary for listing."""

    __slots__ = (
        "id",
        "name",
        "description",
        "category",
        "icon",
        "tags",
        "node_count",
        "version",
        "source",
    )

    def __init__(
        self,
        id: str,
        name: str,
        description: str = "",
        category: str = "general",
        icon: str = "📋",
        tags: list[str] | None = None,
        node_count: int = 0,
        version: str = "1.0",
        source: str = "yaml",
    ):
        self.id = id
        self.name = name
        self.description = description
        self.category = category
        self.icon = icon
        self.tags = tags or []
        self.node_count = node_count
        self.version = version
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "category_label": CATEGORY_LABELS.get(self.category, self.category.title()),
            "icon": self.icon,
            "tags": self.tags,
            "node_count": self.node_count,
            "version": self.version,
            "source": self.source,
        }


class TemplateService:
    """Loads and serves workflow templates."""

    def __init__(self, templates_dir: str | Path | None = None):
        self._templates_dir = Path(templates_dir) if templates_dir else None
        self._cache: dict[str, dict[str, Any]] = {}
        self._info_cache: dict[str, TemplateInfo] = {}
        self._loaded = False

    def _find_templates_dir(self) -> Path | None:
        if self._templates_dir and self._templates_dir.exists():
            return self._templates_dir
        candidates: list[Path] = []
        try:
            from leagent.config.constants import WORKFLOWS_DIR
            from leagent.config.settings import get_settings

            wd = (get_settings().workflows_directory or "").strip()
            if wd:
                candidates.append(Path(wd).expanduser().resolve() / "templates")
            candidates.append(Path(WORKFLOWS_DIR).resolve() / "templates")
        except Exception:  # noqa: BLE001
            pass
        candidates.extend(
            [
                Path("/app/config/workflows/templates"),
                Path(__file__).resolve().parents[3] / "config" / "workflows" / "templates",
                Path.cwd() / "config" / "workflows" / "templates",
            ]
        )
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return None

    def load(self) -> None:
        self._cache.clear()
        self._info_cache.clear()

        self._load_builtin_templates()
        self._load_yaml_templates()

        self._loaded = True
        logger.info(
            "templates_loaded",
            total=len(self._cache),
            yaml_dir=str(self._find_templates_dir()),
        )

    def _load_builtin_templates(self) -> None:
        try:
            from leagent.workflow.templates import BUILTIN_TEMPLATES
        except ImportError:
            logger.debug("builtin_templates_not_available")
            return

        for tid, tdata in BUILTIN_TEMPLATES.items():
            canonical = to_canonical(tdata)
            self._cache[tid] = canonical
            self._info_cache[tid] = TemplateInfo(
                id=tid,
                name=canonical.get("name", tid),
                description=canonical.get("description", ""),
                category=self._infer_category(tdata),
                icon=self._infer_icon(tdata),
                tags=list(tdata.get("tags", []) or []),
                node_count=len(canonical.get("nodes", {})),
                version=str(tdata.get("version", "1.0")),
                source="builtin",
            )

    def _load_yaml_templates(self) -> None:
        tdir = self._find_templates_dir()
        if not tdir:
            logger.debug("yaml_templates_dir_not_found")
            return

        for yaml_file in sorted(tdir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    continue

                canonical = _yaml_to_canonical(raw)
                tid = canonical.get("id") or yaml_file.stem
                canonical["id"] = tid

                self._cache[tid] = canonical
                meta = canonical.get("metadata", {}) or {}
                category = meta.get("category") or self._infer_category(raw)
                tags = list(canonical.get("control", {}).get("tags", []) or [])
                self._info_cache[tid] = TemplateInfo(
                    id=tid,
                    name=canonical.get("name", tid),
                    description=canonical.get("description", ""),
                    category=category,
                    icon=CATEGORY_ICONS.get(category, "📋"),
                    tags=tags,
                    node_count=len(canonical.get("nodes", {})),
                    version=str(raw.get("version", "1.0")),
                    source="yaml",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("yaml_template_load_error", file=str(yaml_file), error=str(e))

    def list_templates(self, category: str | None = None) -> list[dict[str, Any]]:
        if not self._loaded:
            self.load()
        infos = list(self._info_cache.values())
        if category:
            infos = [i for i in infos if i.category == category]
        return [i.to_dict() for i in sorted(infos, key=lambda x: x.name)]

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        if not self._loaded:
            self.load()
        return self._cache.get(template_id)

    def get_template_info(self, template_id: str) -> dict[str, Any] | None:
        if not self._loaded:
            self.load()
        info = self._info_cache.get(template_id)
        return info.to_dict() if info else None

    def list_categories(self) -> list[dict[str, str]]:
        if not self._loaded:
            self.load()
        counts: dict[str, int] = {}
        for info in self._info_cache.values():
            counts[info.category] = counts.get(info.category, 0) + 1
        return [
            {
                "id": cat,
                "label": CATEGORY_LABELS.get(cat, cat.title()),
                "icon": CATEGORY_ICONS.get(cat, "📋"),
                "count": count,
            }
            for cat, count in sorted(counts.items())
        ]

    def _infer_category(self, data: dict[str, Any]) -> str:
        tags = data.get("tags", []) or []
        for tag in tags:
            canonical = CATEGORY_ALIASES.get(tag, tag)
            if canonical in CATEGORY_LABELS:
                return canonical
        name_lower = str(data.get("name", "")).lower()
        desc_lower = str(data.get("description", "")).lower()
        combined = name_lower + " " + desc_lower
        for cat in CATEGORY_LABELS:
            if cat.replace("_", " ") in combined or cat in combined:
                return cat
        return "general"

    def _infer_icon(self, data: dict[str, Any]) -> str:
        cat = self._infer_category(data)
        return CATEGORY_ICONS.get(cat, "📋")


_service: TemplateService | None = None


def get_template_service() -> TemplateService:
    global _service
    if _service is None:
        _service = TemplateService()
        _service.load()
    return _service
