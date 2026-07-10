"""Chart block rendering (matplotlib → PNG bytes) for all document formats.

CJK-safe: applies :func:`leagent.code.matplotlib_cjk.configure_matplotlib_cjk`
before drawing so Chinese titles / labels never render as boxes.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from leagent.docgen.model import ChartBlock
    from leagent.docgen.themes import Theme

logger = structlog.get_logger(__name__)

_DEFAULT_DPI = 160


def render_chart_png(
    block: ChartBlock,
    theme: Theme,
    *,
    width_in: float = 6.4,
    height_in: float = 3.6,
    dpi: int = _DEFAULT_DPI,
    transparent: bool = False,
) -> bytes | None:
    """Render a chart block to PNG bytes. Returns None on failure."""
    try:
        import matplotlib

        matplotlib.use("Agg", force=False)
        from leagent.code.matplotlib_cjk import configure_matplotlib_cjk

        configure_matplotlib_cjk()
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001 - charts degrade to omission
        logger.warning("docgen_chart_matplotlib_unavailable", error=str(exc))
        return None

    series = [s for s in block.series if s.values]
    if not series:
        logger.warning("docgen_chart_no_series", title=block.title)
        return None

    palette = _series_palette(theme, len(series))
    text_color = theme.colors.text if not theme.deck.dark else theme.colors.text
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    try:
        _draw(ax, block, series, palette)

        if block.title:
            ax.set_title(block.title, color=text_color, fontsize=12, pad=12)
        if block.x_label and block.chart_type != "pie":
            ax.set_xlabel(block.x_label, color=text_color, fontsize=10)
        if block.y_label and block.chart_type != "pie":
            ax.set_ylabel(block.y_label, color=text_color, fontsize=10)

        if block.chart_type != "pie":
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.grid(axis="y", alpha=0.25, linewidth=0.6)
            ax.set_axisbelow(True)
            if len(series) > 1 or any(s.name for s in series):
                ax.legend(frameon=False, fontsize=9)

        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", transparent=transparent)
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("docgen_chart_render_failed", error=str(exc), title=block.title)
        return None
    finally:
        plt.close(fig)


def _draw(ax: Any, block: ChartBlock, series: list[Any], palette: list[str]) -> None:
    n = len(series)
    cats = block.categories or [str(i + 1) for i in range(len(series[0].values))]
    x = list(range(len(cats)))

    if block.chart_type == "pie":
        values = series[0].values[: len(cats)] if cats else series[0].values
        labels = cats[: len(values)] if cats else None
        ax.pie(
            values,
            labels=labels,
            colors=palette * (len(values) // len(palette) + 1),
            autopct="%1.1f%%",
            startangle=90,
            textprops={"fontsize": 9},
            wedgeprops={"linewidth": 1, "edgecolor": "white"},
        )
        ax.axis("equal")
        return

    if block.chart_type == "bar":
        width = 0.8 / n
        for idx, s in enumerate(series):
            offs = [xi + (idx - (n - 1) / 2) * width for xi in x[: len(s.values)]]
            ax.bar(offs, s.values, width=width, label=s.name, color=palette[idx % len(palette)])
        ax.set_xticks(x)
        ax.set_xticklabels(cats, fontsize=9)
        return

    if block.chart_type == "barh":
        height = 0.8 / n
        for idx, s in enumerate(series):
            offs = [xi + (idx - (n - 1) / 2) * height for xi in x[: len(s.values)]]
            ax.barh(offs, s.values, height=height, label=s.name, color=palette[idx % len(palette)])
        ax.set_yticks(x)
        ax.set_yticklabels(cats, fontsize=9)
        ax.invert_yaxis()
        return

    if block.chart_type == "scatter":
        for idx, s in enumerate(series):
            ax.scatter(
                x[: len(s.values)],
                s.values,
                label=s.name,
                color=palette[idx % len(palette)],
                s=36,
                alpha=0.85,
            )
        ax.set_xticks(x)
        ax.set_xticklabels(cats, fontsize=9)
        return

    # line / area
    for idx, s in enumerate(series):
        color = palette[idx % len(palette)]
        ax.plot(
            x[: len(s.values)],
            s.values,
            label=s.name,
            color=color,
            linewidth=2,
            marker="o",
            markersize=4,
        )
        if block.chart_type == "area":
            ax.fill_between(x[: len(s.values)], s.values, alpha=0.18, color=color)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=9)


def _series_palette(theme: Theme, n: int) -> list[str]:
    base = [
        theme.colors.primary,
        theme.colors.accent,
        theme.colors.secondary,
        "#7F8C8D",
        "#8E44AD",
        "#16A085",
        "#E67E22",
        "#2C3E50",
    ]
    # De-duplicate while preserving order (some themes repeat hues).
    seen: set[str] = set()
    out: list[str] = []
    for c in base:
        cl = c.lower()
        if cl not in seen:
            seen.add(cl)
            out.append(c)
    return out or ["#1F4E79"]
