# 39. Scoped Tools 与结构化 Handoff

## 定位与先修

本文讲委派时的能力边界与交接契约，是子 Agent 系列的「权限 + 协议」篇。先修 [37](37-when-to-use-subagents.md)、[38](38-delegation-context-isolation.md)。核心不变量：**模型看得到的工具 schema** 与 **executor 真正能执行的工具** 必须来自同一 `ToolRegistry.scoped` 结果。Handoff 在 LeAgent 里主要是 **结构化任务包（prompt）+ 结构化返回 envelope**，而不是默认移交整段父对话控制权。

## 目标

完成后你应能回答：

1. `ToolRegistry.scoped(allow, deny)` 与 `make_child_executor` 如何一起收紧权限；
2. `DEFAULT_AGENT_TOOL_DENIED_TOOLS` 默认挡住哪些危险能力，何时可被 definition 覆盖；
3. 一份合格 handoff prompt 与父级验收 envelope 应包含哪些字段；
4. 它与 OpenAI 式 conversation handoff、MCP server 边界的异同；
5. 工作流 `Agent.*` 节点的 `read_only` 与 scoped 哲学是否一致。

## 心智模型

两道闸门，一道契约：

```text
父 ToolRegistry
   │ _filter_registry → scoped(allow, deny, exact, only_enabled)
   ▼
子 registry（LLM tool schema 的唯一来源）
   │ make_child_executor(parent_executor, child_registry)
   ▼
子 ToolExecutor（运行时查找只走子 registry）

Handoff 契约：
  父 → 子：厚 prompt（目标/输入/禁区/输出格式/完成条件/验收证据）
  子 → 父：SubagentResult（text/success/partial/error/activity/changed_files/...）
  图 → 下游：AGENT_OUTPUT_NAMES 六元组（见 41）
```

若只过滤「系统提示里的可用工具描述」却不换 executor，模型仍可能通过规范名或别名调到父工具——LeAgent 用 **同一 scoped registry 驱动 schema 与执行** 堵住这条缝。Handoff 也不是第二套消息总线：没有自动把父 transcript 摘要塞进子级，也没有把子全程消息并回父 transcript。

## 读写数据流

**Allow / Deny 解析顺序。** `AgentRuntime.delegate` 先取 `definition.tools.allow/deny`，再叠加调用方 `extra_denied_tools` 与 `AgentTool` 路径注入的默认 deny。`_filter_registry` 薄封装 `registry.scoped(allow, deny, match="exact", only_enabled=True)`：`allow=None` 表示在父已启用集合上再应用 deny；非空 `allow` 为白名单。别名解析在 scoped 层处理，设计 allow 列表要用规范名并写测试锁住别名可达性。

**默认拒绝表。** `DEFAULT_AGENT_TOOL_DENIED_TOOLS` 为：

```text
project_write, project_edit, project_apply_patch, project_shell,
code_execution, coding_agent,
coding_project_scaffold, coding_project_run, coding_project_stop
```

意图是：经 `AgentTool`（`agent`/`subagent`/`delegate`）的一般委派默认偏只读、低副作用。若 definition 的 allow 显式包含写工具，或代码路径直接 `delegate` 并传入更宽 allow，可以放开——但应配套人工审批、更短 `max_turns` 与父级验收 `changed_files`。

**Child executor 拷贝策略。** `make_child_executor` 复制 `default_timeout`、`max_parallel`、`_permission_context`、`service_manager`，**registry 换成 child**。权限框架（destructive approval 等）仍在，只是可解析工具名变少。嵌套写工具预览经 `nested_preview_emit` 挂到父 `tool_call_id`，不改变执行边界。

**Handoff prompt 最低字段。** 目标（交付物是什么）、输入位置（路径/URL/变量名）、允许动作、禁止动作、输出 schema（列表/JSON/行号证据）、完成条件与失败条件。对 coding 任务再加：是否允许改文件、必须跑的测试名、`verification_gap` 为空才算过。

**返回 envelope 验收。** 父级应检查：`success` 与 `partial`、`error`、工具 `activity` 是否越权、`changed_files`/`produced_files`、coding 的 `verification_gap`。工作流 Agent 节点再把结果折成 `AGENT_OUTPUT_NAMES`：`text, success, steps_count, checkpoint_id, activity, produced_files`——代码常量是公共契约，不以旧注释「三个输出」为准。

