"""Markdown → IR parser tests (blocks, directives, inline spans)."""

from __future__ import annotations

from leagent.docgen.markdown import parse_inline, parse_markdown_blocks
from leagent.docgen.model import (
    CalloutBlock,
    ChartBlock,
    CodeBlock,
    HeadingBlock,
    ListBlock,
    MetricsBlock,
    PageBreakBlock,
    ParagraphBlock,
    QuoteBlock,
    TableBlock,
    TocBlock,
)


def test_empty_input_returns_no_blocks() -> None:
    assert parse_markdown_blocks("") == []
    assert parse_markdown_blocks("   \n  ") == []


def test_headings_and_paragraphs() -> None:
    blocks = parse_markdown_blocks("# 报告标题\n\n## Section\n\n正文 with **bold**.")
    assert isinstance(blocks[0], HeadingBlock)
    assert blocks[0].text == "报告标题"
    assert blocks[0].level == 1
    assert isinstance(blocks[1], HeadingBlock)
    assert blocks[1].level == 2
    assert isinstance(blocks[2], ParagraphBlock)
    assert "**bold**" in blocks[2].text


def test_gfm_table() -> None:
    md = "| 名称 | 数量 |\n| --- | ---: |\n| 苹果 | 3 |\n| 梨 | 5 |\n"
    (block,) = parse_markdown_blocks(md)
    assert isinstance(block, TableBlock)
    assert block.columns == ["名称", "数量"]
    assert block.rows == [["苹果", "3"], ["梨", "5"]]
    assert block.align is not None
    assert block.align[1] == "right"


def test_task_list() -> None:
    (block,) = parse_markdown_blocks("- [x] done item\n- [ ] open item\n- plain\n")
    assert isinstance(block, ListBlock)
    assert [it.checked for it in block.items] == [True, False, None]
    assert block.items[0].text == "done item"


def test_nested_ordered_list() -> None:
    (block,) = parse_markdown_blocks("1. first\n2. second\n   1. child\n")
    assert isinstance(block, ListBlock)
    assert block.ordered is True
    assert block.items[1].children
    assert block.items[1].children[0].text == "child"


def test_fenced_code_block() -> None:
    (block,) = parse_markdown_blocks('```python\nprint("你好")\n```\n')
    assert isinstance(block, CodeBlock)
    assert block.language == "python"
    assert 'print("你好")' in block.code


def test_blockquote() -> None:
    (block,) = parse_markdown_blocks("> 名言警句\n")
    assert isinstance(block, QuoteBlock)
    assert "名言警句" in block.text


def test_callout_container_with_title() -> None:
    md = "::: warning 风险提示\n注意这个问题。\n:::\n"
    (block,) = parse_markdown_blocks(md)
    assert isinstance(block, CalloutBlock)
    assert block.variant == "warning"
    assert block.title == "风险提示"
    assert "注意这个问题" in block.text


def test_chart_fence_parses_to_chart_block() -> None:
    md = (
        "```chart\n"
        '{"chart_type": "bar", "title": "销量", '
        '"categories": ["Q1", "Q2"], '
        '"series": [{"name": "A", "values": [1, 2]}]}\n'
        "```\n"
    )
    (block,) = parse_markdown_blocks(md)
    assert isinstance(block, ChartBlock)
    assert block.chart_type == "bar"
    assert block.categories == ["Q1", "Q2"]
    assert block.series[0].values == [1, 2]


def test_metrics_fence_parses_to_metrics_block() -> None:
    md = '```metrics\n{"items": [{"label": "收入", "value": "¥1.2M", "delta": "+8%"}]}\n```\n'
    (block,) = parse_markdown_blocks(md)
    assert isinstance(block, MetricsBlock)
    assert block.items[0].label == "收入"


def test_invalid_chart_fence_degrades_to_code_block() -> None:
    (block,) = parse_markdown_blocks("```chart\nnot json at all {{{\n```\n")
    assert isinstance(block, CodeBlock)


def test_page_break_and_toc_directives() -> None:
    blocks = parse_markdown_blocks("first\n\n\\newpage\n\n[TOC]\n\nlast\n")
    kinds = [type(b) for b in blocks]
    assert PageBreakBlock in kinds
    assert TocBlock in kinds


def test_parse_inline_plain_roundtrip() -> None:
    spans = parse_inline("纯文本 no markers")
    assert len(spans) == 1
    assert spans[0].text == "纯文本 no markers"


def test_parse_inline_styles() -> None:
    spans = parse_inline("**bold** and `code` and [link](https://example.com)")
    bold = next(s for s in spans if s.bold)
    assert bold.text == "bold"
    code = next(s for s in spans if s.code)
    assert code.text == "code"
    link = next(s for s in spans if s.link)
    assert link.link == "https://example.com"
    assert link.text == "link"
