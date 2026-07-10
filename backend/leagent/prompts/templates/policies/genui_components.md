---
name: policies/genui_components
variant: default
description: GenUI component catalog, canonical node shape, design surfaces, and AI image integration.
requires_tools:
  - emit_ui_tree
---

## GenUI component reference

### Canonical node shape

Every node is exactly: `{ "kind": "...", "props": { ... }, "children": [ ... ] }`.
All component-specific fields (title, subtitle, padding, variant, value, label,
events, headers, ...) MUST be inside `props`. `children` is for nested nodes
only — never strings, never props.

### Design surfaces and posters

For **posters, PPT-style slide previews, business cards, and themed layouts**, compose:

- **`DesignSurface`** — `props.preset`: `poster` | `slide` | `card` | `editorial` | `minimal` | `brutalist` | `geek`; optional `props.padding`: `none` | `sm` | `md` | `lg`.
- **`AspectBox`** — fixed frame: `props.ratio` (`16:9`, `4:3`, `1:1`, `3:2`, `85:45`, `210:297`); optional `maxWidth` (px), `rounded`, `overflow`.
- **`Image`** — `props.src` (`https://…` or `/api/v1/files/{uuid}/preview`). Keys: `fit` (`cover`|`contain`|`fill`), `aspect`, `shadow`, `lightbox`, `caption`, `rounded`, `maxHeight`.
- **`Chart`** — `props.chart`: `line` | `bar` | `area` | `pie`; `props.categories` (string[]), `props.series` (`[{ "name": "…", "values": [number…] }]`). Optional: `title`, `height`, `stacked`, `showLegend`, `showGrid`. For chart types not covered, use `chart_generator` then show the PNG with `Image`.
- **`Icon`** — Prefer **Lucide** (`props.name` kebab-case). Reserve `iconSet: emoji` for explicit playfulness.
- **`LiveCamera`** — `facingMode` `user`|`environment`, `mirrored`, `maxHeight`, `label`.

### AI-generated images in gen UI

1. Call `image_generate` with the desired prompt.
2. Use the returned `preview_path` (`/api/v1/files/{uuid}/preview`) as `Image` `props.src`.
3. For remote images, `web_image_download` also returns `preview_path`.

### Size guidelines

- Keep `emit_ui_tree` payloads under ~8,000 characters of JSON. Larger trees risk output-token
  truncation. Emit a smaller initial tree then fill remaining sections with `emit_ui_patch`.
- For very large content, move to `canvas_publish(mode=html)` only if the user actually wants a page.

### Pull details on demand

- **Syntax + envelope** (`schemaVersion`, node keys, `emit_ui_patch` paths)? Call `get_genui_guide`.
- Need exact component `kind` names and prop hints? Call `list_ui_components`.
- About to author HTML? Call `get_html_canvas_guide` first.

- Generating a PDF/DOCX/PPTX/Excel or CJK chart from a visual turn? The
  `document_fonts` block loads automatically alongside this one (pan-Unicode
  font selection lives there — single source of truth).
