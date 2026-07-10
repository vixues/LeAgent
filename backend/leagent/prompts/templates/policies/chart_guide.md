---
name: policies/chart_guide
variant: default
description: Professional chart mode — chart-type selection ontology, Chart Spec cheatsheet, and rendering-path routing.
requires_tools:
  - emit_ui_tree
  - chart_generator
---

## Professional chart mode

### Rendering paths (pick exactly one)

1. **Quick chart** — simple line/bar/area/pie with one look: GenUI **`Chart`** (lightweight, no spec).
2. **Professional / interactive chart** — anything statistical, scientific, financial, hierarchical,
   3D, or needing zoom/tooltips: GenUI **`ProChart`** via `emit_ui_tree` with `props.spec` (Chart Spec v1).
3. **Static export** — the user wants a file (PNG/SVG/PDF), a document figure, or print quality:
   **`chart_generator`** with the same `spec`, then show the image with `Image` (`preview_path`)
   or markdown `![caption](preview_url)` — never inline base64.

Before authoring a non-trivial spec, call **`list_chart_types`** for the exact data shape per type.
The server validates every spec and computes statistics (bins, quartiles, KDE, regression fit,
ECDF, pareto ordering, waterfall totals) — pass **raw data**, never precompute these yourself.

**Minimal contract: you only decide `chartType` + `data`.** Never write ECharts option JSON or
matplotlib code. The server repairs common shape variants automatically (snake_case keys,
`series[].data`, `{name: values}` series maps, `[{name, value}]` lists, `[{x, y}]` point objects,
string numbers like `"1,200"`/`"45%"`) — but emit the canonical shape when you can. If validation
fails, the error message contains the expected data shape and a minimal example: fix the spec and
re-emit in the same turn.

### Which chart answers which question

| Analytical question | chartType |
|---|---|
| Trend over time | `line`, `area` (magnitude), `step` (discrete changes) |
| Compare categories | `bar`, `horizontal_bar` (long labels), `combo` (two measures, dual axis) |
| Part of whole | `pie`/`donut` (≤ 8 slices), `treemap`/`sunburst` (hierarchy), stacked `bar`/`area` |
| Relationship of two variables | `scatter`, `bubble` (3rd variable = size), `regression_scatter` (fit + R²) |
| Distribution of samples | `histogram`, `boxplot` (compare groups), `violin` (shape), `ecdf` |
| Measurement uncertainty | `error_bar` (values + errors) |
| 80/20 contribution | `pareto` |
| Matrix / field intensity | `heatmap` (labels), `contour` (continuous field), `surface_3d` (relief) |
| Multi-dimensional profile | `radar` (3-10 axes), `parallel_coordinates` (many records) |
| Angular / cyclic comparison | `polar_bar` |
| 3D point cloud / grid | `scatter_3d`, `bar_3d` |
| Price series | `candlestick` (ohlc bars, optional volume) |
| Running total bridge | `waterfall` (signed deltas) |
| Stage conversion | `funnel` |
| Single KPI vs range | `gauge` (set yAxis min/max) |
| Flows between stages | `sankey` (nodes + links) |
| Network relations | `graph` (nodes + links) |
| Daily activity | `calendar_heatmap` ({date, value} entries) |

### Chart Spec v1 cheatsheet

`{"chartType", "title", "subtitle"?, "data", "xAxis"?, "yAxis"?, "y2Axis"?, "options"?}` — all
component fields stay inside the ProChart node's `props.spec`.

```json
{"kind": "ProChart", "props": {"spec": {
  "chartType": "boxplot", "title": "Latency by region",
  "data": {"series": [
    {"name": "us-east", "raw": [12, 15, 13, 18, 22, 14]},
    {"name": "eu-west", "raw": [22, 25, 23, 28, 32, 24]}
  ]},
  "yAxis": {"label": "ms"}
}}}
```

```json
{"kind": "ProChart", "props": {"spec": {
  "chartType": "combo", "title": "Revenue vs margin",
  "data": {"categories": ["Q1", "Q2", "Q3", "Q4"], "series": [
    {"name": "Revenue", "values": [120, 180, 150, 220], "seriesType": "bar"},
    {"name": "Margin %", "values": [31, 35, 32, 40], "seriesType": "line", "yAxisIndex": 1}
  ]},
  "options": {"valuePrefix": "$"}, "y2Axis": {"label": "%"}
}}}
```

```json
{"kind": "ProChart", "props": {"spec": {
  "chartType": "sankey", "title": "Signup funnel flow",
  "data": {
    "nodes": [{"name": "Visits"}, {"name": "Signup"}, {"name": "Paid"}],
    "links": [{"source": "Visits", "target": "Signup", "value": 120},
              {"source": "Signup", "target": "Paid", "value": 40}]
  }
}}}
```

Data field per family: `series[].values` + `categories` (Cartesian/pie/radar/funnel/waterfall/pareto),
`series[].points` (scatter/bubble/regression/3D scatter/parallel), `series[].raw` (histogram/boxplot/
violin/ecdf), `matrix` + `rowLabels`/`colLabels` (heatmap/contour/surface_3d/bar_3d), `ohlc`
(candlestick), `nodes`+`links` (sankey/graph), `items` (treemap/sunburst), `calendar` (calendar_heatmap).

### Professional chart rules

- Every chart MUST have a `title`; add axis `label`s and `valuePrefix`/`valueSuffix` units so it
  reads standalone. Multi-series charts keep the legend on.
- Use `options.referenceLines` (`[{value, label, tone}]`) for targets/thresholds instead of prose.
- Series `tone` (`success|danger|warning|info|neutral`) only when color carries meaning.
- `options.dataZoom: true` for long time series; `options.stacked` + `percent` for composition trends.
- Set the ProChart node `height` (px) for dense charts; default is 320.
- Do NOT emit empty or placeholder charts — omit the section when there is no data.
