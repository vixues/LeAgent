"""Rule definitions package.

This module is intended for storing YAML rule definition files
and any programmatically-defined rule sets.

Rule YAML files should be placed in this directory or subdirectories
and will be automatically loaded by the RuleEngine when configured
to load from this path.

Example YAML rule definition:

```yaml
id: expense_validation
name: Expense Validation Rules
description: Rules for validating expense reports
version: "1.0.0"
rules:
  - id: max_amount
    name: Maximum Amount Check
    description: Expense must not exceed maximum limit
    severity: error
    condition:
      type: threshold
      params:
        value: "{{amount}}"
        max: 5000
    message: "Amount {{amount}} exceeds maximum of 5000"

  - id: valid_category
    name: Valid Category Check
    severity: warning
    condition:
      type: compare
      params:
        left: "{{category}}"
        operator: in
        right: ["travel", "meals", "supplies", "equipment"]
    message: "Invalid expense category: {{category}}"

  - id: date_not_future
    name: Future Date Check
    condition:
      type: date_range
      params:
        date: "{{expense_date}}"
        start: "2020-01-01"
        end: "{{today}}"
    message: "Expense date cannot be in the future"
```
"""

from pathlib import Path

DEFINITIONS_DIR = Path(__file__).parent

__all__ = ["DEFINITIONS_DIR"]
