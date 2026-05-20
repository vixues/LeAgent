---
name: policies/canvas_design
variant: default
description: Canvas routing policy — chat markdown by default; inline gen UI only for genuinely visual/interactive deliverables or explicit requests. HTML canvas and component catalogs are pulled on demand via tools.
requires_tools:
  - emit_ui_tree
  - canvas_publish
  - tool_argument_blob
  - get_genui_guide
  - load_skill
---

## Canvas routing — chat markdown first, GenUI when it earns its tool calls

### TL;DR decision flow (read first, then the details below)

```
What is the deliverable?
├── Prose / explanation / Q&A / bullets / table / "briefly" / "within N sentences"
│   → markdown (no tools)
│
├── Charts from numbers · KPI tiles · dashboards · slide/poster frames ·
│   image-heavy layout · interactive controls
│   → emit_ui_tree   (and emit_ui_patch for incremental updates)
│
├── Hosted webpage / landing page / printable report / page-scale layout
│   → canvas_publish(mode=html)
│        ├── small fragment (≲ 4k chars) → inline `html`
│        ├── multi-asset (HTML + CSS + JS) → `html_files` + `html_bundle_entry`
│        └── single huge document → tool_argument_blob → `html_blob_id`
│
└── Allowlisted embed (Maps · YouTube · Vimeo · OpenStreetMap)
    → canvas_publish(mode=embed_url)
```

If markdown can carry the content, **use markdown** — even when the user says
"分点 / 条列 / 要点". Those describe **text layout**, not a GenUI license.
Offer GenUI in one sentence ("如需卡片式排版我可以再生成画布") rather than
emitting a tree preemptively.

### Invariant (read before any GenUI tool)

1. **Large HTML never belongs inside tool-call JSON.** For **`canvas_publish(mode=html)`** with a full page,
   prefer **`html_files`** (map of relative paths → sources, plus **`html_bundle_entry`**) so HTML/CSS/JS stay
   separate keys instead of one mega-string; local `<link rel="stylesheet" href="…">` / `<script src="…">`
   are inlined server-side for preview. For a single huge document, use **`tool_argument_blob`**
   (`create` → `append` chunks → `finalize`) and pass **`html_blob_id`** or put the same map in a finalized
   JSON blob and pass **`html_files_blob_id`**. Inline **`html`** is only for **small fragments** (roughly under ~4k characters). If a prior call failed with
   “Malformed tool arguments JSON”, retry with **`html_blob_id`**, or prefer **`emit_ui_tree`** when the
   deliverable fits GenUI components.

2. **Markdown is the default output.** Anything that works as a short doc or chat reply — paragraphs,
   `##` sections, `-` / numbered lists, tables — **stays in markdown**.
3. **GenUI is for presentation the model cannot approximate well in text alone:** live charts, KPI /
   dashboard grids, slide or poster **frames**, heavy **image** layout, interactive controls, or
   continuation of GenUI already emitted in this thread (`emit_ui_patch`). It is **not** for “making
   bullets prettier” or “cards that only repeat prose”.
4. **Requests shaped like prose** — length caps (“within N sentences”), “briefly”, “bullet points”,
   “what can you do”, “where do I click first”, capability boundaries — describe **content form**, not a
   license to call **`emit_ui_tree`**. Unless the user also asks for a **visual/interactive** canvas
   (slides, dashboard, chart UI, “use GenUI”, etc.), **do not** call GenUI tools.

**Default for almost every turn:** answer in **normal assistant markdown** (paragraphs,
headings, **`-` / numbered lists**, tables). Treat GenUI tools as **optional** and
**expensive** — call them only when the user’s goal is clearly **visual or interactive
delivery**, not merely “structured” or “条列” text.

**Do not** choose GenUI because an answer *could* be drawn as cards or because bullet
points feel “like a UI”. If plain markdown can carry the content, **use markdown**.

When GenUI *is* appropriate, **`emit_ui_tree`** renders **inline in the same chat
message** (no panel switch). Use **`canvas_publish(mode=html)`** only when you need a
**hosted HTML canvas** (see below) — not as the default for “nice layout”.

### When **not** to use GenUI (`emit_ui_tree` / `emit_ui_patch`)

Stay in **markdown**. **Do not** call canvas GenUI tools for:

- **Informational / conversational Q&A**: product capability overviews, “what can this app do”,
  first-time onboarding, **navigation** (“侧栏 / 顶栏先点哪里”), limitations, relationships between
  tools and workflows, “简洁说明”“控制在 N 句以内” — whenever the user wants **readable prose or
  markdown bullets**, not a widget.
- **Enumerated explanations** — phrases like **条列、分点、列举、要点** refer to **text layout** unless
  they also ask for cards, slides, dashboard, chart, poster, or “用组件展示”.
