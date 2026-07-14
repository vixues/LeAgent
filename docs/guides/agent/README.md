# LeAgent Agent 工程教程

> 一套从基础概念、动手实现到生产工程的中文 Agent 教程。正文以
> LeAgent 当前代码为参考实现，同时对照 Anthropic、OpenAI Agents SDK、
> LangGraph、Google ADK、AutoGen 与 MCP/OWASP 的公开实践。

这套教程不把 Agent 简化成“一段系统提示词加一次模型调用”。你会沿着
`AgentRuntime → run_loop → QueryEngine → query → ToolExecutor` 的真实路径，
逐步理解提示词、上下文、工具、会话、记忆、子 Agent、工作流、恢复、评测与
安全怎样组成一个可长期运行的系统。

## 如何阅读

- **基础**：第一次系统学习 Agent，按 01 → 12 顺序阅读。
- **实践**：准备修改 Agent 行为，继续学习 13 → 30。
- **进阶**：需要记忆、多 Agent 或工作流，学习 31 → 42。
- **生产**：准备部署、评测和治理，学习 43 → 48。
- 每篇都可以独立阅读；遇到不熟悉的 LeAgent 类型，可先查
  [Agent SDK 技术参考](../../technical/agent_sdk_zh.md) 和
  [执行拓扑](../../technical/execution-topology_zh.md)。

教程中的命令默认从仓库根目录执行。Python 命令通常先进入后端：

```bash
cd backend
uv sync
```

标为“离线验证”的测试不需要模型 API Key。涉及真实模型、外部 MCP 服务、
Milvus 或联网工作流的实验会单独注明依赖。

## 第一部分：架构基础

1. [Agent 与 Chatbot 到底有什么区别](01-agent-vs-chatbot.md)
2. [从 ReAct 到 Think-Act Loop](02-think-act-loop.md)
3. [一套 Kernel，多个入口](03-one-kernel-many-ingresses.md)
4. [理解 AgentEvent 流式事件协议](04-agent-event-stream.md)
5. [状态所有权：会话、检查点、记忆与工作流](05-state-ownership.md)
6. [主流 Agent 框架架构对照](06-framework-architecture-comparison.md)

## 第二部分：从零搭建 Agent

7. [用纯 Python 搭一个最小 Agent](07-minimal-python-agent.md)
8. [接入模型与流式输出](08-model-and-streaming.md)
9. [使用 AgentBuilder 声明 Agent](09-agent-builder.md)
10. [设计一个领域 Agent](10-domain-agent-definition.md)
11. [从 YAML 加载和注册 Agent](11-yaml-agent-registration.md)
12. [把最小 Agent 补成工程化 Agent](12-production-ready-agent.md)

## 第三部分：提示词与上下文工程

13. [设计分层提示词系统](13-layered-prompts.md)
14. [解耦 Persona 与 Context Recipe](14-persona-and-context-recipe.md)
15. [编写 Context Source](15-context-source.md)
16. [上下文预算、裁剪与压缩](16-context-budget-and-compaction.md)
17. [设计门控提示词](17-relevance-gated-prompts.md)
18. [Prompt Cache、Fingerprint 与上下文卫生](18-prompt-cache-and-context-hygiene.md)

## 第四部分：工具与能力

19. [设计模型真正会用的工具 Schema](19-tool-schema-design.md)
20. [实现一个 BaseTool](20-build-a-base-tool.md)
21. [ToolRegistry 与 ToolExecutor 执行链](21-tool-registry-and-executor.md)
22. [工具并发、顺序、限流与超时](22-tool-concurrency-rate-limit.md)
23. [文件产物、FileService 与路径沙箱](23-files-artifacts-and-sandbox.md)
24. [接入 MCP 并防御工具投毒](24-mcp-and-tool-poisoning.md)

## 第五部分：多轮对话与持久状态

25. [Session Identity：让多轮对话不失忆](25-session-identity.md)
26. [TieredSessionStore 与 Transcript SSOT](26-tiered-session-store.md)
27. [一条消息的完整生命周期](27-message-lifecycle.md)
28. [长对话的历史压缩](28-history-compaction.md)
29. [跨会话读取 Conversation History](29-cross-session-conversation-history.md)
30. [Checkpoint、暂停与恢复](30-checkpoint-pause-resume.md)

## 第六部分：记忆系统

31. [短期状态、历史与长期记忆的边界](31-memory-boundaries.md)
32. [Episodic、Semantic、Procedural 三类记忆](32-three-store-memory.md)
33. [Memory Formation：决定什么值得记住](33-memory-formation.md)
34. [混合召回、去重与重排](34-hybrid-recall-reranking.md)
35. [异步预取、超时与无向量降级](35-recall-prefetch-degradation.md)
36. [记忆隐私、遗忘与保留策略](36-memory-privacy-retention.md)

## 第七部分：多 Agent 与工作流

37. [什么时候应该拆分子 Agent](37-when-to-use-subagents.md)
38. [Delegate、上下文隔离与状态合并](38-delegation-context-isolation.md)
39. [Scoped Tools 与结构化 Handoff](39-scoped-tools-and-handoffs.md)
40. [Manager 与 Supervisor 编排模式](40-supervisor-orchestration.md)
41. [把 Agent 变成 DAG 节点](41-agent-nodes-and-dag.md)
42. [Human-in-the-loop 与可恢复工作流](42-human-in-the-loop-workflows.md)

## 第八部分：可靠性与生产化

43. [Hooks、Guardrails 与策略执行点](43-hooks-and-guardrails.md)
44. [错误恢复与自校正](44-error-recovery-self-correction.md)
45. [Trace、ExecutionRun 与 OpenTelemetry](45-tracing-and-otel.md)
46. [Agent 轨迹评测与回归测试](46-trajectory-evaluation.md)
47. [Agent 安全控制面](47-agent-security-control-plane.md)
48. [成本、延迟、扩展与生产检查表](48-production-cost-latency-scaling.md)

## 教程统一约定

每篇教程尽量回答八个问题：

1. 这个机制解决什么问题？
2. 它在整条 Agent 数据流的哪个位置？
3. LeAgent 当前由哪些文件和类型实现？
4. 最小实现是什么？
5. 如何用离线命令验证？
6. 生产环境还缺哪些条件？
7. 常见失败方式是什么？
8. 它与其他主流 Agent 框架的同类概念有何异同？

代码与文档冲突时，以代码和测试为准。尤其注意：

- 新集成应从 `leagent.sdk` 导入公共类型；`leagent.runtime` 仍承担兼容层角色。
- `AgentController` 是会话、SSE 与持久化编排壳，不是第二套 Agent loop。
- 子 Agent 使用独立 transcript；文件状态是 fork 时复制、结束后合并，并非实时共享。
- Session transcript、turn checkpoint、长期 memory 和 workflow state 是四类不同状态。
- `ExecutionRunRegistry` 当前是进程内注册表，多 worker 部署必须考虑粘性会话。

## 相关资料

- [Agent 面试题库](../../interview/README.md)
- [LeAgent 产品使用教程](../../tutorial_zh.md)
- [Agent SDK 技术参考](../../technical/agent_sdk_zh.md)
- [Agent Runtime 技术参考](../../technical/agent-runtime_zh.md)
- [执行拓扑](../../technical/execution-topology_zh.md)
- [Agent 系统调研](../../technical/agent-systems-survey_zh.md)
- [Agent Trace](../../technical/agent-trace_zh.md)
- [工具参数契约](../../technical/tool-parameters_zh.md)
- [微信接入自建 Agent](../weixin-agent-from-scratch.md)

