# 06｜主流 Agent 框架架构对照

## 定位、难度与先修

- **定位**：把 LeAgent 的抽象映射到常见生态，便于选型与面试/系统设计讨论。
- **难度**：★★★☆☆
- **先修**：[01](01-agent-vs-chatbot.md)–[05](05-state-ownership.md)

## 学习目标

1. 用「循环 / 状态 / 工具 / 多 Agent / 可观测」五轴比较框架，而不陷于 API 细节。
2. 说出 LeAgent 与 Codex、Claude Agent SDK、OpenAI Agents SDK、LangGraph、Google ADK、AutoGen 的概念对应。
3. 明确「概念对齐 ≠ API 等价」：迁移时必须以各自文档与本仓库代码为准。

## 核心心智模型：对齐意图，而非对齐类名

成熟 Agent 系统都在回答同一组问题：谁驱动循环？状态存哪？工具如何治理？如何暂停恢复？如何委托？如何观测？

下表是**概念映射**，不是声称接口兼容：

| 问题 | LeAgent | 常见对应物 |
|------|---------|------------|
| 统一内核 | `run_loop` + `QueryEngine` | Codex core loop、Claude Agent loop、OpenAI Runner |
| 声明式 Agent | `AgentDefinition` / `AgentBuilder` | OpenAI `Agent`、ADK Agent |
| 工具执行 | `ToolRegistry` + `ToolExecutor` | function tools / MCP tools |
| 短期会话 | `TieredSessionStore` | ADK Session、Agents SDK Session |
| 可恢复暂停 | `CheckpointStore` | LangGraph checkpointer、Claude SessionStore |
| 长期记忆 | `AgentMemory` 三 store | ADK Memory、AutoGen Memory protocol |
| 子 Agent | `delegate` + fork | Claude subagents、OpenAI handoffs（语义不同） |
| DAG / 确定性编排 | `WorkflowExecutor` | LangGraph StateGraph、AutoGen Teams（团队轮转） |
| 钩子 | `HookManager` | Claude hooks、ADK callbacks |
| 追踪 | TraceStore + OTel | Agents SDK tracing、LangSmith |

更完整的调研记录见 [`docs/technical/agent-systems-survey_zh.md`](../../technical/agent-systems-survey_zh.md)。

## 有意偏离（理解差异才算理解架构）

LeAgent 文档写明的偏离包括：

1. **无循环内 steering 队列**：运行中的工具批次不中途插入用户消息；到达 `awaiting_user_input` / abort 后由门面决定下一步，并用 checkpoint 补偿可恢复性。
2. **进程内子 Agent**：轻量共享服务，沙箱隔离交给 code/project 层，而非默认 spawn 独立进程。
3. **Entry-point 插件**而非扫描魔法目录：workflow 节点 / provider / context source 用 `importlib.metadata`。

## 分步：选型清单（教学用）

需要**强图控制流、time-travel、显式边** → 研究 LangGraph 类图引擎；在 LeAgent 里复杂确定性流优先写 Workflow DAG，Agent 节点嵌入推理。

需要**库化嵌入、丰富 hooks** → 对照 Claude Agent SDK；LeAgent hooks 已在 `run_loop` 单点派发。

需要**handoff 身份转移** → OpenAI Agents SDK；LeAgent 更常见是 `delegate` 返回摘要，父级仍拥有会话（详见第 38–40 篇）。

需要**Session/State/Memory/Artifacts 清晰分层** → Google ADK；与「transcript / scratch / long-term」拆分同构。

需要**多角色团队轮转与终止条件** → AutoGen Teams；LeAgent 可用多 agent 定义 + 工具委派 + workflow，不是同一种 group chat 原语。

## 验证方式

本篇偏概念。实践验证：

```bash
cd backend
uv run pytest tests/test_runtime_sdk.py tests/test_execution_topology_invariants.py -v
```

阅读：`docs/technical/agent-systems-survey_zh.md`、`agent_sdk_zh.md`。

## 常见误区

1. **「学了 LangGraph 就能照抄 LeAgent API」**：图节点 ≠ `run_loop` 轮次语义。
2. **「handoff == delegate」**：handoff 常转移对话所有权；delegate 多是短暂委派并回传摘要。
3. **「有 memory 模块就等于生产记忆」**：还要看写入门控、召回预算与无向量降级。
4. **「框架越多越强」**：多套循环并存通常比少套但统一的内核更危险。

## 数据流对照：同一用户请求在不同框架的「落点」

概念上，请求总会经过：入口鉴权 → 组装上下文 → 模型决策 → 工具/子代理副作用 → 状态提交 → 可观测事件。各框架用不同对象命名这些步骤。对照时画出你系统里的真实路径，再映射名词，而不是从外框 API「翻译」进 LeAgent。

| 关注点 | 你在 LeAgent 应打开的路径 | 常见外部词汇 |
|--------|---------------------------|--------------|
| 循环 | `sdk/kernel/loop.py` + `agent/query.py` | Runner / agent loop / ReAct |
| 声明 | `runtime/definition.py` + Builder | Agent() / ADK Agent |
| 会话 | `services/session/` | Session / thread |
| 暂停 | `CheckpointStore` | checkpointer / interrupt |
| 记忆 | `AgentMemory` | MemoryService / Memory Bank |
| 图 | `WorkflowExecutor` | StateGraph / workflow |
| 钩子 | `HookManager` | hooks / callbacks |

### 选型排障（团队讨论用）

1. **争论 handoff 还是 delegate**：先问会话所有权是否转移；LeAgent 默认委派回传摘要。见 [38](38-delegation-context-isolation.md)–[40](40-supervisor-orchestration.md)。  
2. **争论要不要上图**：步骤稳定且要并行/审计 → Workflow；步骤依赖口语理解 → 父 Agent + `delegate`。  
3. **争论记忆放哪**：先读 [05](05-state-ownership.md)/[31](31-memory-boundaries.md)，避免把 checkpointer 当长期记忆。  
4. **迁移幻觉**：类名相似不等于语义相同；以本仓库测试与技术调研文档为准。

更深调研记录：[`docs/technical/agent-systems-survey_zh.md`](../../technical/agent-systems-survey_zh.md)。读完本篇应能用五轴比较框架，而不是背 API。

## 总结与延伸阅读

框架对照的价值是借用成熟词汇讨论你自己的系统，而不是追逐名词。LeAgent 选择「单内核 + 声明式定义 + 四类状态分治 + DAG 补确定性」。

- [07｜最小 Python Agent](07-minimal-python-agent.md)
- [Agent 系统调研](../../technical/agent-systems-survey_zh.md)
- [Agent SDK](../../technical/agent_sdk_zh.md)
