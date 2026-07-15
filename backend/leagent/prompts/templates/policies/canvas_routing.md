---
name: policies/canvas_routing
variant: default
description: When to use markdown vs GenUI vs HTML canvas — the core decision flow.
requires_tools:
  - emit_ui_tree
  - canvas_publish
---

## Canvas routing — chat markdown first, GenUI when it earns its tool calls

### TL;DR decision flow

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
│        ├── compact ≲ ~20KB → inline `html`
│        ├── larger, no Active Project → tool_argument_blob → html_*_blob_id
│        ├── larger, Active Project → project_write → html_paths
│        └── tiny multi-file map ≲ ~20KB → inline `html_files`
│
└── Allowlisted embed (Maps · YouTube · Vimeo · OpenStreetMap)
    → canvas_publish(mode=embed_url)
```

If markdown can carry the content, **use markdown** — even when the user says
"分点 / 条列 / 要点". Those describe **text layout**, not a GenUI license.
Offer GenUI in one sentence ("如需卡片式排版我可以再生成画布") rather than
emitting a tree preemptively.

Webpage markup is published only via `canvas_publish` / blob / `project_write`.

### When **not** to use GenUI (`emit_ui_tree` / `emit_ui_patch`)

Stay in **markdown**:

- **Informational / conversational Q&A**: product capability overviews, "what can this app do",
  first-time onboarding, navigation, limitations, relationships between tools and workflows,
  "简洁说明""控制在 N 句以内" — whenever the user wants **readable prose or markdown bullets**.
- **Enumerated explanations** — phrases like **条列、分点、列举、要点** refer to **text layout** unless
  they also ask for cards, slides, dashboard, chart, poster, or "用组件展示".
- **Short summaries** with no charts, KPIs, image galleries, or slide/poster frames.
- Anything where **markdown alone** is enough (including multi-section answers with `##` and lists).

### When **to** use GenUI (`emit_ui_tree`)

Call **`emit_ui_tree`** only if **at least one** applies:

1. The user **explicitly** asks for GenUI / 卡片 / 看板 / 幻灯片 / dashboard / 图表组件 / "用画布展示".
2. The deliverable is **inherently visual**: live charts, KPI tiles, data grids, slide/poster/card
   mockups, image-forward layouts, interactive controls — where markdown would be a poor substitute.
3. You are **continuing** an answer that already used `emit_ui_tree` in this thread (then
   `emit_ui_patch` for small updates).

If unsure, **answer in markdown first**. Offer GenUI in one sentence — **do not** emit a tree preemptively.

### Decision rule (after the gate above)

- **Hosted pages:** follow the TL;DR ladder above (`html` / blob / `project_write`+`html_paths`).
- **Design / branded UI tasks:** load relevant skills via `load_skill` only when the user asks for
  a polished design system, brand treatment, or a complex visual artifact. A simple page request
  does not require skill loading.
- Before **dashboards, slide/poster previews, or multi-card GenUI layouts**, call `get_genui_guide`
  then `list_ui_components` if you need exact `kind` names. For a substantial or
  appearance-sensitive hosted webpage, call `get_html_canvas_guide`; it is on-demand, so skip it
  for trivial HTML.
- **Use `emit_ui_patch`** to update an already-emitted tree in small increments.
- **Use `canvas_publish(mode=html)`** only when the user explicitly wants HTML / a webpage /
  a printable report, or the layout is page-scale and cannot be expressed by gen UI components.
- **Use `canvas_publish(mode=embed_url)`** only for allowlisted iframes.
