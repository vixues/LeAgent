# 工具参数命名约定

LeAgent 的工具输入遵循**严格的规范契约**：每个工具 `parameters` 属性上声明的
JSON Schema 是暴露给 LLM 的唯一权威定义。不存在静默别名强制转换。

英文版：[tool-parameters.md](./tool-parameters.md)

## 规范键名

| 语义角色 | 规范键 | 示例工具 |
|---|---|---|
| 文档文件输入 | `file_path` | `markdown_processor`、`pdf_reader`、`text_processor`、`excel_reader` |
| 数据文件输入 | `source_path` | `data_clean`、`data_merge`、`sql_query` |
| 文件管理目标 | `path` | `file_manager`（`file_ops`） |
| Markdown 正文 | `content` | `markdown_processor` |
| 纯文本正文 | `data` | `text_processor` |
| 生成输出 | `output_path` | `chart_generator`、`document_generate` |
| JSON 指针（非文件系统） | `path` | `config_file` 查询操作 |

## 契约强制

校验在 `BaseTool.validate_params()` 中通过
[`backend/leagent/tools/contract.py`](../../backend/leagent/tools/contract.py) 执行：

1. **未知键** — 以可操作错误拒绝（例如 schema 期望 `file_path` 时传入了 `path`）。
2. **操作条件必填字段** — 例如 `markdown_processor` 的 `create` 需要 `file_path`。
3. **JSON Schema** — `jsonschema.validate()`；工具应设置 `additionalProperties: false`。
4. **路径沙箱** — 每个 `path_params` / `output_path_params` 键必须出现在
   `parameters.properties` 中。

结构化警告在执行前以 `tool_contract_violation` 记录。

## 提示词与清单对齐

- `session_attachments` 清单发出 `file_path=…`（不是 `path=`）。
- `prompts/templates/playbooks/` 下的 playbook 模板按操作记录规范参数名与必填字段；
  当 harness 上设置了 `playbook_ids` 时，它们在运行时通过 `playbooks` 上下文源挂载。

## 添加新工具

1. 在 `parameters` JSON Schema 中用规范名称声明所有参数。
2. 将 `path_params` / `output_path_params` 设为与 schema 属性名一致。
3. 在 `execute` 中对必填字段使用 `self.require_param(params, "key")`。
4. **不要**添加 `_normalize_params` 或其他别名垫片——应修复提示词与 schema。
5. 引入新的路径/正文参数模式时，在 `tests/test_tool_param_invariants.py` 中补充覆盖。

## 畸形 JSON 恢复

`recover_raw_args()` 可能挽救大字符串字段中损坏的 JSON 转义。
恢复只提取**规范键**——它不是别名层。
