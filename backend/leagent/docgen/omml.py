"""LaTeX → OMML (Office Math Markup Language) for native Office equations.

Word and PowerPoint render math from **OMML** (`<m:oMath>`) using their own
professional math engine — the result is editable, selectable, scales
perfectly, and matches the document font. This module turns a LaTeX string
into an OMML element tree with no image rasterisation.

Pipeline::

    LaTeX --latex2mathml--> MathML (Presentation) --this module--> OMML

The MathML → OMML step is a hand-written converter covering the constructs
that appear in real technical writing: fractions, radicals, sub/superscripts,
n-ary operators (∑ ∏ ∫ …) with limits, delimiters, matrices, accents, and
plain runs. Unknown elements degrade to their text content, so conversion
never raises — callers fall back to a vector/image render when this returns
``None``.
"""

from __future__ import annotations

from functools import lru_cache

import structlog

logger = structlog.get_logger(__name__)

# OMML + markup-compatibility namespaces.
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
_MATHML_NS = "http://www.w3.org/1998/Math/MathML"

# Large operators that become an OMML n-ary (limits above/below or as scripts).
_NARY_OPS = set("∑∏∐∫∬∭∮∯∰⨋⋃⋂⨀⨁⨂⋁⋀⨆⨅")
# Characters MathML emits as accents.
_ACCENTS = {"^", "ˆ", "~", "˜", "¯", "‾", "→", "⃗", "˙", "¨", "ˇ", "˘", "`", "´"}


def _q(tag: str) -> str:
    return f"{{{M_NS}}}{tag}"


def _localname(el: object) -> str:
    tag = getattr(el, "tag", "")
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _text_of(el: object) -> str:
    return ("".join(el.itertext()) if el is not None else "").strip()  # type: ignore[union-attr]


