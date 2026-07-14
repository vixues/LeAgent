# 19. 工具 Schema 设计：让模型稳定地产生可执行参数

## 定位与先修

本文是工具系统系列的起点，面向需要为 LeAgent 增加或重构工具的开发者。建议先理解 JSON Schema 的 `type`、`properties`、`required`、`enum`，并浏览 `backend/leagent/tools/base.py`、`contract.py` 与 `backend/tests/test_tool_param_invariants.py`。这里讨论的 Schema 不是普通 API 文档：它会直接进入模型上下文，既约束参数，也影响模型是否选择该工具。

## 学习目标

完成本文后，你应能设计名称稳定、语义明确、可验证且节省 token 的工具接口；知道 Schema 校验、业务校验和权限校验的边界；能够避免“Schema 看似合法、模型却总调用失败”的接口。

## 心智模型：Schema 是模型与执行器之间的协议

一次调用大致经过：

```text
用户意图 → 模型阅读 name/description/parameters
        → 生成参数对象
        → Executor 解析与规范化
        → BaseTool.validate_params
        → validate_input
        → execute(params, context)
```

`BaseTool.validate_params()` 先拒绝未知键，再检查按 operation 变化的必填字段，最后调用 `jsonschema.validate`。因此不要把希望模型“自行领会”的隐含规则留在描述中。能用结构表达的规则应进入 Schema；依赖运行时状态的规则，例如文件是否存在，放入 `validate_input()`；用户是否有权限则交给权限层。

## 真实代码路径

- `backend/leagent/tools/base.py`：`parameters`、`validate_params()`、`to_openai_schema()`、`to_anthropic_schema()`
- `backend/leagent/tools/contract.py`：未知参数与 operation 条件必填约束
- `backend/leagent/tools/registry.py`：注册校验、Schema 格式转换与缓存
- `backend/leagent/tools/executor.py`：模型参数解析、修复和执行入口
- `backend/tests/test_registry.py`：OpenAI/Anthropic Schema 及注册约束
- `backend/tests/test_tool_param_invariants.py`：仓库级参数契约

## 设计步骤

第一，工具名使用小写字母、数字和下划线，表达一个稳定能力，而不是一次任务。注册器要求名称去掉下划线后为字母数字且不超过 64 字符。第二，`description` 写清“何时使用、产出什么、关键副作用”，不要塞长篇操作手册。第三，字段名采用仓库约定的规范名，不要同时提供 `path`、`file`、`filename` 三个近义入口。第四，默认拒绝未知字段，避免拼写错误被静默忽略。第五，枚举应小而稳定；自由文本不要伪装成巨大枚举。

可复用的 Schema 骨架：

```python
from typing import Any

REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120,
            "description": "报告标题，不包含目录路径。",
        },
        "format": {
            "type": "string",
            "enum": ["markdown", "json"],
            "default": "markdown",
            "description": "输出格式。",
        },
        "sections": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
            "description": "按输出顺序排列的章节名。",
        },
    },
    "required": ["title", "sections"],
    "additionalProperties": False,
}
```

注意：仓库的 `detect_unknown_keys()` 已在顶层拦截未知键，但显式写 `additionalProperties: False` 仍能让协议对外自解释。对于嵌套对象，也应在各层设置约束。不要把密码、令牌设计为普通模型参数；应由服务端配置或 `ToolContext` 注入。

## Schema、语义校验与执行的分工

Schema 负责类型、范围、枚举和结构。`validate_input()` 负责需要 I/O 或上下文的判断，例如路径是否存在、资源状态是否允许转换。`execute()` 假定前两层已经通过，但仍应处理外部系统错误。确定性错误可抛 `NonRetryableToolError`，网络抖动等暂态错误才值得由 `BaseTool.run()` 重试。

多操作工具应谨慎。若 `operation=create|delete|list` 的字段完全不同，拆成三个工具通常比在一个对象里堆条件更容易被模型正确调用。只有多个操作共享资源、命名和绝大多数参数时，才保留 `operation`。这也减少描述 token 和错误恢复复杂度。

## 验证命令

```bash
cd backend
uv run pytest tests/test_registry.py tests/test_tool_param_invariants.py -q
uv run python -m pytest tests/test_executor.py -q
uv run ruff check leagent/tools
```

还可以在测试中直接断言 `tool.validate_params()` 的成功与失败分支，并检查 `registry.get_schemas("openai")` 和 `"anthropic"` 的输出。

## 常见误区

1. **照抄旧签名。** 当前抽象方法是 `async def execute(self, params: dict[str, Any], context: ToolContext) -> Any`，不是 `execute(context, **kwargs)`。
2. **描述替代约束。** 写“format 只能是 json”却不写 `enum`，模型仍可能产生别值。
3. **字段过多。** 十几个互相依赖的可选字段会显著提高调用失败率，优先拆工具或引入清晰的嵌套对象。
4. **返回 Schema 与输入 Schema 混为一谈。** `parameters` 只描述输入；结果由 `ToolResult` 统一封装。
5. **把权限写进提示词。** “请勿删除重要文件”不是安全边界，权限、沙箱与人工确认必须在服务端执行。

## 业内对照

OpenAI function calling 与 Anthropic tool use 的外层格式不同，但 LeAgent 分别由 `to_openai_schema()` 和 `to_anthropic_schema()` 转换，内部参数都以 JSON Schema 为核心。与普通 REST OpenAPI 相比，Agent 工具更强调简短描述、低歧义字段和可恢复错误；与 LangChain 等框架的自动函数签名推导相比，显式 Schema 更啰嗦，却能稳定控制兼容性、权限标记和多模型表现。

## 总结

优质工具首先是优质协议：名称稳定、描述指出使用边界、Schema 表达结构约束、运行时校验处理环境事实。把模糊性留给自然语言，把确定性规则交给代码，模型调用成功率和系统安全性才会同时提升。
