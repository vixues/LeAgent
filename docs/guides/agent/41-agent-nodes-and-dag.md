# 41. 把 Agent 变成 DAG 节点

## 定位与先修

本文说明 Agent 如何成为工作流一等公民，衔接编排模式与可恢复执行。先修 [02](02-think-act-loop.md)、[40](40-supervisor-orchestration.md)，并建议扫一眼 `workflow/nodes/agent_exec.py` 与 `agent_node_factory.py`。核心事实：内建 Script/Coding 节点与生成式 `Agent.<name>` 节点 **都** 经 `run_agent_node`；输出槽顺序以代码常量 **`AGENT_OUTPUT_NAMES`** 为唯一契约，旧注释若只写前三项视为过时简述。

## 目标

完成后你应能回答：

1. `Agent.<name>` 如何从 `AgentRegistry` 自动生成节点 schema；
2. dual path：有父 `agent_controller` 时 `delegate`，否则 `stream`/`resume` 各意味着什么；
3. `AGENT_OUTPUT_NAMES` 六元组每项的下游用途；
4. `block_execution=awaiting_user_input` 与 `__resume__<node_id>` 如何与图调度、kernel checkpoint 对齐；
5. `chat_workflow` 编译路径与画布 DAG 是否共用执行器。

## 心智模型

Agent 节点 = definition 驱动的图步骤，不是聊天里的旁路脚本：

```text
AgentDefinition ──agent_node_factory──► WorkflowNode (node_id = Agent.<name>)
                                              │
                                              ▼
                                       run_agent_node(...)
                              ┌───────────────┴───────────────┐
                              │ ctx.agent_controller 存在？      │
                              ▼                               ▼
                    runtime.delegate                 runtime.stream
                    （子 Agent 语义）                  （standalone 会话）
                              │                               │
                              └───────────────┬───────────────┘
                                              ▼
                         NodeOutput.values 对齐 AGENT_OUTPUT_NAMES
                         (text, success, steps_count, checkpoint_id,
                          activity, produced_files)
```

暂停时 standalone 路径可返回 `block_execution=AWAITING_USER_INPUT`，调度器暂停整图；恢复时 executor 把用户答案放进 `state.variables["__resume__<node_id>"]`，节点走 `runtime.resume(checkpoint_id, answer)` 续跑，而不是换新 transcript 从头 `stream`。

## 读写数据流

**工厂与 schema。** `agent_node_factory` 为每个 `AgentDefinition` 建 `WorkflowNode` 子类：`node_id` 为 `Agent.<name>`。输入含 `prompt`、可选模型覆盖、`max_turns`、`allowed_tools`、`project_path`、`read_only`、`output`（写入 workflow 变量的文本）。hidden 注入 `AGENT_RUNTIME`、`TOOL_CONTEXT`、`WORKFLOW_STATE`、session/user id、`abort_event` 等。`read_only=true` 时 allow 收束为项目只读工具集，与 scoped 哲学一致。新增 Agent 定义后重启或热加载 registry，工厂会为每个 name 生成对应节点类型，无需手写 `WorkflowNode` 子类。

**执行主路径 `run_agent_node`。** 解析 prompt（可含状态模板）、合并 `playbook_ids`，读取 resume payload：若 `state` 存在 `__resume__<node_id>` 且能配对已 stash 的 `checkpoint_id`，则 **`runtime.resume`** 续跑。否则：

- **有 parent `agent_controller`**（聊天 turn 内嵌工作流）→ `runtime.delegate`，`meta["mode"]="delegate"`，享受子 Agent 的 fresh transcript 与 FileState clone/merge 语义；
- **无 parent**（工作流页、cron、独立运行）→ `runtime.stream` 经 `_run_standalone_stream`，`meta["mode"]="standalone"`。

事件经 `_aggregate_agent_events` 折叠 `text`、步数、`activity`、`produced_files`、`checkpoint_id` 与 `reason`。

**输出契约 `AGENT_OUTPUT_NAMES`。** 代码常量（source of truth）：

```python
AGENT_OUTPUT_NAMES = (
    "text",
    "success",
    "steps_count",
    "checkpoint_id",
    "activity",
    "produced_files",
)
```

`_finalize` 按此顺序填 `NodeOutput.values`；若配置 `output_var` 则 `state.set(output_var, text)`。`checkpoint_id` stash 到 `state.metadata["agent_checkpoints"]` 供 resume 配对。

**暂停与 block。** standalone 且 `agg.reason == awaiting_user_input` 并有 `checkpoint_id` 时，返回带 `block_execution=AWAITING_USER_INPUT` 的 `NodeOutput`，`ui` 可含 `question` 与 `checkpoint_id`。图调度器据此暂停；调用方通过 `POST /api/v1/workflow/prompts/{prompt_id}/resume` 提交答案，变量写入 `__resume__<node>` 后重入节点。

**Chat workflow 同构。** `chat_workflow.compile` 把步进式 playbook 编译成 **线性** `WorkflowDocument`，嵌入同一 `WorkflowExecutor` 与 `run_agent_node`——聊天步进卡与画布图不是两套 Agent 运行时。

## 真实实现中的边界

