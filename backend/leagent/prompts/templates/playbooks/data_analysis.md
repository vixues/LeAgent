---
name: playbooks/data_analysis
variant: default
description: Data analysis playbook — CSV profiling, aggregation, and charts.
requires_tools:
  - csv_processor
  - data_aggregate
  - chart_generator
---

## Data Analysis playbook

Use this playbook when the user wants to explore, summarise, or visualise
tabular data (CSV/TSV, inline rows, or session files).

### Tool routing

| Step | Tool | Typical operations |
|------|------|--------------------|
| Load / profile | **`csv_processor`** | read, stats, query, write (export) |
| Summarise | **`data_aggregate`** | groupby, describe, pivot, value_counts |
| Visualise | **`chart_generator`** | bar, line, pie, scatter, heatmap |

### Multi-file association (required when ≥2 attachments)

Before filling a master template from multiple Excel/PDF/CSV inputs:

1. **List** each attachment with its role (master / lookup / rules).
2. **Schema-align** — for each file, name the join keys and columns you will use.
3. **Coverage check** — confirm every required master row has a match strategy
   (exact key, fuzzy name, or “leave blank / fetch from web”).
4. Only then write the filled spreadsheet, and cite the managed `file_id`.

### Workflow

1. **Profile** — Start with `csv_processor` stats or read on the source file,
   or `write` demo rows when building from scratch.
2. **Aggregate** — Pass rows inline via `data` or `source_path` to
   `data_aggregate`; pick group columns and aggregation functions that match
   the user's question.
3. **Chart** — Call `chart_generator` with `chart_type` (`bar` or `line`),
   `data.categories`, `data.series`, and `output_path` under the session
   workspace. Prefer the `report` or `presentation` theme unless the user
   specifies otherwise.

### Do not

- Do not hand-roll matplotlib in `code_execution` when `chart_generator`
  covers the chart type.
- Do not inline megabyte-scale datasets; spill to CSV and use `source_path`.
- Do not skip schema alignment when joining two or more attachments.