class _Builder:
    """Builds OMML elements (lxml) from a MathML tree."""

    def __init__(self) -> None:
        from lxml import etree

        self._etree = etree

    def el(self, tag: str, *children: object, root: bool = False) -> object:
        # Declare the ``m`` prefix once on the root; descendants reuse it.
        nsmap = {"m": M_NS} if root else None
        node = self._etree.Element(_q(tag), nsmap=nsmap)  # type: ignore[attr-defined]
        for child in children:
            if child is not None:
                node.append(child)  # type: ignore[union-attr]
        return node

    # -- leaf runs ------------------------------------------------------

    def run(self, text: str) -> object:
        r = self.el("r")
        t = self._etree.SubElement(r, _q("t"))  # type: ignore[attr-defined]
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = text
        return r

    def _wrap(self, tag: str, children: list[object]) -> object:
        """Create ``<m:tag>`` holding a run-sequence of ``children``."""
        node = self.el(tag)
        for child in children:
            node.append(child)  # type: ignore[union-attr]
        return node

    # -- MathML dispatch ------------------------------------------------

    def convert_seq(self, elements: list[object]) -> list[object]:
        out: list[object] = []
        for el in elements:
            out.extend(self.convert(el))
        return out

    def convert(self, el: object) -> list[object]:
        name = _localname(el)
        children = list(el)  # type: ignore[call-overload]

        if name in ("math", "mrow", "mstyle", "mpadded", "semantics"):
            return self.convert_seq(children)
        if name == "mphantom":
            return []
        if name in ("mi", "mn", "mo", "mtext", "ms"):
            text = (el.text or "").strip() or _text_of(el)  # type: ignore[union-attr]
            return [self.run(text)] if text else []
        if name == "mspace":
            return [self.run(" ")]
        if name == "mfrac":
            return [self._frac(children)]
        if name == "msqrt":
            return [self._radical(None, children)]
        if name == "mroot" and len(children) == 2:
            return [self._radical(children[1], [children[0]])]
        if name == "msup" and len(children) == 2:
            return [self._script("sSup", children[0], sup=children[1])]
        if name == "msub" and len(children) == 2:
            return [self._script("sSub", children[0], sub=children[1])]
        if name == "msubsup" and len(children) == 3:
            return [self._sub_sup(children[0], children[1], children[2])]
        if name == "munderover" and len(children) == 3:
            return [self._under_over(children[0], children[1], children[2])]
        if name == "munder" and len(children) == 2:
            return [self._under_over(children[0], children[1], None)]
        if name == "mover" and len(children) == 2:
            return [self._under_over(children[0], None, children[1])]
        if name in ("mtable",):
            return [self._matrix(children)]
        if name == "mfenced":
            return [self._delim(children, el)]

        # Unknown / unsupported: fall back to text content.
        text = _text_of(el)
        return [self.run(text)] if text else []

    def _e(self, elements: list[object]) -> object:
        return self._wrap("e", self.convert_seq(elements))

    def _frac(self, children: list[object]) -> object:
        f = self.el("f")
        f.append(self.el("fPr", self._val("type", "bar")))  # type: ignore[union-attr]
        num = self._wrap("num", self.convert(children[0]) if children else [])
        den = self._wrap(
            "den", self.convert(children[1]) if len(children) > 1 else []
        )
        f.append(num)  # type: ignore[union-attr]
        f.append(den)  # type: ignore[union-attr]
        return f

    def _radical(self, degree: object | None, body: list[object]) -> object:
        rad = self.el("rad")
        pr = self.el("radPr")
        if degree is None:
            pr.append(self._val("degHide", "1"))  # type: ignore[union-attr]
        rad.append(pr)  # type: ignore[union-attr]
        deg = self.el("deg")
        if degree is not None:
            for c in self.convert(degree):
                deg.append(c)  # type: ignore[union-attr]
        rad.append(deg)  # type: ignore[union-attr]
        rad.append(self._e(body))  # type: ignore[union-attr]
        return rad

    def _script(
        self,
        tag: str,
        base: object,
        *,
        sup: object | None = None,
        sub: object | None = None,
    ) -> object:
        node = self.el(tag)
        node.append(self._e([base]))  # type: ignore[union-attr]
        if sub is not None:
            node.append(self._wrap("sub", self.convert(sub)))  # type: ignore[union-attr]
        if sup is not None:
            node.append(self._wrap("sup", self.convert(sup)))  # type: ignore[union-attr]
        return node

    def _is_nary_base(self, base: object) -> str | None:
        if _localname(base) == "mo":
            ch = (base.text or "").strip()  # type: ignore[union-attr]
            if ch and ch in _NARY_OPS:
                return ch
        return None

    def _nary(
        self,
        chr_: str,
        sub: object | None,
        sup: object | None,
        *,
        und_ovr: bool,
    ) -> object:
        nary = self.el("nary")
        pr = self.el("naryPr")
        pr.append(self._val("chr", chr_))  # type: ignore[union-attr]
        pr.append(self._val("limLoc", "undOvr" if und_ovr else "subSup"))  # type: ignore[union-attr]
        if sub is None:
            pr.append(self._val("subHide", "1"))  # type: ignore[union-attr]
        if sup is None:
            pr.append(self._val("supHide", "1"))  # type: ignore[union-attr]
        nary.append(pr)  # type: ignore[union-attr]
        nary.append(self._wrap("sub", self.convert(sub) if sub is not None else []))  # type: ignore[union-attr]
        nary.append(self._wrap("sup", self.convert(sup) if sup is not None else []))  # type: ignore[union-attr]
        nary.append(self._wrap("e", []))  # operand follows as sibling runs
        return nary

    def _sub_sup(self, base: object, sub: object, sup: object) -> object:
        chr_ = self._is_nary_base(base)
        if chr_ is not None:
            return self._nary(chr_, sub, sup, und_ovr=False)
        node = self.el("sSubSup")
        node.append(self._e([base]))  # type: ignore[union-attr]
        node.append(self._wrap("sub", self.convert(sub)))  # type: ignore[union-attr]
        node.append(self._wrap("sup", self.convert(sup)))  # type: ignore[union-attr]
        return node

    def _under_over(
        self, base: object, under: object | None, over: object | None
    ) -> object:
        chr_ = self._is_nary_base(base)
        if chr_ is not None:
            return self._nary(chr_, under, over, und_ovr=True)
        # Accent (hat/bar/tilde) over a base → m:acc.
        if under is None and over is not None and _localname(over) == "mo":
            ch = (over.text or "").strip()  # type: ignore[union-attr]
            if ch in _ACCENTS:
                acc = self.el("acc")
                pr = self.el("accPr")
                pr.append(self._val("chr", ch))  # type: ignore[union-attr]
                acc.append(pr)  # type: ignore[union-attr]
                acc.append(self._e([base]))  # type: ignore[union-attr]
                return acc
        node = self.el("limUpp" if over is not None and under is None else "limLow")
        node.append(self._e([base]))  # type: ignore[union-attr]
        lim = over if over is not None else under
        node.append(self._wrap("lim", self.convert(lim) if lim is not None else []))  # type: ignore[union-attr]
        return node

    def _delim(self, children: list[object], el: object) -> object:
        d = self.el("d")
        pr = self.el("dPr")
        opener = el.get("open", "(")  # type: ignore[union-attr]
        closer = el.get("close", ")")  # type: ignore[union-attr]
        pr.append(self._val("begChr", opener))  # type: ignore[union-attr]
        pr.append(self._val("endChr", closer))  # type: ignore[union-attr]
        d.append(pr)  # type: ignore[union-attr]
        d.append(self._wrap("e", self.convert_seq(children)))  # type: ignore[union-attr]
        return d

    def _matrix(self, rows: list[object]) -> object:
        m = self.el("m")
        for tr in rows:
            if _localname(tr) != "mtr":
                continue
            mr = self.el("mr")
            for td in list(tr):  # type: ignore[call-overload]
                if _localname(td) != "mtd":
                    continue
                mr.append(self._e(list(td)))  # type: ignore[union-attr, call-overload]
            m.append(mr)  # type: ignore[union-attr]
        return m

    def _val(self, tag: str, value: str) -> object:
        node = self.el(tag)
        node.set(_q("val"), value)  # type: ignore[union-attr]
        return node


