---
name: data-analyzer
description: Guidance for analyzing structured data, generating statistics and producing data-driven insights. Use when the user asks to analyze data, compute statistics, find patterns, or generate analytical reports.
license: Apache-2.0
allowed-tools: data_extractor rule_matcher document_parser
metadata:
  version: 1.0.0
  category: data
  tags: [data, analysis, statistics, report, insights]
---

# Data Analysis

You are assisting with data analysis tasks. Follow these guidelines.

## Analysis Workflow

1. **Understand** the data: identify columns, types, ranges, and any quality issues.
2. **Clean** the data: handle missing values, outliers, and format inconsistencies.
3. **Analyze**: compute relevant statistics (counts, sums, averages, distributions).
4. **Compare**: when multiple datasets or time periods exist, provide comparative analysis.
5. **Summarize**: present findings clearly with key metrics highlighted.

## Statistical Methods

- Use descriptive statistics (mean, median, mode, std dev) as a baseline.
- Identify trends and patterns — year-over-year, month-over-month, category breakdowns.
- Flag outliers and anomalies with context about their potential significance.
- For comparisons, compute both absolute and percentage differences.

## Output Formats

- **Summary**: Concise paragraph with key findings and numbers.
- **Table**: Structured tabular format for detailed breakdowns.
- **Report**: Sectioned report with executive summary, methodology, findings, and recommendations.

## Best Practices

- Always state the sample size and time range of the data being analyzed.
- Round numbers appropriately for readability (2 decimal places for percentages).
- When making comparisons, ensure the baseline and comparison period are clear.
- Distinguish between correlation and causation in findings.
- Provide actionable recommendations when the analysis supports them.
