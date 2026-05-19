"""ChartGeneratorTool — professional-grade charts without full code_execution.

A higher-level tool that wraps matplotlib/plotly for common chart types with
professional defaults (typography, color palettes, axis formatting). Runs
chart generation in the code_execution subprocess sandbox for isolation.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

CHART_THEMES: dict[str, dict[str, Any]] = {
    "presentation": {
        "figsize": (12, 7),
        "dpi": 150,
        "font_family": "sans-serif",
        "font_size": 14,
        "title_size": 20,
        "palette": ["#2563EB", "#DC2626", "#16A34A", "#CA8A04", "#9333EA", "#0891B2"],
        "bg_color": "#FFFFFF",
        "grid_alpha": 0.3,
        "spine_visible": False,
    },
    "report": {
        "figsize": (8, 5),
        "dpi": 200,
        "font_family": "serif",
        "font_size": 11,
        "title_size": 14,
        "palette": ["#1F4E79", "#2E75B6", "#9DC3E6", "#ED7D31", "#A5A5A5", "#FFC000"],
        "bg_color": "#FFFFFF",
        "grid_alpha": 0.2,
        "spine_visible": True,
    },
    "dashboard": {
        "figsize": (10, 6),
        "dpi": 150,
        "font_family": "sans-serif",
        "font_size": 12,
        "title_size": 16,
        "palette": ["#6366F1", "#EC4899", "#14B8A6", "#F59E0B", "#8B5CF6", "#EF4444"],
        "bg_color": "#F8FAFC",
        "grid_alpha": 0.15,
        "spine_visible": False,
    },
    "minimal": {
        "figsize": (8, 5),
        "dpi": 150,
        "font_family": "sans-serif",
        "font_size": 11,
        "title_size": 13,
        "palette": ["#111111", "#555555", "#999999", "#CCCCCC", "#E5E5E5", "#F5F5F5"],
        "bg_color": "#FFFFFF",
        "grid_alpha": 0.1,
        "spine_visible": False,
    },
}


class ChartGeneratorTool(SyncTool):
    """Generate professional charts and visualizations.

    Produces high-quality analytical graphics with sensible defaults.
    Supports common chart types without requiring the user to write
    matplotlib/plotly code.
    """

    name = "chart_generator"
    description = (
        "Generate professional charts and visualizations. Supports bar, line, pie, "
        "scatter, heatmap, radar, area, and histogram chart types with built-in "
        "themes (presentation, report, dashboard, minimal). Returns the chart as "
        "a saved image file."
    )
    category = ToolCategory.GEN
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["create_chart", "plot", "visualize", "chart"]
    search_hint = "chart plot visualization bar line pie scatter heatmap graph"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000
    output_path_params = ("output_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "pie", "scatter", "heatmap", "radar", "area", "histogram", "horizontal_bar"],
                    "description": "Type of chart to generate.",
                },
                "data": {
                    "type": "object",
                    "description": "Chart data. Structure depends on chart_type.",
                    "properties": {
                        "categories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "X-axis categories / labels.",
                        },
                        "series": {
                            "type": "array",
                            "description": "Data series.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "values": {"type": "array", "items": {"type": "number"}},
                                },
                            },
                        },
                        "values": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Single series values (for pie/histogram).",
                        },
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Labels for pie chart slices.",
                        },
                        "x": {"type": "array", "items": {"type": "number"}, "description": "X values for scatter."},
                        "y": {"type": "array", "items": {"type": "number"}, "description": "Y values for scatter."},
                        "matrix": {
                            "type": "array",
                            "description": "2D matrix for heatmap.",
                            "items": {"type": "array", "items": {"type": "number"}},
                        },
                    },
                },
                "title": {
                    "type": "string",
                    "description": "Chart title.",
                },
                "x_label": {
                    "type": "string",
                    "description": "X-axis label.",
                },
                "y_label": {
                    "type": "string",
                    "description": "Y-axis label.",
                },
                "theme": {
                    "type": "string",
                    "enum": ["presentation", "report", "dashboard", "minimal"],
                    "description": "Visual theme (default: presentation).",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["png", "svg", "pdf"],
                    "description": "Output file format (default: png).",
                },
                "output_path": {
                    "type": "string",
                    "description": "Path to save the chart image.",
                },
                "show_legend": {
                    "type": "boolean",
                    "description": "Whether to show legend (default: true for multi-series).",
                },
                "stacked": {
                    "type": "boolean",
                    "description": "Stack bars/areas (default: false).",
                },
            },
            "required": ["chart_type", "data", "output_path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Generating chart"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        chart_type = params["chart_type"]
        data = params["data"]
        title = params.get("title", "")
        x_label = params.get("x_label", "")
        y_label = params.get("y_label", "")
        theme_name = params.get("theme", "presentation")
        output_format = params.get("output_format", "png")
        output_path = Path(params["output_path"])
        show_legend = params.get("show_legend")
        stacked = params.get("stacked", False)

        theme = CHART_THEMES.get(theme_name, CHART_THEMES["presentation"])

        output_path.parent.mkdir(parents=True, exist_ok=True)

        script = self._build_script(
            chart_type=chart_type,
            data=data,
            title=title,
            x_label=x_label,
            y_label=y_label,
            theme=theme,
            output_path=str(output_path),
            output_format=output_format,
            show_legend=show_legend,
            stacked=stacked,
        )

        result = self._run_in_sandbox(script, context)

        if not output_path.exists():
            return {
                "success": False,
                "error": result.get("stderr", "Chart generation failed — output file not created."),
                "stdout": result.get("stdout", ""),
            }

        file_size = output_path.stat().st_size
        logger.info(
            "chart_generated",
            chart_type=chart_type,
            theme=theme_name,
            output_path=str(output_path),
            file_size=file_size,
        )

        return {
            "success": True,
            "output_path": str(output_path),
            "file_size_bytes": file_size,
            "chart_type": chart_type,
            "format": output_format,
        }

    def _build_script(
        self,
        *,
        chart_type: str,
        data: dict[str, Any],
        title: str,
        x_label: str,
        y_label: str,
        theme: dict[str, Any],
        output_path: str,
        output_format: str,
        show_legend: bool | None,
        stacked: bool,
    ) -> str:
        data_json = json.dumps(data)
        theme_json = json.dumps(theme)

        return textwrap.dedent(f"""\
            import json
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            try:
                from leagent.services.code_execution.matplotlib_cjk import configure_matplotlib_cjk
                configure_matplotlib_cjk()
            except Exception:
                pass
            import numpy as np

            data = json.loads('''{data_json}''')
            theme = json.loads('''{theme_json}''')
            chart_type = {chart_type!r}
            title = {title!r}
            x_label = {x_label!r}
            y_label = {y_label!r}
            output_path = {output_path!r}
            output_format = {output_format!r}
            show_legend = {show_legend!r}
            stacked = {stacked!r}

            plt.rcParams['font.family'] = theme['font_family']
            plt.rcParams['font.size'] = theme['font_size']
            fig, ax = plt.subplots(figsize=tuple(theme['figsize']))
            fig.patch.set_facecolor(theme['bg_color'])
            ax.set_facecolor(theme['bg_color'])
            palette = theme['palette']

            categories = data.get('categories', [])
            series_list = data.get('series', [])
            values = data.get('values', [])
            labels = data.get('labels', categories)

            if chart_type == 'bar' or chart_type == 'horizontal_bar':
                x = np.arange(len(categories))
                width = 0.8 / max(len(series_list), 1)
                for i, s in enumerate(series_list):
                    offset = (i - len(series_list)/2 + 0.5) * width
                    if stacked:
                        bottom = np.zeros(len(categories))
                        for j in range(i):
                            bottom += np.array(series_list[j]['values'][:len(categories)])
                        if chart_type == 'horizontal_bar':
                            ax.barh(x, s['values'][:len(categories)], width*len(series_list), left=bottom, label=s.get('name',''), color=palette[i % len(palette)])
                        else:
                            ax.bar(x, s['values'][:len(categories)], width*len(series_list), bottom=bottom, label=s.get('name',''), color=palette[i % len(palette)])
                    else:
                        if chart_type == 'horizontal_bar':
                            ax.barh(x + offset, s['values'][:len(categories)], width, label=s.get('name',''), color=palette[i % len(palette)])
                        else:
                            ax.bar(x + offset, s['values'][:len(categories)], width, label=s.get('name',''), color=palette[i % len(palette)])
                if chart_type == 'horizontal_bar':
                    ax.set_yticks(x)
                    ax.set_yticklabels(categories)
                else:
                    ax.set_xticks(x)
                    ax.set_xticklabels(categories, rotation=45 if len(categories) > 6 else 0, ha='right' if len(categories) > 6 else 'center')

            elif chart_type == 'line' or chart_type == 'area':
                for i, s in enumerate(series_list):
                    vals = s['values'][:len(categories)] if categories else s['values']
                    xs = categories if categories else list(range(len(vals)))
                    if chart_type == 'area':
                        ax.fill_between(range(len(vals)), vals, alpha=0.3, color=palette[i % len(palette)])
                    ax.plot(range(len(vals)), vals, label=s.get('name',''), color=palette[i % len(palette)], linewidth=2, marker='o', markersize=4)
                if categories:
                    ax.set_xticks(range(len(categories)))
                    ax.set_xticklabels(categories, rotation=45 if len(categories) > 6 else 0, ha='right' if len(categories) > 6 else 'center')

            elif chart_type == 'pie':
                pie_values = values if values else (series_list[0]['values'] if series_list else [])
                pie_labels = labels if labels else [f'Slice {{i+1}}' for i in range(len(pie_values))]
                colors = palette[:len(pie_values)]
                ax.pie(pie_values, labels=pie_labels, colors=colors, autopct='%1.1f%%', startangle=90)
                ax.set_aspect('equal')

            elif chart_type == 'scatter':
                x_vals = data.get('x', [])
                y_vals = data.get('y', [])
                ax.scatter(x_vals, y_vals, c=palette[0], alpha=0.7, s=50)

            elif chart_type == 'heatmap':
                matrix = np.array(data.get('matrix', [[]]))
                im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto')
                fig.colorbar(im, ax=ax)
                if categories:
                    ax.set_xticks(range(len(categories)))
                    ax.set_xticklabels(categories, rotation=45, ha='right')
                row_labels = data.get('row_labels', [])
                if row_labels:
                    ax.set_yticks(range(len(row_labels)))
                    ax.set_yticklabels(row_labels)

            elif chart_type == 'histogram':
                hist_values = values if values else (series_list[0]['values'] if series_list else [])
                ax.hist(hist_values, bins='auto', color=palette[0], edgecolor='white', alpha=0.8)

            elif chart_type == 'radar':
                if series_list and categories:
                    angles = np.linspace(0, 2*np.pi, len(categories), endpoint=False).tolist()
                    angles += angles[:1]
                    ax.remove()
                    ax = fig.add_subplot(111, polar=True)
                    for i, s in enumerate(series_list):
                        vals = s['values'][:len(categories)]
                        vals += vals[:1]
                        ax.plot(angles, vals, color=palette[i % len(palette)], linewidth=2, label=s.get('name',''))
                        ax.fill(angles, vals, color=palette[i % len(palette)], alpha=0.1)
                    ax.set_xticks(angles[:-1])
                    ax.set_xticklabels(categories)

            if title:
                ax.set_title(title, fontsize=theme['title_size'], fontweight='bold', pad=12)
            if x_label:
                ax.set_xlabel(x_label)
            if y_label:
                ax.set_ylabel(y_label)

            if not theme.get('spine_visible', True) and chart_type not in ('pie', 'radar'):
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)

            if chart_type not in ('pie', 'radar', 'heatmap'):
                ax.grid(True, alpha=theme.get('grid_alpha', 0.2))

            has_multi = len(series_list) > 1
            if show_legend is True or (show_legend is None and has_multi):
                ax.legend(framealpha=0.9, edgecolor='none')

            plt.tight_layout()
            plt.savefig(output_path, format=output_format, dpi=theme['dpi'], bbox_inches='tight', facecolor=fig.get_facecolor())
            plt.close()
            print(f"Chart saved: {{output_path}}")
        """)

    def _run_in_sandbox(self, script: str, context: ToolContext) -> dict[str, Any]:
        """Execute the chart script via the code_execution subprocess sandbox."""
        try:
            from leagent.services.code_execution import SubprocessSandbox, Workspace, WorkspaceManager

            workspace_root = "/tmp/leagent-charts"
            Path(workspace_root).mkdir(parents=True, exist_ok=True)
            session_id = str(context.session_id or "chart-session")
            mgr = WorkspaceManager(root=workspace_root)
            ws = mgr.get_or_create(session_id)

            sandbox = SubprocessSandbox()
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    result = pool.submit(
                        asyncio.run,
                        sandbox.execute(
                            source=script,
                            workspace=ws,
                            timeout_sec=self.timeout_sec,
                            import_tier="extended",
                        ),
                    ).result()
            else:
                result = asyncio.run(
                    sandbox.execute(
                        source=script,
                        workspace=ws,
                        timeout_sec=self.timeout_sec,
                        import_tier="extended",
                    )
                )
            return {
                "status": result.status,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except Exception as e:
            logger.warning("chart_sandbox_fallback", error=str(e))
            return self._run_direct(script)

    def _run_direct(self, script: str) -> dict[str, Any]:
        """Fallback: run script directly in-process (less isolated)."""
        import subprocess
        import sys

        try:
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
            )
            return {
                "status": "ok" if proc.returncode == 0 else "error",
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except Exception as e:
            return {"status": "error", "stdout": "", "stderr": str(e)}
