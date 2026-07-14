# 40. Manager 与 Supervisor 编排模式

## 定位与先修

本文讨论多 Agent 协作时常见的 Manager/Supervisor 模式，并澄清 LeAgent 中的实现事实：**Supervisor 是编排模式与角色命名，不是独立运行时类**。先修 [37](37-when-to-use-subagents.md)–[39](39-scoped-tools-and-handoffs.md)。务必区分：仓库里的 `DevServerSupervisor`（`project.runtime`）管的是 coding project 的 `npm run dev` 等子进程生命周期，与本文「多 Agent 路由、委派、验收」毫无关系——写架构图时不要画在同一条泳道。

## 目标

完成后你应能回答：

1. Manager（委派并回收结果）与 Supervisor（持续路由/监控工人）在职责上差在哪里；
2. 如何在 LeAgent 用父 Agent、`runtime.delegate`、条件节点与 `Agent.*` DAG 节点拼出两种模式；
3. 为何不应在文档或设计里假设存在 `class Supervisor` 或中央调度邮箱；
4. 何时改用纯 DAG、何时改用单 Agent + 直接工具；
5. 并行工人与 FileState merge 语义会带来哪些协调成本。

## 心智模型

两种模式共享同一 kernel，差别在 **谁决定下一跳**：

```text
        ┌─────────────────────────┐
        │  Coordinator（模式角色） │
        │  父 Agent / DAG 路由点   │
        └───────────┬─────────────┘
                    │ delegate / Agent 节点 / Condition
        ┌───────────┼───────────┐
        ▼           ▼           ▼
     Worker A    Worker B    Worker C
   (fresh tx)  (scoped)   (budgeted)
        │           │           │
        └───────────┴───────────┘
                    │ envelope / AGENT_OUTPUT_NAMES
                    ▼
              验收 / 重试 / 人工 / 结束
```

**Manager 模式：** 一或几次委派，拿回 envelope，自己汇总结束——对应服务代码里多次 `runtime.delegate`，或 DAG 上顺序 `Agent.research` → `Agent.writer`。Coordinator 负责把上一工人的 `text`/`activity` 摘要写进下一 prompt 或 `state.set` 变量。

**Supervisor 模式：** 根据中间结果反复决定「下一位工人是谁 / 是否重试 / 是否升级人工」——对应父模型在 think-act 循环里多次调 `AgentTool`，或 DAG 上的 `Condition(success)`、回边与 `HumanReviewNode`。路由策略可以写在系统提示、Python 路由函数或 workflow 图里，**不是**内置 Selector 算法对象。

## 读写数据流

**父 Agent 作 coordinator。** 系统提示规定可用工人（`AgentDefinition` 名称）、委派时机与验收清单（`success`、`changed_files`、测试证据）。父通过 `AgentTool`（工具名 `agent`，别名 `subagent`、`delegate`）或服务层 `AgentRuntime.delegate` 调工人。每次调用仍是 fresh transcript + scoped tools + 独立 `max_turns`；父级必须把上一 envelope 的关键字段显式写进下一 handoff prompt，因为工人 **不共享** 父聊天 transcript。

**DAG 作 coordinator。** `agent_node_factory` 为每个 definition 生成 `Agent.<name>` 节点，执行统一走 `run_agent_node`。节点产出 `AGENT_OUTPUT_NAMES` 六元组；`Condition`/`If` 读 `success` 或 workflow 变量；失败可导向 `Agent.fixer` 或 `HumanReviewNode`（`block_execution="awaiting_review"` → `WorkflowStatus.WAITING_HUMAN`）。Cron、`workflow_run`、聊天里嵌的工作流触发 **同一** `WorkflowExecutor`；`chat_workflow` 把步进 playbook 编译成线性 `WorkflowDocument`，不是第二套运行时。

**状态如何汇合。** 工人 envelope 写入节点输出槽或 `output_var`；coordinator 通过图边或父 prompt 传递摘要。`TieredSessionStore` 的聊天 transcript、`WorkflowStateStore` 的图进度、`CheckpointStore` 的 agent pause 仍是不同 durable owner——Supervisor 逻辑必须接受「没有自动团队聊天记录」。

**不要混淆的同名物。** 聊天里起名 `supervisor_agent` 的 `AgentDefinition` 没有特殊调度权，除非你写进 prompt 与工具策略。`DevServerSupervisor` 启动/监控 dev server 进程，不能编排多 Agent。

