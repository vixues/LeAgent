# LeAgent Agent 面试题库

本目录以 LeAgent 的真实架构为主线，系统回答 AI Agent 面试中的基础概念、工程实现与 Staff/Principal 级系统设计问题。答案先说明通用原理，再结合 LeAgent 的单一 think-act kernel、工具系统、工作流引擎、三层记忆、检查点、可观测性与安全控制面落地。

## 阅读说明

- 编号采用“章号.题号”，与原始问题顺序一致。
- “在 LeAgent 中”描述仓库当前实现；通用方案或建议不会冒充已实现能力。
- 闭源产品相关设计仅依据公开能力进行架构分析，不代表其内部实现。
- 框架和模型能力会持续变化，选型应以目标版本的官方文档和实测结果为准。
- 本目录采用面试问答体；需要循序渐进的实现教程，请阅读
  [LeAgent Agent 工程教程](../guides/agent/README.md)。

## 目录

1. [Agent 基础概念](01-agent-basics.md)
2. [Prompt Engineering](02-prompt-engineering.md)
3. [Tool Calling](03-tool-calling.md)
4. [RAG](04-rag.md)
5. [Memory](05-memory.md)
6. [Planning](06-planning.md)
7. [Multi-Agent](07-multi-agent.md)
8. [LangGraph / Agent Framework](08-agent-frameworks.md)
9. [Agent 系统设计](09-system-design.md)
10. [Agent Evaluation](10-evaluation.md)
11. [Agent Production](11-production.md)
12. [安全](12-security.md)
13. [模型层面](13-models.md)
14. [Coding 高频题](14-coding.md)
15. [大厂高频深挖题](15-deep-dive.md)

## LeAgent 架构参考

- [执行拓扑](../technical/execution-topology_zh.md)
- [Agent Runtime](../technical/agent-runtime_zh.md)
- [Agent SDK](../technical/agent_sdk_zh.md)
- [Agent Trace](../technical/agent-trace_zh.md)
- [安全控制平面](../technical/security-control-plane_zh.md)
- [工具参数契约](../technical/tool-parameters_zh.md)