**以常量与 schema.outputs 为契约。** 接线、模板、测试断言应 import `AGENT_OUTPUT_NAMES` 或与其顺序一致。工厂模块顶部注释若写「outputs: text/success/steps_count」，以 schema 与常量为准（六个）。

**`success` 含可恢复暂停。** 聚合逻辑把 `awaiting_user_input` 也视为可接受成功态之一（与 SDK `AgentResult` 类似）；下游判断「业务完成」应再看 `reason`、是否仍 `block_execution`、或是否需第二次 resume。

**双路径行为差。** delegate 路径有父 FileState clone/merge、coding 变体 merge-back；standalone stream 更像独立会话，暂停靠 kernel checkpoint + workflow resume。同一节点在「聊天里嵌工作流」与「纯工作流页运行」可能走不同 path，调试时看 `metadata.mode`。

**非幂等。** 生成节点标记 `not_idempotent=True`——重跑可能重复副作用；resume 路径专为同 turn checkpoint 续跑设计，不应混作「幂等重试」。

**Abort 传播。** `hidden.abort_event` 转发到 agent kernel；取消 workflow 应 abort 进行中的 agent turn。聊天里取消 SSE 也应经同一 abort 链停止嵌套 delegate。

**进度与 live streaming。** `ProgressRegistry` 经 `HiddenHolder` 把 assistant delta、tool call 行折叠进节点 body 预览；这不改变 `AGENT_OUTPUT_NAMES` 终态，但影响编辑器/执行页的实时观感。排障「节点卡住」时同时看 `block_execution` 与 progress 是否仍在收 delta。

**无 runtime 时显式失败。** `hidden.agent_runtime is None` 返回带 `error` 的 `NodeOutput`，而不是裸异常击穿 executor。

## 示例与验证

**画布/demo：** 导入 `config/demo-workflows/demo-agent-pause-resume.yaml`，拖入 Script/Coding 或 `Agent.<name>` 节点，prompt 要求先 `ask_user` 再完成。运行后图应暂停；`POST /api/v1/workflow/prompts/{prompt_id}/resume` 提交答案后，`__resume__<node>` 触发 `runtime.resume`，`plan`/`output` 变量有终稿，`checkpoint_id` 槽非空。若节点在聊天 turn 内执行且存在 `agent_controller`，同一提问可能走 delegate 路径，暂停与恢复仍应通过正确的 scope 与 checkpoint 字段联调，而不是假设「在聊天里就不需要 workflow resume API」。

**离线断言：**

1. 各 Agent 节点 `schema.outputs` 的 id 列表等于 `AGENT_OUTPUT_NAMES`；
2. `_finalize` 的 `values` 长度与顺序一致；
3. `tests/workflow/test_agent_nodes.py` — `awaiting_user_input` 时 `block_execution` 正确；
4. 无 `agent_runtime` 时返回明确 error 字符串；
5. delegate 路径 `metadata.mode=="delegate"`，standalone 为 `standalone`，resume 为 `resume` 且 `resumed_from` 等于 stash 的 checkpoint。

```bash
cd backend
uv run pytest tests/workflow/test_agent_nodes.py tests/workflow/test_executor_resume.py -v
```

## 常见误区

- **「只接 text 槽就够。」** 分支常用 `success`；恢复常用 `checkpoint_id`；审计常用 `activity`；文件下游用 `produced_files`。
- **「文档写三个输出所以只有三个。」** 以 `AGENT_OUTPUT_NAMES` 与 schema 为准（六个）。
- **「Agent 节点失败图就崩。」** 可把 `success` 导入 `Condition`，导向修复或 `HumanReviewNode`。
- **「chat 步进卡与 DAG 是两套 Agent。」** 编译后共用 `WorkflowExecutor` 与 `run_agent_node`。
- **「resume 会换新 transcript 重来。」** 设计是同 checkpoint 续跑；新 prompt 应新开节点或新 run。
- **「delegate 与 stream 输出形状不同。」** 最终都折成同一六元组（delegate 经 envelope 映射）。
- **「有 checkpoint 就能无限次 resume。」** 每次 resume 消费用户答案并推进 turn；应用应防止重复提交同一答案导致双副作用。

## 与 ADK、Anthropic、AutoGen 等方案对照

LangGraph 把 LLM 节点与工具节点放进图，state schema 完全自定；LeAgent 用固定六元组降低画布接线歧义与「下游猜字段名」成本。Temporal 等外部编排器常把 Agent 当 activity，暂停靠 workflow 信号；LeAgent 把 kernel `checkpoint_id` 透出到节点输出，使 **DAG 调度** 与 **Agent 暂停** 对齐。AutoGen 少「一节点一 agent 固定输出槽」的可视化约定。统一槽位的代价是扩展新输出需同步改常量、schema 与文档；收益是 Supervisor 图、HITL 恢复与产物节点可以稳定接线，而不必每个项目自定义 JSON 形状。

## 总结

Agent 节点 = definition 驱动的 `run_agent_node`：dual path（delegate / stream+resume），输出严格对齐 `AGENT_OUTPUT_NAMES`。把该常量当作公共 API；图编排、Supervisor 路由与 HITL 恢复才可预期。人工审批节点、`awaiting_review` 与 chat/workflow 双入口 resume 见 [42](42-human-in-the-loop-workflows.md)。
