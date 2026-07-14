"""Relevance-gated policy sources.

These sources reuse the existing ``policies/<name>.md`` templates as the single
source of truth, but only inject them into the system prompt when the turn is
actually about their domain (decided by a :class:`~leagent.context.relevance.RelevanceGate`).
This keeps heavy, domain-specific manuals (canvas/GenUI rules, document-font
guidance) out of the always-on prompt while still delivering them automatically
the moment a relevant turn arrives — or when the runtime harness opts in.

Contrast with :mod:`leagent.context.sources.policies`, which loads the small,
universally-relevant policies (``file_access``, ``database_tool``, ``human_gate``)
on every turn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import structlog

from leagent.context.relevance import RelevanceGate
from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.policies import _get_enabled_tool_names, _substitute
from leagent.context.types import ContextBlock, ContextScope, RenderTarget

if TYPE_CHECKING:
    from leagent.context.sources.base import ResolveContext

logger = structlog.get_logger(__name__)


class GatedPolicySource:
    """Base class: load a fixed set of policy snippets only when relevant.

    Subclasses set :attr:`id`, :attr:`priority`, :attr:`gate`, and
    :attr:`policy_names`. The block is assembled from the existing
    ``policies/<name>`` markdown templates, with template-variable substitution
    and the same ``requires_tools`` filtering used by the always-on policies
    source.
    """

    kind: str = "identity"
    scope: ContextScope = ContextScope.TURN
    weight: float = 1.0
    render_target: RenderTarget = RenderTarget.SYSTEM

    # Subclass overrides
    id: ClassVar[str] = ""
    priority: ClassVar[int] = 1100
    gate: ClassVar[RelevanceGate] = RelevanceGate(name="")
    policy_names: ClassVar[tuple[str, ...]] = ()

    def _is_relevant(self, ctx: ResolveContext) -> bool:
        return self.gate.matches(
            ctx.query,
            workflow_hint=ctx.workflow_hint,
            template_vars=ctx.template_vars,
        )

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"{self.id}:{self._is_relevant(ctx)}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            if not self._is_relevant(ctx):
                return None
            if ctx.prompt_registry is None:
                logger.warning("gated_policy_resolve_no_registry", source=self.id)
                return None

            variables = {
                "agent_name": ctx.agent_id,
                "cwd": ctx.cwd,
                **ctx.template_vars,
            }
            enabled_tool_names = _get_enabled_tool_names(ctx)

            bodies: list[str] = []
            for policy_name in self.policy_names:
                try:
                    policy = ctx.prompt_registry.get(
                        f"policies/{policy_name}",
                        variant="default",
                    )
                except Exception:
                    logger.warning(
                        "gated_policy_snippet_missing",
                        source=self.id,
                        policy=policy_name,
                    )
                    continue

                if (
                    policy.requires_tools
                    and enabled_tool_names is not None
                    and not any(t in enabled_tool_names for t in policy.requires_tools)
                ):
                    logger.debug(
                        "gated_policy_skipped_missing_tools",
                        source=self.id,
                        policy=policy_name,
                        requires=policy.requires_tools,
                    )
                    continue

                body = _substitute(policy.body, variables).strip()
                if body:
                    bodies.append(body)

            if not bodies:
                return None

            body = "\n\n".join(bodies)
            return ContextBlock(
                source_id=self.id,
                kind=self.kind,
                render_target=self.render_target,
                body=body,
                tokens=ContextBlock.approx_tokens(body),
                cost=ContextBlock.approx_tokens(body),
                signature=ContextBlock.content_signature(self.id, body),
                priority=self.priority,
                weight=self.weight,
                metadata={"count": len(bodies), "gated": True},
            )
        except Exception:
            logger.exception("gated_policy_resolve_failed", source=self.id)
            return None


class CanvasGuideSource(GatedPolicySource):
    """Canvas / GenUI authoring rules, loaded only for visual-deliverable turns."""

    id = "canvas_guide"
    priority = 1150
    policy_names = (
        "canvas_routing",
        "genui_components",
        "blob_staging",
    )
    gate = RelevanceGate(
        name="canvas_guide",
        hints=(
            "canvas",
            "genui",
            "gen ui",
            "dashboard",
            "poster",
            "slide",
            "deck",
            "chart",
            "kpi",
            "emit_ui_tree",
            "emit_ui_patch",
            "canvas_publish",
            "htmlframe",
            "html frame",
            "html mode",
            "html 模式",
            "webpage",
            "web page",
            "landing page",
            "网页",
            "落地页",
            "画布",
            "卡片",
            "看板",
            "海报",
            "仪表盘",
            "幻灯片",
            "图表",
        ),
        opt_in_keys=("canvas_guide", "enable_canvas"),
    )


CANVAS_INTENT_MAX_OUTPUT_TOKENS = 32_768


def resolve_canvas_intent_max_output_tokens(
    query: str | None,
    *,
    base: int | None,
) -> int | None:
    """Bump ``max_output_tokens`` when the turn matches canvas/GenUI intent.

    Reuses :class:`CanvasGuideSource`'s ``RelevanceGate`` keyword list so the
    first ``canvas_publish`` is less likely to hit output-length truncation.
    """
    if not CanvasGuideSource.gate.matches(query or ""):
        return base
    if base is None:
        return CANVAS_INTENT_MAX_OUTPUT_TOKENS
    return max(base, CANVAS_INTENT_MAX_OUTPUT_TOKENS)


class ChartGuideSource(GatedPolicySource):
    """Professional chart mode guide, loaded only for chart/visualization turns."""

    id = "chart_guide"
    priority = 1140
    policy_names = ("chart_guide",)
    gate = RelevanceGate(
        name="chart_guide",
        hints=(
            "chart",
            "plot",
            "graph",
            "visualiz",
            "visualis",
            "histogram",
            "boxplot",
            "box plot",
            "violin",
            "heatmap",
            "scatter",
            "candlestick",
            "waterfall",
            "sankey",
            "treemap",
            "sunburst",
            "funnel",
            "gauge",
            "pareto",
            "radar",
            "contour",
            "regression",
            "ecdf",
            "prochart",
            "chart_generator",
            "图表",
            "画图",
            "绘图",
            "可视化",
            "柱状图",
            "折线图",
            "饼图",
            "散点图",
            "直方图",
            "箱线图",
            "小提琴图",
            "热力图",
            "K线",
            "k线",
            "蜡烛图",
            "瀑布图",
            "桑基图",
            "漏斗图",
            "雷达图",
            "仪表盘图",
        ),
        opt_in_keys=("chart_guide", "enable_charts"),
    )


class DocumentFontsSource(GatedPolicySource):
    """Mixed CJK/Latin font guidance, loaded only for document-generation turns."""

    id = "document_fonts"
    priority = 1100
    policy_names = ("document_fonts",)
    gate = RelevanceGate(
        name="document_fonts",
        hints=(
            "pdf",
            "docx",
            "pptx",
            "xlsx",
            "excel",
            "word document",
            "powerpoint",
            "reportlab",
            "font",
            "字体",
            "报告",
            "文档",
            "幻灯片",
            "document_generate",
            "slides_generate",
            "excel_generator",
        ),
        opt_in_keys=("document_fonts", "enable_fonts"),
    )


class DocumentGenerationSource(GatedPolicySource):
    """Document/slide authoring quality guide, loaded for doc-generation turns."""

    id = "document_generation"
    priority = 1105
    policy_names = ("document_generation",)
    gate = RelevanceGate(
        name="document_generation",
        hints=(
            "pdf",
            "docx",
            "pptx",
            "word document",
            "powerpoint",
            "presentation",
            "slide",
            "deck",
            "report",
            "whitepaper",
            "proposal",
            "document_generate",
            "slides_generate",
            "theme_designer",
            "document_template",
            "报告",
            "文档",
            "白皮书",
            "方案书",
            "幻灯片",
            "演示文稿",
            "简报",
            "模板",
            "主题",
        ),
        opt_in_keys=("document_generation", "enable_docgen"),
    )


class EmailToolSource(GatedPolicySource):
    """Outbound SMTP settings and sending — loaded for mail-related turns."""

    id = "email_tool"
    priority = 1100
    policy_names = ("email_tool",)
    gate = RelevanceGate(
        name="email_tool",
        hints=(
            "email",
            "e-mail",
            "mail",
            "smtp",
            "outbound mail",
            "send email",
            "mail settings",
            "mail config",
            "email config",
            "发件",
            "发信",
            "邮件",
            "邮箱",
            "smtp",
            "邮件配置",
            "邮件设置",
            "发件邮箱",
            "测试邮件",
            "邮件连接",
            "LEAGENT_SMTP",
        ),
        opt_in_keys=("email_tool", "enable_email"),
    )


class SettingsSetupSource(GatedPolicySource):
    """Env secrets / MCP / channels setup via configure_settings."""

    id = "settings_setup"
    priority = 1100
    policy_names = ("settings_setup",)
    gate = RelevanceGate(
        name="settings_setup",
        hints=(
            "configure",
            "configuration",
            "settings",
            "api key",
            "api_key",
            "secret",
            "token",
            "mcp",
            "mcp server",
            "dingtalk",
            "feishu",
            "lark",
            "wechat work",
            "wecom",
            "webhook",
            "smtp",
            "web search",
            "bing",
            "searxng",
            "deepseek",
            "openai key",
            "anthropic",
            "dashscope",
            "configure_settings",
            "环境密钥",
            "环境变量",
            "配置",
            "设置",
            "密钥",
            "api密钥",
            "飞书",
            "钉钉",
            "企微",
            "企业微信",
            "联网搜索",
            "网页搜索",
            "mcp服务器",
        ),
        opt_in_keys=("settings_setup", "enable_settings_setup"),
    )


class StructuredOutputElicitationSource(GatedPolicySource):
    """Ask blocking layout/business params before underspecified spreadsheet/report gen."""

    id = "structured_output_elicitation"
    priority = 1110
    policy_names = ("structured_output_elicitation",)
    gate = RelevanceGate(
        name="structured_output_elicitation",
        hints=(
            "签到表",
            "考勤",
            "attendance",
            "spreadsheet",
            "excel",
            "xlsx",
            "excel_generator",
            "报表",
            "填表",
            "差旅",
            "报销",
            "采购审核",
            "audit",
            "审核",
            "generate table",
            "fill template",
            "打印",
            "行高",
            "sign-in sheet",
            "attendance sheet",
        ),
        opt_in_keys=(
            "structured_output_elicitation",
            "enable_structured_elicitation",
        ),
    )


SOURCE_REGISTRY[CanvasGuideSource.id] = CanvasGuideSource
SOURCE_REGISTRY[ChartGuideSource.id] = ChartGuideSource
SOURCE_REGISTRY[DocumentFontsSource.id] = DocumentFontsSource
SOURCE_REGISTRY[DocumentGenerationSource.id] = DocumentGenerationSource
SOURCE_REGISTRY[EmailToolSource.id] = EmailToolSource
SOURCE_REGISTRY[SettingsSetupSource.id] = SettingsSetupSource
SOURCE_REGISTRY[StructuredOutputElicitationSource.id] = StructuredOutputElicitationSource