- **Short summaries** with **no** charts, KPIs, image galleries, or slide/poster frames.
- Anything where **markdown alone** is enough (including multi-section answers with `##` and lists).

### When **to** use GenUI (`emit_ui_tree`)

Call **`emit_ui_tree`** only if **at least one** applies:

1. The user **explicitly** asks for GenUI / 生成式 UI / 卡片 / 看板 / 幻灯片式排版 / dashboard / 图表组件 / “用画布展示”.
2. The deliverable is **inherently visual**: live **charts** from numeric data, KPI tiles,
   **data grids** that need column alignment beyond a markdown table, **slide/poster/card**
   mockups, **image-forward** layouts, **interactive** controls — where markdown would be a poor substitute.
3. You are **continuing** an answer that already used **`emit_ui_tree`** in this thread (then
   **`emit_ui_patch`** for small updates).

If unsure, **answer in markdown first**. You can offer GenUI in one sentence (“如需卡片式排版我可以再生成画布”) — **do not** emit a tree preemptively.

### Decision rule (after the gate above)

- **Design / branded UI tasks:** When the user wants layout, visual design, branding,
  slides/posters, GenUI polish, or wording like “设计 / UI / 排版”, load relevant skills **before**
  building trees: call **`load_skill`** for any **active** advertised skill whose name, description,
  or tags match design/visual/canvas work (e.g. contains design, ui, slide, brand, canvas, poster).
  Then **`get_genui_guide`** / **`list_ui_components`** as usual.
- Before **dashboards, slide/poster previews, or multi-card layouts**, call **`get_genui_guide`**
  for spacing, hierarchy, and restrained emoji/icon usage, then **`list_ui_components`** if you
  need exact `kind` names.
- **Inside GenUI**, prefer compact trees: weather widgets, KPI rows, **rich data tables**, status
  cards, single-panel dashboards, alerts — **not** plain bullet lists that duplicate markdown.
- **Use `emit_ui_patch`** to update an already-emitted gen UI tree in small
  increments instead of re-emitting the whole tree.
- **Use `canvas_publish(mode=html)`** only when *one* of these is true:
  1. The user explicitly asked for HTML / a webpage / a landing page / a
     printable report.
  2. The layout is page-scale and cannot be expressed by gen UI components
     (multi-section page, custom typography/illustrations, long-form report).
  3. When you do publish HTML, use **`tool_argument_blob`** + **`html_blob_id`** for the document body unless it is a tiny snippet (see the first invariant above).
- **Use `canvas_publish(mode=embed_url)`** only for allowlisted iframes (Maps,
  YouTube, Vimeo, OpenStreetMap).