**只读捷径。** 生成式 `Agent.<name>` 节点的 `read_only=true` 会把项目工具收束到 read/grep/glob/tree 一类——与 scoped 同一哲学：在节点 schema 层收紧，而不是只靠 prompt 自律。

## 真实实现中的边界

**定义 allow 为空的语义。** `list(definition.tools.allow) or None`：空列表会变成 `None` 从而「继承父集合再 deny」，未必是「零工具」。若要真正最小权限，应在 definition 写明确白名单，并用 `tests/test_subagent_scoped_executor.py` 断言 child executor 解析不到父独占工具。

**Handoff 不是会话移交。** 没有 OpenAI handoff 那种默认「下一位 agent 看见全文历史」。Coordinator 必须把上一工人 envelope 摘要手写进下一 prompt 或 workflow 变量。

**嵌套委派。** 子 Agent 仍可调用 `agent` 工具再委派，每层都重新 scoped；预算与副作用叠加，Supervisor 式多轮路由容易指数耗费用——给工人更短 `max_turns`、更严 deny。

**与工具审批协同。** 即使 allow 含 `project_write`，`ToolExecutor` 仍可按 `needs_approval` 暂停父/子 turn（`AWAITING_USER_INPUT`）。Scoped 管「能不能解析到工具」，approval 管「副作用是否立刻执行」——两层都要设计。

## 示例与验证

```python
result = await runtime.delegate(
    parent,
    "subagent",
    (
        "目标：汇总 workflow agent_exec 的暂停与 resume 标签。\n"
        "输入：backend/leagent/workflow/nodes/agent_exec.py\n"
        "禁止：写文件、shell、code_execution。\n"
        "输出：要点列表 + 证据行号 + 相关测试文件名。"
    ),
    allowed_tools=["project_read", "project_grep"],
    extra_denied_tools=["project_shell"],
    max_turns=4,
)
assert result["success"]
for step in result.get("activity") or []:
    assert step.get("name") not in DEFAULT_AGENT_TOOL_DENIED_TOOLS
```

验收路径：

1. `tests/test_subagent_scoped_executor.py` — child executor 绑定 child registry；
2. `tests/test_subagent.py` — allow/deny、turn budget、父取消传播；
3. 故意把 `project_write` 放进 allow 才应出现 `changed_files`；
4. 工作流节点 `read_only=true` 时 schema 工具列表与执行一致。

## 常见误区

- **「deny 写在 system prompt 就够了。」** 不够；必须 scoped + child executor，否则 schema/执行分裂。
- **「handoff = 把会话转交另一个 agent 接着聊。」** LeAgent 默认是任务委派 + envelope，不是控制权移交。
- **「返回 text 成功即业务成功。」** 查 envelope、测试与 `verification_gap`。
- **「子级会继承父级全部工具除非写 deny。」** 还受 definition.allow、AgentTool 默认 deny 与 scoped exact 匹配影响。
- **「read_only 只是 UI 提示。」** 节点层会收紧 allow 列表，与 executor 同源。
- **「放开写工具就等于已审批。」** approval 与 HumanReview 仍是独立门禁。

## 与 ADK、Anthropic、AutoGen 等方案对照

OpenAI handoff 强调对话控制权转移，可用 `input_filter` 改写可见历史；LeAgent 强调任务包与 envelope。MCP 用 server 边界隔离工具集合——类似 scoped registry，但 LeAgent 在单进程内用 registry 切片。LangGraph 常用独立 node + 显式 state 字段传交接；AutoGen 靠 chat 消息约定工人输出。LeAgent 把 **工具集合** 与 **返回 envelope** 提为一等契约，历史默认不分享，适合审计型桌面 Agent 与可复现工作流。

## 总结

Scoped tools 让 schema 与执行共享同一白名单；`DEFAULT_AGENT_TOOL_DENIED_TOOLS` 降低委派默认副作用。结构化 handoff = 厚 prompt 任务包 + 厚返回 envelope + 父级验收清单。写清禁区并用测试锁住 executor，比在提示词里喊「不要乱用工具」可靠得多。编排多个工人、用图做路由时见 [40](40-supervisor-orchestration.md)。
