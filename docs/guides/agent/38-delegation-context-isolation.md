# 38. Delegate、上下文隔离与状态合并

## 定位与先修

本文深入 `AgentRuntime.delegate` 与 `_run_subagent_core` 的状态语义，是子 Agent 系列的实现篇。先修 [37. 何时使用子 Agent](37-when-to-use-subagents.md)，并建议已读过 [05 状态所有权](05-state-ownership.md) 中关于 transcript 与 checkpoint 的区分。读者应已接受「子 Agent 不是更聪明的同一对话」；本篇用代码事实钉死三条契约：**fresh transcript**、**FileState clone**、以及 `prompt_variant == "coding_agent"` 结束时的 **merge-back**。

## 目标

完成后你应能回答：

1. `delegate` 如何解析 `AgentDefinition` 并落到 `_run_subagent_core`；
2. 子级消息历史为何从空开始，父级必须在 `prompt` 里放什么；
3. `ContextManager.clone()` / `FileState.clone()` 与 `merge_from` 的时机与作用域；
4. abort bridge、memory/recipe 覆盖如何保证「定义保真」而非静默继承父级；
5. 磁盘文件与 FileState 缓存在委派前后分别由谁感知。

## 心智模型

把委派想成「带着任务说明书进入空会议室，桌上只有一份文件索引复印件」：

```text
AgentRuntime.delegate(parent, agent, prompt, allow/deny, ...)
        │ resolve AgentDefinition → tools/model/budget/memory/recipe
        ▼
_run_subagent_core
        │ _filter_registry → ToolRegistry.scoped
        │ fork_scoped_engine → make_child_executor
        │ QueryEngine.fork（mutable_messages 不传入）
        │ ContextManager.clone()  ⇒ file_state.clone()
        ▼
sdk.kernel.run_loop(child, prompt)
        │
        └─ finally: prompt_variant == "coding_agent"
              ⇒ parent.file_state.merge_from(child.file_state)
```

复印件开场与父级一致，之后各自批注；只有 coding 任务在散会时把批注合回父桌。工作目录中的真实文件可能被工具直接修改，但 **缓存对象** 遵循 clone/merge 语义，与「父子共享同一 Python 引用」不是一回事。

## 读写数据流

**定义驱动入口。** `AgentRuntime.delegate` 先 `resolve(agent)` 得到 `AgentDefinition`，合并 definition 的 `tools.allow/deny`、模型参数、`resolve_runtime_budget`、`memory_enabled` / `memory_formation` 与 `resolved_recipe()`。调用方参数可再覆盖 `allowed_tools`、`max_turns`、`extra_denied_tools`。最终全部传入 `_run_subagent_core`，由它统一建 child registry、fork 引擎并驱动 `run_loop`。

**Scoped registry 与 child executor。** `_filter_registry` 对父 registry 调用 `scoped(allow, deny, match="exact", only_enabled=True)`。`fork_scoped_engine` 用 `make_child_executor(parent_executor, child_registry)` 复制 timeout、max_parallel、permission_context、service_manager，但 **registry 换成 child**。因此 LLM 收到的 tool schema 与 `ToolExecutor` 查找路径一致，模型无法通过别名调到父级独占工具。

**Fresh transcript。** `QueryEngine.fork()` 的配置不把父 `mutable_messages` 交给子级，子 Agent 从用户（子）`prompt` 起拥有独立消息列表。父 transcript（`TieredSessionStore` SSOT）不会自动追加子级全文；需要审计时靠返回 envelope 的 `activity`、hooks 的 `SubagentStart`/`SubagentStop` 与 trace，而不是把子对话并入父聊天。

**FileState 快照与 merge-back。** `ContextManager.clone()` 调用 `file_state.clone()` 与 `artifact_tracker.clone()`。子级 `project_read` 等会更新自己的 cache。`finally` 块里 **仅当** `prompt_variant == "coding_agent"` 执行 `parent_eng._context.file_state.merge_from(child._context.file_state)`；其它 variant（如 `subagent`、`script_agent`）默认不把子 cache 合回——父级看不到子读过的路径缓存，除非父自己再读或你扩展合并策略。

**Definition fidelity 覆盖。** 若调用方传入 `context_recipe`、`model_*`、`memory_enabled=False` 等，子级会显式覆盖 fork 继承值；`memory_enabled=False` 时 `child.config.agent_memory=None`，子级不做 recall。这与「子 Agent 静默继承父 persona」的直觉相反，设计意图是让每个 `AgentDefinition` 自成策略。

**Abort 与身份。** 默认 `inherit_abort=True`：监听 parent `abort_event`，触发后 `child.abort()`。`resolve_subagent_run_identity` 提供 session/user hint 用于观测与权限，但不等于共享聊天 transcript。