@lru_cache(maxsize=512)
def latex_to_omml_xml(latex: str, *, display: bool = False) -> str | None:
    """Convert one LaTeX expression to an OMML XML string.

    Returns the serialised ``<m:oMath>`` (or ``<m:oMathPara>`` when
    ``display``) element, or ``None`` if the expression cannot be parsed.
    """
    expr = latex.strip().strip("$").strip()
    if not expr:
        return None
    try:
        from latex2mathml.converter import convert
        from lxml import etree

        mathml = convert(expr)
        root = etree.fromstring(mathml.encode("utf-8"))  # noqa: S320 - trusted local
        builder = _Builder()
        omath = builder.el("oMath", root=not display)
        for child in builder.convert(root):
            omath.append(child)  # type: ignore[union-attr]
        if display:
            para = builder.el("oMathPara", omath, root=True)
            omath = para
        return etree.tostring(omath).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - never fail a render on bad math
        logger.debug("docgen_omml_convert_failed", latex=latex[:120], error=str(exc))
        return None


def latex_to_omml_element(latex: str, *, display: bool = False) -> object | None:
    """Convert LaTeX to a live lxml OMML element (for XML injection)."""
    xml = latex_to_omml_xml(latex, display=display)
    if xml is None:
        return None
    from lxml import etree

    return etree.fromstring(xml.encode("utf-8"))  # noqa: S320 - self-produced


def omml_pptx_alternate(latex: str, fallback_text: str, *, display: bool = False) -> object | None:
    """Wrap OMML in ``mc:AlternateContent`` for a DrawingML paragraph.

    PowerPoint 2010+ reads the ``a14`` choice (native equation); other
    renderers use the ``mc:Fallback`` run carrying ``fallback_text`` (the
    Unicode transliteration) so slides always show readable math.
    """
    omath_xml = latex_to_omml_xml(latex, display=display)
    if omath_xml is None:
        return None
    from lxml import etree

    nsmap = {"mc": MC_NS, "a": A_NS, "a14": A14_NS, "m": M_NS}
    alt = etree.Element(f"{{{MC_NS}}}AlternateContent", nsmap=nsmap)
    choice = etree.SubElement(alt, f"{{{MC_NS}}}Choice")
    choice.set("Requires", "a14")
    a14m = etree.SubElement(choice, f"{{{A14_NS}}}m")
    a14m.append(etree.fromstring(omath_xml.encode("utf-8")))  # noqa: S320

    fallback = etree.SubElement(alt, f"{{{MC_NS}}}Fallback")
    run = etree.SubElement(fallback, f"{{{A_NS}}}r")
    t = etree.SubElement(run, f"{{{A_NS}}}t")
    t.text = fallback_text
    return alt
