# 20. 从 BaseTool 实现一个可用工具

## 定位与先修

本文接在 [19. 工具 Schema 设计](19-tool-schema-design.md) 之后，面向要真正落地一个工具类、而不只是画出 JSON Schema 的开发者。建议先理解 JSON Schema 基本字段，并打开 `backend/leagent/tools/base.py`。这里的重点不是“如何让模型更愿意点这个工具”，而是：**宿主进程怎样安全、可重试、可观测地执行你写的业务函数**。

当前抽象方法签名必须是：

```python
async def execute(self, params: dict[str, Any], context: ToolContext) -> Any
```

仓库文档与旧笔记里若仍出现 `execute(self, context, **kwargs)`，以源码为准。`params` 是已经过契约与 Schema 校验的字典；`context` 携带 `session_id`、`user_id`、中止信号、以及可选的 `file_service` 等依赖。

## 学习目标

完成本文后，你应能独立完成一个工具从声明到注册的闭环：写清类级元数据；实现 `parameters` 与 `execute`；理解 `run()` 在调用 `execute` 前后做了哪些强制步骤；用 `ToolResult` 与 `NonRetryableToolError` 区分可重试与不可重试失败；知道无参构造工具靠 discovery、需依赖注入的工具靠 bootstrap 固化列表。

## 心智模型：execute 只管业务，run 管生命周期

对模型而言，工具是 name、description、parameters；对运行时而言，工具是 `BaseTool` 实例。Executor 与 `BaseTool.run()` 才会真正进入进程。`run()` 的固定顺序是：

```text
validate_params（未知键拒绝 + operation 条件必填 + jsonschema）
  → _enforce_path_sandbox（声明了 path_params / output_path_params 时）
  → validate_input（可覆盖的语义校验，如资源状态）
  → 带超时与 max_retries 的 _invoke_execute
  → execute(params, context)
  → 结果体积预算 → coerce_tool_result → ToolResult
```

因此 `execute` 应假设结构合法，但仍必须处理外部系统错误。路径穿越、缺字段这类确定性问题，应在校验阶段或抛 `NonRetryableToolError` 时结束，不要浪费重试次数。网络抖动、短暂锁冲突才适合留给默认重试。

类级安全默认值是 fail-closed：`is_concurrency_safe=False`、`is_read_only=False`、`is_destructive=False`。只读纯函数工具再显式打开并发与只读标记；会改文件、发邮件、改会话 todos 的工具不要假装安全。

## 真实实现路径

- `backend/leagent/tools/base.py`：`BaseTool`、`ToolContext`、`ToolResult`、`run()`、权限相关类型
- `backend/leagent/bootstrap/tools.py`：启动 discovery + curated 列表，HTTP/CLI/worker 共用
- 可参考的工具：`util/date_calculator.py`、`util/conversation_history.py`、`web/web_search_tool.py`
- 测试落点：`backend/tests/test_tools/`、`tests/test_registry.py`

常用类属性还包括：`category`、`timeout_sec`、`max_retries`、`capabilities`（如 `FILE_READ`）、`path_params` / `output_path_params`、`search_hint`（供工具检索）、`aliases`（旧名兼容）。

## 实现步骤与示例

第一步，选稳定 `name`：小写字母数字下划线，表达能力而非某次任务。第二步，写短 `description`：何时用、产出什么、有何副作用。第三步，写严格 `parameters`。第四步，实现 `execute`。第五步，按是否需要构造参数选择 discovery 或加入 `_CURATED_UTIL_TOOL_PATHS`。

```python
from typing import Any
from leagent.tools.base import BaseTool, ToolCategory, ToolContext, NonRetryableToolError


class EchoTitleTool(BaseTool):
    name = "echo_title"
    description = (
        "Echo a short title for debugging. Use when you need a no-side-effect "
        "confirmation of structured args."
    )
    category = ToolCategory.UTIL
    is_read_only = True
    is_concurrency_safe = True
    search_hint = "echo title debug"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 80,
                    "description": "Title text without file paths.",
                },
            },
            "required": ["title"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        title = self.require_param(params, "title")
        if not str(title).strip():
            raise NonRetryableToolError("title must be non-empty")
        return {
            "title": str(title).strip(),
            "session_id": context.session_id,
            "user_id": str(context.user_id) if context.user_id else None,
        }
```

若工具产出文件，应通过 `context.file_service.register(...)` 得到 `FileRef`，并放入返回数据或 `produced_files`，而不是在受管目录外随意写入。路径类输入要声明 `path_params`，让 `run()` 统一走 `PathSandbox`（见 [23](23-files-artifacts-and-sandbox.md)）。

测试至少覆盖：Schema 失败、语义失败、一次成功。不要只测“happy path 能 import”。

## 验证命令

```bash
cd backend
uv run pytest tests/test_registry.py -q
uv run ruff check leagent/tools/base.py
```

在单测里对实例直接 `await tool.run({"title": "ok"}, ToolContext())`，断言 `success` 与错误分支，比只测 `execute` 更接近生产路径。

## 常见误区

1. **照抄旧签名。** 必须是 `(params, context)`。
2. **跳过 run 假设 executor 只调 execute。** 沙箱、重试、超时与体积预算都在 `run()`。
3. **默认并发不安全却标 True。** 有共享可变状态或写冲突时保持 `False`。
4. **把密钥做成模型参数。** 应从配置或 `ToolContext` 注入。
5. **用 description 代替服务端校验。** 权限与路径必须以代码强制。
6. **返回随意字符串却期待前端结构化展示。** 尽量返回稳定字典，失败用 `ToolResult.fail` 或明确 error 字段。

## 业内对照

OpenAI function calling 与 Anthropic tool use 最终都落到“名字 + 描述 + JSON Schema + 宿主执行”。LangChain 常从函数注解推导 schema，上手快，但对多模型格式、权限标记与结果预算的控制较弱。Cursor / Codex 一类产品更强调只读/破坏性分类与审批。LeAgent 的 `BaseTool` 显式暴露这些开关，并用 `run()` 把契约变成强制执行流程，而不是约定俗成。

## 落地检查清单

提交新工具前，建议按下列清单自检一遍。名称是否只表达稳定能力，而不是某次活动或客户简称？描述是否同时覆盖适用场景与明确不适用场景，避免模型在边界任务上乱调用？Schema 是否拒绝未知字段，并对枚举、长度、数组元素给出可机器校验的约束？`execute` 是否始终使用 `(params, context)` 签名，并用 `require_param` 或显式取值处理必填项？失败路径是否区分可重试的外部故障与不应重试的契约错误？若触及文件系统，是否声明了 `path_params` 或 `output_path_params`，而不是在 `execute` 内部自己拼接路径？若产出二进制或文本产物，是否走文件登记而不是散落临时目录？测试是否覆盖成功、Schema 失败、语义失败至少三条路径？只有这些问题都有肯定答案，工具才算达到仓库当前工程标准。

## 总结

一个合格工具等于：稳定名称、边界清晰的描述、可验证 Schema、正确的 `execute(params, context)`，以及把校验与重试交给 `run()`。先把这一层写对，再进入注册表、执行器、并发与沙箱；否则上层再精巧也会被错误签名或绕过校验的实现拖垮。
