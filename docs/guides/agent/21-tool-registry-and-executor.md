# 21. ToolRegistry 与 ToolExecutor：从发现到调用

## 定位与先修

本文说明工具如何进入可用池、如何变成模型可见的 schema，以及调用如何落到 `ToolExecutor`。先修：[19](19-tool-schema-design.md)、[20](20-build-a-base-tool.md)。核心代码位于 `backend/leagent/tools/registry.py`、`executor.py`，装配入口是 `backend/leagent/bootstrap/tools.py`。读本篇时请带着一个问题：**“模型看见的工具列表”与“进程里真正能执行的实例”是不是同一策略控制的？”** 答案是否定时，就会出现 UI 能点、模型看不见，或模型看得见却在执行时被拒的体验裂缝。

## 学习目标

你应能解释 discovery 与 curated 注册为何并存；`get_schemas("openai"|"anthropic")` 如何过滤 deny 并缓存；单次 `execute` 与批量 `execute_partitioned` 的职责边界；为何工作流里的 `Tool.<name>` 节点可以和聊天共用同一注册表；以及如何避免在 main 与 CLI 各自维护工具清单。

## 心智模型：注册表是目录，执行器是接线板

```text
bootstrap_tools()
  ├─ discover_all()     # 扫描 leagent.tools.* 中可无参构造的工具
  ├─ curated paths      # 显式 import：plan/task/file/code/MCP 桥等
  └─ register_workflow_tool_nodes()  # 工具 → DAG 节点

模型一轮
  └─ registry.get_schemas(deny=...) → 进入 prompt 的工具列表
       └─ 模型返回 tool_calls
            └─ ToolExecutor.execute / execute_partitioned
                 ├─ 权限 / 限流 / middleware pipeline
                 └─ tool.run(params, ToolContext)
```

Registry 不执行副作用，只保证“名字合法、实例可检索、schema 可导出”。Executor 不拥有工具定义真相，真相在已注册实例上。把两者混进同一个上帝对象，最后会变成无法测试的隐式全局状态。

## 真实实现要点

**注册校验。** `ToolRegistry.register()` 要求：非空名称；去下划线后仅字母数字；长度不超过 64；必须有 description；`parameters.type` 必须是 `object`。支持 `aliases` 映射到规范名；`replace=True` 可覆盖同名工具并清理旧分类索引。

**Deny 与 schema 缓存。** `filter_by_deny_rules` / `get_schemas` 使用 `fnmatch`（例如 `mcp__*`、`*_admin`）。禁用应发生在 schema 出口，避免模型看见不可用工具；执行前仍应再做 permission，防止有人绕过 schema 直接调 executor。缓存键包含 provider 格式与 deny 集合，注册变更会递增 generation。

**Executor。** 构造时绑定 `registry`、`default_timeout`、`max_parallel`（默认信号量 10）、可选 `permission_context` 与 `service_manager`。`execute(tool_name, parameters, context)` 会把松散上下文 coercing 成完整 `ToolContext`。`approval_requirement()` 供 query 循环前置检查：需要人工确认时，应先进入 Allow/Deny，而不是执行失败后再解释。

**Bootstrap 单一入口。** `register_default_tools` / `bootstrap_tools` 被 HTTP、CLI、worker 共用，专门修复历史上“服务器有、CLI 没有”的漂移。`ConversationHistoryTool` 等会出现在 `_CURATED_UTIL_TOOL_PATHS`，因为它们与自动 discovery 策略一起保证关键能力始终存在。

## 示例：本地确认注册与过滤

```python
from leagent.bootstrap.tools import register_default_tools
from leagent.tools.registry import ToolRegistry

reg = ToolRegistry()
register_default_tools(reg, run_discovery=True)
assert reg.get_optional("conversation_history") is not None
schemas = reg.get_schemas("openai", deny=("mcp__*",))
print(len(schemas), schemas[0]["function"]["name"])
```

调试时可用 `get_optional` 与 `list` 类接口确认别名解析；不要假设别名会以本名出现在 schema 里而不做转换验证。工作流侧在注册完成后生成同名节点，使 agent 设计 DAG 与聊天调用共享语义。

## 验证命令

```bash
cd backend
uv run pytest tests/test_registry.py tests/test_executor.py -q
```

关注点：OpenAI/Anthropic 外层包装是否正确；未知工具是否返回清晰失败信封；畸形 JSON 参数修复后是否仍经过 `validate_params`；deny 后 schema 中确实不再出现匹配工具。

## 常见误区

1. **在多个入口分散 `register`。** 应收敛到 bootstrap，否则部署形态之间工具集合不一致。
2. **以为 unregister 后模型立刻忘记。** 还要确保调用方不长期缓存旧 schema 列表。
3. **跳过 Executor 直接 `tool.execute`。** 会丢掉权限、限流、进度回调与统一 `ExecutionResult`。
4. **把 registry 单例当成跨进程共享状态。** 多 worker 各自 bootstrap 一份内存表。
5. **只用 UI 隐藏危险工具。** 隐藏不等于安全；deny + permission + 沙箱缺一不可。
6. **把工作流节点当成另一套工具实现。** 应复用同一实例语义，避免双份逻辑分叉。

## 业内对照

LangGraph / LlamaIndex 常把工具列表绑在 graph 节点或 agent 构造参数上；OpenAI Assistants 把 tools 存在远端配置。LeAgent 选择本地 `ToolRegistry` 与进程启动装配，便于桌面零配置、离线调试，以及“每个工具自动成为工作流节点”。代价是每个进程启动都要完整 bootstrap，且多 worker 下没有中心化工具目录服务。

## 装配与排障顺序

当“模型说有工具但执行报找不到”或反过来“注册表里有却从不被调用”时，按固定顺序排查，通常比反复重启更快。首先确认当前进程是否调用了 `bootstrap_tools` 或 `register_default_tools`，以及 `run_discovery` 是否被测试夹具关掉。其次打印 `registry.get_optional(name)` 看别名是否解析到规范名。再次对比 `get_schemas` 的 deny 列表是否误伤了刚加的前缀。然后检查 Agent 定义或会话级工具白名单是否又做了一层过滤。最后才看 Executor 权限上下文是否 hard deny。工作流路径还要确认节点注册是否在工具注册之后执行，否则会出现图里缺节点但聊天里能调的分裂现象。把装配顺序写成团队约定，比事后对日志更省时间。

## 总结

Registry 回答“有哪些工具、模型能看见哪些”；Executor 回答“如何安全地调用一次或一批”。扩展系统时先保证单一 bootstrap 与一致的 deny/permission 出口，再调整并行策略与中间件。目录清楚、接线干净，工具生态才能同时服务聊天、SDK、CLI 与工作流，而不靠复制粘贴注册列表。
