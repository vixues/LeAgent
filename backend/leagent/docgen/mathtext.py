"""LaTeX math rendering for the document generation subsystem.

Formulas render through **matplotlib mathtext** — a self-contained LaTeX
subset engine (no TeX installation required) that covers fractions, roots,
sums/integrals/limits, Greek letters, operators, accents, matrices-lite,
sub/superscripts, and \\mathbb / \\mathcal styles.

matplotlib mathtext is a real TeX-style box-and-glue typesetting engine, so
the layout it produces is professional; the question is only how each output
format *embeds* that layout. This module exposes both options:

- :func:`math_vector_path` — the laid-out equation as **vector geometry**
  (Bézier outlines + bar rectangles) in points, for crisp, scalable,
  resolution-independent embedding (used by the PDF renderer as real
  ReportLab paths — no rasterisation).
- :func:`render_math_png` — the same layout rasterised to a transparent PNG
  with baseline metrics, kept as a portable fallback (and for HTML).
- :func:`latex_lines` — normalises multi-line / AMS environments
  (``align``, ``aligned``, ``gather``, ``cases``, …) into renderable rows.
- :func:`latex_to_unicode` — best-effort plain-text fallback (Greek
  letters, super/subscripts, operators) for text-only contexts and for
  render failures.

Native Office equations (Word / PowerPoint OMML) are produced separately by
:mod:`leagent.docgen.omml`; this module is the raster/vector plane.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from functools import lru_cache

import structlog

logger = structlog.get_logger(__name__)

# Default display color; renderers pass the theme text color.
_DEFAULT_COLOR = "#333333"


@dataclass
class MathVector:
    """Vector geometry for one laid-out equation, in typographic points.

    Coordinates use a text-style origin: ``y`` increases upward from the
    baseline, so glyph/rect ``y`` values are already baseline-relative
    (negative ``y`` extends below the baseline). ``depth`` is how far the
    equation descends below the baseline; ``height`` is the full box height.
    """

    width: float
    height: float
    depth: float
    # Each contour: list of (op, points) where op is "m"/"l"/"c" and points
    # are (x, y) tuples already scaled to points.
    contours: list[list[tuple[str, tuple[float, ...]]]] = field(default_factory=list)
    # Filled bars (fraction/radical rules): (x, y, w, h) in points.
    rects: list[tuple[float, float, float, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PNG rendering (matplotlib mathtext)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=512)
def math_vector_path(latex: str, *, font_size: float = 11.0) -> MathVector | None:
    """Lay out one LaTeX expression as scalable vector geometry.

    Uses matplotlib's :class:`~matplotlib.textpath.TextPath`, which runs the
    mathtext engine and returns glyph outlines *and* fraction/radical bars as
    a single vector path (points at ``font_size``). Quadratic segments are
    promoted to cubic Béziers so callers (ReportLab) can draw them directly.
    Returns ``None`` when the expression cannot be parsed.
    """
    expr = latex.strip().strip("$").strip()
    if not expr:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg", force=False)
        from matplotlib.path import Path
        from matplotlib.textpath import TextPath

        tp = TextPath((0.0, 0.0), f"${expr}$", size=font_size)
        verts = tp.vertices
        codes = tp.codes
        if len(verts) == 0:
            return None

        xs = verts[:, 0]
        ys = verts[:, 1]
        x_min = float(xs.min())
        y_min = float(ys.min())
        y_max = float(ys.max())
        contours: list[list[tuple[str, tuple[float, ...]]]] = []
        current: list[tuple[str, tuple[float, ...]]] = []
        cur_pt = (0.0, 0.0)
        i = 0
        n = len(verts)
        while i < n:
            code = codes[i]
            if code == Path.MOVETO:
                if current:
                    contours.append(current)
                x, y = float(verts[i, 0]) - x_min, float(verts[i, 1])
                current = [("m", (x, y))]
                cur_pt = (x, y)
                i += 1
            elif code == Path.LINETO:
                x, y = float(verts[i, 0]) - x_min, float(verts[i, 1])
                current.append(("l", (x, y)))
                cur_pt = (x, y)
                i += 1
            elif code == Path.CURVE3:
                qx, qy = float(verts[i, 0]) - x_min, float(verts[i, 1])
                ex, ey = float(verts[i + 1, 0]) - x_min, float(verts[i + 1, 1])
                # Quadratic (P0,Q,P2) → cubic control points.
                p0x, p0y = cur_pt
                c1x = p0x + 2.0 / 3.0 * (qx - p0x)
                c1y = p0y + 2.0 / 3.0 * (qy - p0y)
                c2x = ex + 2.0 / 3.0 * (qx - ex)
                c2y = ey + 2.0 / 3.0 * (qy - ey)
                current.append(("c", (c1x, c1y, c2x, c2y, ex, ey)))
                cur_pt = (ex, ey)
                i += 2
            elif code == Path.CURVE4:
                c1x, c1y = float(verts[i, 0]) - x_min, float(verts[i, 1])
                c2x, c2y = float(verts[i + 1, 0]) - x_min, float(verts[i + 1, 1])
                ex, ey = float(verts[i + 2, 0]) - x_min, float(verts[i + 2, 1])
                current.append(("c", (c1x, c1y, c2x, c2y, ex, ey)))
                cur_pt = (ex, ey)
                i += 3
            elif code == Path.CLOSEPOLY:
                current.append(("z", ()))
                i += 1
            else:
                i += 1
        if current:
            contours.append(current)
        if not contours:
            return None
        return MathVector(
            width=float(xs.max()) - x_min,
            height=y_max - y_min,
            depth=max(0.0, -y_min),
            contours=contours,
        )
    except Exception as exc:  # noqa: BLE001 - invalid LaTeX must never fail a render
        logger.debug("docgen_math_vector_failed", latex=latex[:120], error=str(exc))
        return None


@lru_cache(maxsize=512)
def render_math_png(
    latex: str,
    *,
    font_size: float = 11.0,
    color: str = _DEFAULT_COLOR,
    dpi: int = 220,
) -> tuple[bytes, float, float, float] | None:
    """Render one LaTeX expression to a transparent PNG.

    Returns ``(png_bytes, width_pt, height_pt, depth_pt)`` where the values
    are in points at ``font_size`` (depth = distance the image extends below
    the text baseline), or ``None`` when the expression cannot be parsed.
    """
    expr = latex.strip().strip("$").strip()
    if not expr:
        return None
    s = f"${expr}$"
    try:
        import matplotlib

        matplotlib.use("Agg", force=False)
        from matplotlib import mathtext
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        from matplotlib.font_manager import FontProperties

        prop = FontProperties(size=font_size)
        parser = mathtext.MathTextParser("path")
        width, height, depth, _, _ = parser.parse(s, dpi=72, prop=prop)
        if width <= 0 or height <= 0:
            return None

        fig = Figure(figsize=(width / 72.0, height / 72.0))
        FigureCanvasAgg(fig)
        fig.patch.set_alpha(0.0)
        fig.text(0, depth / height, s, fontproperties=prop, color=color)
        buf = io.BytesIO()
        fig.savefig(buf, dpi=dpi, format="png", transparent=True)
        return buf.getvalue(), float(width), float(height), float(depth)
    except Exception as exc:  # noqa: BLE001 - invalid LaTeX must never fail a render
        logger.debug("docgen_mathtext_parse_failed", latex=latex[:120], error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Multi-line / AMS environment normalisation
# ---------------------------------------------------------------------------

_ENV_RE = re.compile(r"\\(?:begin|end)\{[a-zA-Z]+\*?\}")
_ROW_SPLIT_RE = re.compile(r"\\\\")


def latex_lines(latex: str) -> list[str]:
    """Split a (possibly multi-line AMS) expression into renderable rows.

    Environment wrappers are stripped, alignment tabs (``&``) removed, and
    rows split on ``\\\\`` — mathtext renders one line at a time.
    """
    s = _ENV_RE.sub("", latex.strip().strip("$"))
    s = s.replace("&", " ")
    rows = [row.strip() for row in _ROW_SPLIT_RE.split(s)]
    return [row for row in rows if row] or [s.strip() or latex.strip()]


# ---------------------------------------------------------------------------
# Unicode fallback
# ---------------------------------------------------------------------------

_COMMANDS = {
    # Greek
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι",
    "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω",
    # Operators / relations
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓",
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠",
    "approx": "≈", "sim": "∼", "equiv": "≡", "propto": "∝",
    "rightarrow": "→", "to": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "Leftarrow": "⇐", "leftrightarrow": "↔", "infty": "∞",
    "partial": "∂", "nabla": "∇", "sum": "∑", "prod": "∏", "int": "∫",
    "sqrt": "√", "in": "∈", "notin": "∉", "subset": "⊂", "subseteq": "⊆",
    "cup": "∪", "cap": "∩", "forall": "∀", "exists": "∃", "emptyset": "∅",
    "angle": "∠", "perp": "⊥", "parallel": "∥", "degree": "°",
    "ldots": "…", "cdots": "⋯", "dots": "…", "prime": "′",
    # Spacing / structure — drop
    "quad": " ", "qquad": "  ", ",": " ", ";": " ", "!": "", "left": "",
    "right": "", "displaystyle": "", "limits": "",
}

_SUPERSCRIPTS = str.maketrans(
    "0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ"
)
_SUBSCRIPTS = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")

_FRAC_RE = re.compile(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}")
_TEXT_RE = re.compile(r"\\(?:text|mathrm|mathit|mathbf|operatorname)\{([^{}]*)\}")
_CMD_RE = re.compile(r"\\([a-zA-Z]+|[,;!])")
_SUP_RE = re.compile(r"\^\{([^{}]*)\}|\^(\S)")
_SUB_RE = re.compile(r"_\{([^{}]*)\}|_(\S)")


def latex_to_unicode(latex: str) -> str:
    """Best-effort LaTeX → plain Unicode (fallback for text-only contexts)."""
    s = latex.strip().strip("$")
    s = _ENV_RE.sub("", s).replace("&", " ")
    s = _ROW_SPLIT_RE.sub("; ", s)
    # Structures first (innermost-out for shallow nesting).
    for _ in range(3):
        new = _FRAC_RE.sub(lambda m: f"({m.group(1)})/({m.group(2)})", s)
        new = _TEXT_RE.sub(lambda m: m.group(1), new)
        if new == s:
            break
        s = new
    s = _CMD_RE.sub(lambda m: _COMMANDS.get(m.group(1), m.group(1)), s)

    def _sup(m: re.Match[str]) -> str:
        body = m.group(1) if m.group(1) is not None else m.group(2)
        converted = body.translate(_SUPERSCRIPTS)
        return converted if converted != body or len(body) <= 2 else f"^({body})"

    def _sub(m: re.Match[str]) -> str:
        body = m.group(1) if m.group(1) is not None else m.group(2)
        converted = body.translate(_SUBSCRIPTS)
        return converted if converted != body or len(body) <= 2 else f"_({body})"

    s = _SUP_RE.sub(_sup, s)
    s = _SUB_RE.sub(_sub, s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s{2,}", " ", s).strip()