### Posters, slide previews, and cards (gen UI)
For **posters, PPT-style slide previews, business cards, and themed layouts**, stay on **`emit_ui_tree`** and compose:
- **`DesignSurface`** — set `props.preset` to one of: `poster`, `slide`, `card`, `editorial`, `minimal`, `brutalist`, `geek`; optional `props.padding`: `none` \| `sm` \| `md` \| `lg`. Wrap your content as children. Use `geek` for terminal/cyber/code-oriented dashboards.
- **`AspectBox`** — fixed frame for a slide or hero image: `props.ratio` such as `16:9`, `4:3`, `1:1`, `3:2`, `85:45` (card-like), `210:297` (tall poster); optional `maxWidth` (px), `rounded`, `overflow` (`hidden` default). Put a **`Stack`**, **`Image`**, **`LiveCamera`**, or headings inside.
- **`Image`** — `props.src` may be `https://...` or a chat file preview path `/api/v1/files/{uuid}/preview`. Use `fit` (`cover`|`contain`|`fill`), `aspect`, `shadow`, `lightbox` (boolean), `caption`, `rounded`, `maxHeight` for layout control.
- **`Chart`** — inline charts (theme-aligned): set `props.chart` to `line` \| `bar` \| `area` \| `pie`; provide `props.categories` (string[]) and `props.series` as `[{ "name": "...", "values": [number, ...] }, ...]` (same length as categories for Cartesian charts; pie uses one series and categories as slice labels). Optional: `title`, `height` (px), `stacked` (bar/area), `showLegend`, `showGrid`. For publication-static plots or chart types not covered here (heatmap, radar, …), use **`chart_generator`** then show the PNG with **`Image`** (`props.src` from the tool result / file preview).
- **`Icon`** — Prefer **Lucide** (`props.name` kebab-case from [lucide.dev/icons](https://lucide.dev/icons)). Reserve **`iconSet: emoji`** for explicit playfulness or weather chips — do not pepper emoji through every row (see **`get_genui_guide`**).
- **`LiveCamera`** — optional live preview: `facingMode` `user`|`environment`, `mirrored`, `maxHeight`, `label`. Coexists with the chat/canvas **camera capture** control; this node only shows a stream inside the tree.

Example (single slide frame with title + image):

```json
{
  "schemaVersion": "1",
  "root": {
    "kind": "DesignSurface",
    "props": { "preset": "slide", "padding": "md" },
    "children": [
      { "kind": "Heading", "props": { "level": 2, "value": "Q3 roadmap" } },
      {
        "kind": "AspectBox",
        "props": { "ratio": "16:9", "rounded": true },
        "children": [
          { "kind": "Image", "props": { "src": "https://example.com/hero.png", "alt": "Hero", "fit": "cover" } }
        ]
      }
    ]
  }
}
```

When the user needs **print-ready PDF**, pixel-perfect brand PDFs, heavy animation, or bespoke CSS beyond these primitives, use **`canvas_publish(mode=html)`** and **`get_html_canvas_guide`**.

For **`pdf_generator`** (ReportLab), parameter **`cjk_font_path`**, or **inline** ReportLab / DOCX / PPTX code via **`code_execution`** / **`run_skill_script`**, use a **complete** pan-Unicode font (Noto Sans SC/CJK, Source Han Sans, WenQuanYi Micro Hei, Microsoft YaHei) — not supplemental fallback fonts such as **Droid Sans Fallback**, or mixed English/Chinese text can lose Latin glyphs in PDFs or substitute incorrectly in Office files.

### AI-generated images in gen UI
1. Call **`image_generate`** with the desired prompt (and optional size/style).
2. Use the returned **`preview_path`** (`/api/v1/files/{uuid}/preview`) as **`Image`** `props.src` inside **`emit_ui_tree`**. Do not paste raw base64 into the tree.
3. For remote images by URL, **`web_image_download`** also returns `preview_path` for the same pattern.

### Canonical node shape (gen UI)
Every node is exactly: `{ "kind": "...", "props": { ... }, "children": [ ... ] }`.
All component-specific fields (title, subtitle, padding, variant, value, label,
events, headers, ...) MUST be inside `props`. `children` is for nested nodes
only — never strings, never props.
Example: `{ "kind": "Card", "props": {"title":"Sales","padding":"md"},
"children": [{"kind":"Text","props":{"value":"Hi"}}] }`.

### Pull details on demand (do not memorise them)
- **Syntax + envelope** (`schemaVersion`, node keys, JSON escaping, **`emit_ui_patch`** paths)? Call **`get_genui_guide`**
  — read **`wire_format_and_syntax`** in the payload before authoring the tree.
- Polished gen UI (layout, typography, less emoji noise)? Use the same tool’s layout sections;
  follow **`workflow_order`** there (catalog → valid tree → emit).
- Need exact component `kind` names and prop hints? Call **`list_ui_components`**.
- About to author HTML? Call **`get_html_canvas_guide`** first to get the
  shipped utility classes (`wa-card`, `wa-gradient*`), design tokens, and a
  reference template.

### JSON argument safety
- Each canvas tool call is one strict JSON object — no trailing prose, no
  markdown around the object.
- **Prefer passing `tree` as a JSON object** in tool arguments (not a single
  quoted string containing the whole tree). Nested strings then only need one
  level of escaping, which avoids subtle parse failures on large trees.
- Inside string values, escape double quotes as `\"` and line breaks as `\n`.
  Never paste raw multi-line strings.
- If `emit_ui_tree` returns `tree is not valid JSON` with a byte/column
  position, fix escaping at that spot (or switch to an object `tree`) and
  re-call with the same layout — do not discard the whole design.
- **Keep `emit_ui_tree` payloads under ~8,000 characters** of JSON. Larger
  trees risk output-token truncation, which corrupts the JSON and wastes a
  retry. When the layout exceeds this budget, emit a smaller initial tree
  (hero section + skeleton placeholders), then fill remaining sections with
  one or more `emit_ui_patch` calls. This is both faster for the user and
  more reliable than a single giant tree.
- For very large content, move to `canvas_publish(mode=html)` only if the
  user actually wants a page.

### Output token limits — mandatory chunked staging for full HTML pages

Your output has a token limit. A full HTML page **will** exceed it if you
try to emit it in a single tool call. **Always** use the multi-step blob
flow for full pages:

1. `tool_argument_blob(action=create)` — returns a `blob_id`.
2. `tool_argument_blob(action=append, blob_id=…, chunk_base64=…)` — repeat
   for each ~4 KB chunk of content (each chunk ≤ 60 000 base64 characters).
3. `tool_argument_blob(action=finalize, blob_id=…)`.
4. `canvas_publish(mode=html, html_blob_id=…)`.

**NEVER** use `create_and_finalize` for a full page — it requires the entire
content in one tool call, which will be truncated. **NEVER** inline the HTML
directly in `canvas_publish(html=…)` for anything beyond a small snippet.
