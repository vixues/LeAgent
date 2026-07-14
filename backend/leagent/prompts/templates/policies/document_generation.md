---
name: policies/document_generation
variant: default
description: Structure and quality guidance for generating professional documents (document_generate) and presentations (slides_generate).
requires_tools:
  - document_generate
  - slides_generate
  - checklist_generate
---

## Professional document generation

Route deliverables through the built-in tools — never hand-write ReportLab / python-docx / python-pptx code for something they can produce:

- **`document_generate`** → PDF, DOCX, HTML, Markdown. One markdown `content` string is the preferred input; the typed `blocks` array is the full-control escape hatch.
- **`slides_generate`** → PPTX decks from a structured `slides[]` list.
- **`checklist_generate`** → status-tracked checklists (Markdown/JSON/HTML/PDF/DOCX) with per-item status, priority, assignee, due date, notes, nested sub-items, a progress summary and legend. Build from manual `groups`/`items`, or from a workflow/rules file (`source_type`).

CJK is guaranteed (PDF embeds a pan-Unicode font; Office formats set east-Asian fonts on every run). Check the result: `font_embedded: false` or `warnings` means degraded output — tell the user instead of silently delivering tofu.

### Report anatomy (PDF/DOCX)

A professional report is not a wall of paragraphs. Default skeleton:

1. **Cover** (`cover: true` + `title`/`subtitle`/`author`/`date`) for anything ≥ ~3 pages. PDF covers are a consulting-style brand band; add `organization` and `logo_path` for client-ready output.
2. **TOC** (`toc: true`) once the document has ≥ 4 headings; add `numbered_headings: true` for formal/technical reports.
3. **Executive summary** first — 3-6 sentences or a `metrics` block of headline KPIs.
4. **Body sections** with a real heading hierarchy (`##` → `###`, never skip levels). Break up prose with:
   - tables for anything enumerable (GFM syntax; keep ≤ 6 columns),
   - ```chart fences (bar/line/pie/scatter/area, JSON body) for trends and comparisons,
   - `::: info|tip|warning|danger Title` callouts for risks, caveats, and key takeaways,
   - `- [ ]` / `- [x]` task lists for simple action items, or a ```checklist JSON fence / typed `checklist` block for status-tracked lists (priorities, assignees, progress),
   - a `columns` block (typed `blocks` array) for side-by-side comparisons (pros/cons, before/after),
   - LaTeX math for technical/scientific content: `$x^2$` inline, `$$…$$` or ` ```math ` fences for display equations, `\begin{align}` for multi-line derivations. Rendering is professional and native per format — real editable OMML equations in Word/PowerPoint, scalable vector paths in PDF, images in HTML — with no TeX install required,
   - footnotes (`[^1]` + `[^1]: source`) for citations, and definition lists (`Term` / `: definition`) for glossaries.
   - Markdown may start with YAML front matter (`--- title: … theme: … ---`); it fills any metadata you don't pass explicitly.
5. **Conclusion / recommendations**, then appendices after a `\newpage`.
6. Running `footer` with `show_page_number: true` for multi-page documents.

Formal-report precision switches (PDF-first, other formats degrade gracefully):

- `justify: true` — justified body text with widow/orphan control.
- `section_pages: true` — every H1 opens a new page (chapter-style reports).
- `numbered_figures: true` — captions auto-number as 表/Table N and 图/Figure N, following the content language.
- `header`/`footer` `text` placeholders (PDF): `{page}`, `{pages}`, `{title}`, `{author}`, `{date}`, `{section}`. A left-aligned `{section}` header + `{page}/{pages}` footer is the standard consulting chrome.

Theme choice: `professional` (default), `corporate` (formal blue), `academic` (serif, wide line spacing — papers), `minimal` (clean gray), `modern` (vivid blue). Custom YAML themes in `~/.leagent/templates/styles/` also resolve by name.

### JSON argument safety

Tool calls must be strict JSON. Inside string values (especially slide `body` /
document `content`):

- Escape ASCII double quotes as `\"` and line breaks as `\n`.
- Prefer Chinese book-title quotes「」/『』instead of raw `"` around quoted words —
  e.g. write「忘记」not `"忘记"`, which breaks the outer tool-call JSON.
