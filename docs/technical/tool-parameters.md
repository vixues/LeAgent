# Tool Parameter Naming Conventions

LeAgent tool inputs follow a **strict canonical contract**: the JSON Schema
declared on each tool's `parameters` property is the only authoritative
definition exposed to LLMs. There is no silent alias coercion.

## Canonical keys

| Semantic role | Canonical key | Example tools |
|---|---|---|
| Document file input | `file_path` | `markdown_processor`, `pdf_reader`, `text_processor`, `excel_reader` |
| Data file input | `source_path` | `data_clean`, `data_merge`, `sql_query` |
| File-manager target | `path` | `file_manager` (`file_ops`) |
| Markdown body | `content` | `markdown_processor` |
| Plain-text body | `data` | `text_processor` |
| Generated output | `output_path` | `chart_generator`, `document_generate` |
| JSON pointer (not filesystem) | `path` | `config_file` query operation |

## Contract enforcement

Validation runs in `BaseTool.validate_params()` via
[`backend/leagent/tools/contract.py`](../../backend/leagent/tools/contract.py):

1. **Unknown keys** — rejected with an actionable error (e.g. `path` when the
   schema expects `file_path`).
2. **Operation-conditional required fields** — e.g. `markdown_processor`
   `create` requires `file_path`.
3. **JSON Schema** — `jsonschema.validate()`; tools should set
   `additionalProperties: false`.
4. **Path sandbox** — every `path_params` / `output_path_params` key must
   appear in `parameters.properties`.

Structured warnings are logged as `tool_contract_violation` before execution.

## Prompt and manifest alignment

- `session_attachments` manifest emits `file_path=…` (not `path=`).
- Playbook templates under `prompts/templates/playbooks/` document canonical
  parameter names and required fields per operation; they attach at runtime
  via the `playbooks` context source when `playbook_ids` are set on the harness.

## Adding a new tool

1. Declare all parameters in `parameters` JSON Schema with canonical names.
2. Set `path_params` / `output_path_params` to match schema property names.
3. Use `self.require_param(params, "key")` in `execute` for required fields.
4. Do **not** add `_normalize_params` or other alias shims — fix prompts and
   schemas instead.
5. Add coverage in `tests/test_tool_param_invariants.py` when introducing new
   path/body parameter patterns.

## Malformed JSON recovery

`recover_raw_args()` may salvage broken JSON escaping for large string fields.
Recovery extracts **canonical keys only** — it is not an alias layer.