**返回 envelope。** 扁平 `SubagentResult` 含 `text`、`success`、`steps_count`、`partial`、`error`、`activity`、`changed_files`、`produced_files`、`images`、`verification_gap`、可选 `checkpoint_id`。父模型或工作流节点应验 `success` 与业务证据，而不是只信 `text`。

## 真实实现中的边界

**Fresh transcript 是默认隔离，不是缺陷。** 需要父对话细节时，必须改写进 prompt：路径、约束、已确认事实、验收标准、上一工人 envelope 摘要。把 OpenAI handoff「默认可见历史」的预期套到 LeAgent 会系统性误解委派行为。

**Clone 不是实时共享引用。** 父在子运行期间继续改自己的 FileState，子看不到；子读文件只更新子 cache。非 coding 变体结束后也不合回，父可能重复发起相同 `project_read`——这是隔离代价，不是 bug。

**Merge-back 只管 cache，不管磁盘真相。** 工具写出的 workspace 文件已经存在；merge 解决的是「父级上下文是否知道读过/改过哪些路径」，避免父重复读或丢失变更追踪。`coding_agent` 的 `changed_files` 与 `verification_gap` 仍须父级或测试验收。

**仍走同一 kernel。** `delegate` 不另起并行编排运行时；子级与父级、聊天 SSE、工作流 standalone 路径一样进入 `sdk.kernel.run_loop`。差别在 fork 配置与 scoped tools，不在执行内核。

**Hook 与 nested preview。** 父 hooks 可观察 `SubagentStart`/`SubagentStop`；内置多为 no-op。对 `project_write`、`code_execution` 等，可把 `tool_call_delta` 经 `nested_preview_emit` 挂到父 `tool_call_id`，方便 UI 展示嵌套活动——这是观测通道，不改变隔离语义。

## 示例与验证

```python
result = await runtime.delegate(
    parent_engine,
    "coding_agent",
    (
        "只读说明 Agent 节点 pause/resume 路径；"
        "给出 backend/leagent/workflow/nodes/agent_exec.py 证据行号；"
        "禁止改文件。输出：要点列表 + 测试名。"
    ),
    allowed_tools=["project_read", "project_grep", "project_glob"],
    max_turns=6,
)
assert result["success"] and not result.get("partial")
```

验证清单：

1. **Scoped tools** — `tests/test_subagent_scoped_executor.py` 确认 child executor 解析不到父独占工具；
2. **Fresh transcript** — 父 `mutable_messages` 不因委派自动增长为含子全文；子有独立引擎消息；
3. **FileState** — coding 路径后父 cache 含子读过的路径；`script_agent` 等非 coding 按实现可不含；
4. **Abort** — 父取消时子 `run_loop` 结束，`inherit_abort` 桥接任务被 cancel；
5. **Definition fidelity** — `tests/test_runtime_sdk.py` 中子级 `prompt_variant`、`context_recipe` 跟 definition 而非父级漂移。

## 常见误区

- **「子 Agent 会接着上一句聊。」** 不会；请写厚任务包，含输入位置与完成条件。
- **「FileState 全程共享同一对象。」** 启动时 clone；仅 `coding_agent` 结束时 merge-back。
- **「delegate 另起一套 kernel。」** 仍走同一 `run_loop`；隔离在 fork 与 registry。
- **「关掉父 memory 就关掉子 memory。」** 以 definition 与 `memory_enabled` 参数为准，可显式 detach。
- **「success 表示业务正确。」** 只表示运行态完成；coding 还要看 `verification_gap` 与测试。
- **「子写了文件父一定在 cache 里知道。」** 磁盘已变，但非 coding 变体可能不把读路径合回父 cache。

## 与 ADK、Anthropic、AutoGen 等方案对照

OpenAI Agents SDK 的 handoff 常转移控制权并 **默认暴露历史**；可用 `input_filter` 收紧。LangGraph 用共享 graph state 传字段，隔离靠你设计 channel 与子图。AutoGen 团队聊天广播消息，隔离弱、协作强。Claude/Cowork 式 subagent 更接近「任务说明书 + 独立 transcript」——与 LeAgent `fork` 语义同类。Google ADK 的 sub-agent 组合也强调显式输入包。选型时先问三件事：**历史默认共享还是默认隔离？文件缓存如何合并？返回是扁平 envelope 还是会话移交？**

## 总结

`delegate` 是定义驱动的隔离子运行：fresh transcript 强制显式交接；FileState 为启动时 clone，仅 `coding_agent` 在 `finally` 中 merge-back；scoped registry 与 child executor 保证 schema 与执行一致；memory/recipe/model 跟 definition 走并可由参数覆盖。理解这三层隔离后，才能把委派当成可控的工程边界，而不是「多开一个聊天窗口」。下一篇把隔离延伸到工具白名单与结构化交接包：[39](39-scoped-tools-and-handoffs.md)。