## 真实实现中的边界

**没有中央 Supervisor 类。** 找不到类似 AutoGen `SelectorGroupChat` 的内置发言人选择器。动态选人 = 父模型决策、你自己的 `if envelope["success"]`、或 DAG 条件节点。

**并行工人要自己管汇合。** DAG 引擎支持并行分支与 `ParallelNode`；纯 delegate 循环默认串行。并行时注意 workspace 写冲突、重复 `project_read`，以及仅 `coding_agent` 子路径的 FileState merge-back——两个 coding 工人并行可能让父 cache 合并不确定，优先串行或分区目录。

**预算层层叠加。** 父 `max_turns` 与每个工人 `max_turns` 独立。Supervisor 式多轮路由（调研→写→修→再审）容易指数耗 token 与工具步数——给工人更短预算、给路由更严停止条件（最大工人数、最大重试）。

**失败不会自动换人。** 除非你在 Condition 边或父提示里写「`success=False` 则委派 fixer」，否则 envelope 失败只会停在该节点或返回父级处理。

**观测。** `EventManager` 的 `AGENT_*` / `FLOW_*` 与 OTel `run_id`/`parent_run_id` 可串起父子 run；ExecutionRunRegistry 当前为进程内单例，多 worker 部署需 sticky session 或未来 durable run store。

## 示例与验证

**模式 A — Manager（两次委派）：** 父先 `delegate("subagent", 调研 prompt)`，验收 `success` 与 `activity` 无越权；再把第一次 `text` 摘要写进第二次 `delegate("script_agent", 起草 prompt)`。断言两次 envelope `success`，且第二次 handoff 含第一次要点。

**模式 B — Supervisor-like DAG：**

```text
Agent.research → Condition(success) → Agent.writer
                      │ fail
                      ├→ Agent.fixer → HumanReviewNode
                      └→ HumanReviewNode (awaiting_review)
```

用 `config/demo-workflows/demo-agent-pause-resume.yaml` 或自建图跑一遍：检查 `AGENT_OUTPUT_NAMES` 接线、`success` 分支、人工节点 `WAITING_HUMAN` 与 `POST /api/v1/workflow/prompts/{prompt_id}/resume`。

**反例：** 为三句澄清问题建 Supervisor 图 + 三个工人——交接与验收成本超过收益；单 Agent + `ask_user` 或一次 `project_grep` 更合适。

## 常见误区

- **「LeAgent 内置 Supervisor 运行时。」** 不，是模式；实现是 delegate + Agent 节点 + 图条件。
- **「起名 Supervisor 的 AgentDefinition 有特殊调度。」** 无，除非 prompt/工具/图边定义了路由。
- **「Workers 共享团队聊天记录。」** 默认 fresh transcript，不共享。
- **「DevServerSupervisor 能编排多 Agent。」** 不能；它管 dev 进程。
- **「工人失败会自动换人。」** 要你做 Condition、重试边或父级逻辑。
- **「Supervisor 一定要多 Agent。」** 单 Agent 多步 think-act 也常足够；多 Agent 买的是隔离与并行，不是魔法。

## 与 ADK、Anthropic、AutoGen 等方案对照

LangGraph 的 supervisor 示例通常是显式 state + 路由节点，与「DAG 作 coordinator」最接近。AutoGen 的 `SelectorGroupChat`/`RoundRobinGroupChat` 把说话权算法做进框架，工人共享团队消息总线。OpenAI Agents SDK 用 handoff 转移会话控制权，偏对话连续。Google ADK 提供 multi-agent 组合原语，但仍要选 Manager vs Supervisor 语义。LeAgent 刻意保持薄：提供 **delegate + Agent 节点 + 同一 kernel**，把 Supervisor 算法留给应用与图，避免再维护一套并行编排内核与第二份 transcript SSOT。

## 总结

Manager/Supervisor 描述的是 **路由与验收职责放在何处**，而不是某个必装类。用父 Agent 循环或 DAG 条件组装即可；每次工人调用仍遵守 fresh transcript、scoped tools 与 envelope 验收。把 Agent 沉进图、统一六元组输出槽的细节见 [41](41-agent-nodes-and-dag.md)；人工暂停与恢复见 [42](42-human-in-the-loop-workflows.md)。