- The runtime auto-repairs many unescaped-quote failures, but correct escaping
  still avoids a wasted turn.

### Slide narrative (PPTX)

Build a storyline, not a document on slides:

1. **Open** with `layout: title`, then an agenda or hook slide.
2. **One idea per slide**, 3-6 top-level bullets max, ≤ ~12 words per bullet. Body text auto-shrinks to fit, but density is still your job — long prose belongs in speaker `notes`.
3. Use `layout: section` slides to mark chapter transitions in decks ≥ 8 slides.
4. Prefer **evidence slides**: `layout: chart` / `table` / `image` with a takeaway title ("Revenue doubled in Q3", not "Q3 data").
5. `two_column` for text comparisons; `layout: columns` (2-4 headed columns, `emphasis: true` on the recommended one) for option matrices, frameworks, and before/after cards.
6. Close with `layout: quote` or `closing` (summary + call to action).
7. Slide titles should be assertions the audience can act on.

Consulting-grade slide anatomy (all optional, all layouts):

- `kicker` — short uppercase eyebrow above the title (chapter / topic label, e.g. "MARKET ANALYSIS").
- `title` — the **action title**: state the conclusion, not the topic.
- `takeaway` — one-sentence so-what shown in an accent bar at the bottom. Use it on every evidence slide.
- `body` markdown supports multi-level bullets (indent 2 spaces per level), numbered lists, task lists (`- [x]`), `#### run-in headings`, and **bold** — levels get proper consulting typography automatically.
- Image + text: set `image.position` (`right`/`left`/`top` split with `ratio`, `full`, or `background` for a full-bleed backdrop with a legibility scrim) on `content` or `image` slides.
- `background` (per slide or deck-wide): `{color}`, `{gradient: [from, to]}`, or `{image_url|image_path, overlay: 0.5}` — text colors adapt to background darkness automatically.

Deck themes are curated palettes. The default is `executive_light` (clean white background, professional blue). Others include `midnight_executive` (dark blue), `forest_moss`, `coral_energy`, `charcoal_minimal`, … Match tone: light themes for most business/training decks, dark themes (`midnight_executive`, `ocean_gradient`, `teal_trust`) for executive/keynote drama.

### Custom themes and reusable templates

- **Brand-matched output**: when the user has brand colors or wants a distinct look, use **`theme_designer`** `action: create` with the brand `primary` color (+ `mode: dark` for executive decks, optional `accent`/fonts). It derives a full contrast-checked palette and saves it; then pass the theme name to `document_generate` / `slides_generate`. Fix any `lint_warnings` it reports (usually by picking a darker/lighter primary) before delivering.
- **Recurring deliverables** (weekly reports, branded proposals, standard decks): after producing a good document once, save it as a template with **`document_template`** `action: save` — parameterize the changing parts with `{{ variables }}` (Jinja2 loops/conditionals allowed), declare `variables` with defaults, set `theme` and `defaults` (toc/cover/aspect/...). Instantiate later with `action: generate` + `values` + `output_path`. Use `preview` to check the rendered markdown/slides first.

### Choosing output format

- Print-fidelity, sharing, formal delivery → **pdf**.
- User will edit the file afterwards → **docx**.
- Presenting to an audience → **slides_generate** (pptx).
- Quick preview or web embedding → **html**; plain source of truth → **markdown**.
- Standalone status-tracked checklists (with statuses, priorities, assignees, progress, or a JSON export) → **`checklist_generate`**. Inline binary checklists inside a larger document → `- [ ]` task lists or a ```checklist fence in `document_generate`.
