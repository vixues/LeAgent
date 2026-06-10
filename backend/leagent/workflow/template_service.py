"""Template service — loads, lists, and serves workflow templates.

Serves YAML templates under ``config/workflows/templates/``. Every
template file is authored directly in the **canonical** workflow
document shape that :func:`leagent.workflow.io.load` expects — files
that fail canonical validation are skipped with a warning. There is no
authoring DSL and no runtime migration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from leagent.workflow.io.loader import load as load_document

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

        self._load_yaml_templates()

        self._loaded = True
        logger.info(
            "templates_loaded",
            total=len(self._cache),
            yaml_dir=str(self._find_templates_dir()),
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

                # Template files are authored in the canonical document
                # shape; ``load_document`` hard-validates that.
                canonical = load_document(raw).to_dict()
                tid = canonical.get("id") or yaml_file.stem
                canonical["id"] = tid

                self._cache[tid] = canonical
                meta = canonical.get("metadata", {}) or {}
                category = meta.get("category") or self._infer_category(canonical)
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


_service: TemplateService | None = None


def get_template_service() -> TemplateService:
    global _service
    if _service is None:
        _service = TemplateService()
        _service.load()
    return _service
