# 45｜Trace、ExecutionRun 与 OpenTelemetry：一次运行如何被看见

## 定位、难度与先修

- **定位**：可观测性篇。建立 `run_id`、持久 Agent Trace、OpenTelemetry 导出与聊天 transcript 的边界。
- **难度**：★★★☆☆
- **先修**：[03｜一套 Kernel，多个入口](03-one-kernel-many-ingresses.md)、[05｜状态所有权](05-state-ownership.md)；了解 SSE/WebSocket 只是传输，不是状态真源。

## 学习目标

完成本篇后，你应该能：

1. 用 `ExecutionRun` 解释一次 chat turn、workflow、task、tool_only 的关联模型。
2. 说明 `ExecutionRunRegistry` 是进程内单例，对多 worker 意味着什么。
3. 区分 durable `leagent.telemetry.trace` 与可选 OTLP 导出。
4. 在日志与 span 中用 `run_id` / `parent_run_id` 串起父子作用域。
5. 避免把 Trace、transcript、checkpoint 三类数据混为一谈。

## 核心心智模型：三条相关但不同的“历史”

```text
用户可见 transcript     → TieredSessionStore（聊天 SSOT）
可恢复执行快照         → CheckpointStore / WorkflowStateStore
评测与排障用轨迹       → agent_traces（run_id = trace_id）+ 可选 OTel
```

每次入口应铸造**恰好一个** `ExecutionRun`。子作用域（工作流步骤、子 Agent、后台任务）用 `parent_run_id` 挂到父 turn。WebSocket / SSE 只转发 `EventManager` 上的生命周期信号；Webhook 订阅同一事件总线。

关联身份建议：

| 字段 | 含义 | 不当作 |
|------|------|--------|
| `session_id` | 对话线程 | 单次执行 |
| `run_id` | 一次执行单元 / 默认 `trace_id` | 聊天主键 |
| `parent_run_id` | 子作用域父指针 | 用户身份 |
| `prompt_id` | 工作流/prompt 入口索引 | transcript id |
| `checkpoint_id` | 暂停恢复句柄 | 长期记忆键 |

## LeAgent 的真实实现

### ExecutionRun 与 Registry

`backend/leagent/runtime/execution_run.py` 定义 `ExecutionScope`（`chat_turn` / `workflow` / `task` / `tool_only`）、`ExecutionRun` 与统一 `PauseToken`。`backend/leagent/runtime/execution_registry.py` 的 `ExecutionRunRegistry` 在进程内保存 `run_id → ExecutionRun`，并维护 `prompt_id` 索引；可按 session 列出，或取最近活跃 chat turn。

```python
from leagent.runtime.execution_registry import get_execution_run_registry

reg = get_execution_run_registry()
active = reg.get_active_chat_turn(session_id)
```

**重要边界**：注册表是进程内单例。Gunicorn / uvicorn 多 worker 时，worker A 登记的暂停 run，worker B 可能看不见。默认部署应 `LEAGENT_WORKERS=1`；若必须多进程，需 sticky sessions，或未来的 durable run store。阻塞 run 会留在注册表直到 resume 或显式结束。

铸造位置集中在 `leagent.runtime.execution_factory`：聊天 SSE、SDK、后台任务、子 Agent、工作流 agent 节点都应走同一关联约定，而不是各自发明 id。

### 持久 Agent Trace

`backend/leagent/telemetry/trace/`（`recorder.py`、`store.py`、`models.py`、`context.py`）提供 best-effort、追加式运行轨迹：

- 热路径 **fire-and-forget**，尽量不 await 进入 agent loop；
- 可合并 create / span / counter 到一次 flush；
- 默认不记录完整 I/O 预览；`LEAGENT_TRACE_RECORD_PREVIEWS` 或 `capture_payloads` 才加重；
- span kind 覆盖 `agent`、`llm`、`tool`、`approval`、`compact`、`subagent`、`error`、`event` 等。

`TraceHook`（默认 Hook 之一）在压缩与子 Agent 边界补录。Trace 与 transcript/checkpoint 分离，便于评测导出而不污染用户可见历史。

### OpenTelemetry

`backend/leagent/telemetry/otel.py`：未配置 `OTEL_EXPORTER_OTLP_ENDPOINT`（或 `TelemetryConfig.otlp_endpoint`）时，setup 为 no-op；未安装 `opentelemetry-*` 时 `get_tracer()` 返回空实现，调用方无需条件导入。配置后走 OTLP gRPC BatchSpanProcessor，可选 metrics。`instrument_all()` 可对 FastAPI / SQLAlchemy / Redis 做自动埋点（依赖对应 instrumentation 包）。

OTel 适合接入公司统一 APM；仓库内 durable trace 更适合 Agent 特有的工具树、审批与成本归因。两者通过 `run_id` / `parent_run_id` 对齐，而不是互相替代。

## 验证命令

```bash
cd backend
uv run pytest tests/test_agent_trace.py -v
```

```bash
uv run pytest tests/eval/test_workflow_agent_trace.py -v
```

后者通过 `EngineTrace`（测试夹具，不是生产 TraceStore）断言工具序列与终态，说明“轨迹断言”可以离线做。

手工检查：完成一轮含工具与子 Agent 的任务，在日志中检索同一 `run_id`；确认子作用域日志带 `parent_run_id`。若开启 OTLP，在 Collector 中过滤 `service.name` 与该 `run_id` 属性。

## 常见误区

1. **用 `run_id` 当聊天主键**：下一轮会有新的 run。
2. **假设 Registry 跨 worker 共享**：当前是内存 dict。
3. **默认打开完整 prompt/工具参数预览**：体积、延迟与密钥泄露风险都上升。
4. **把 SSE 断线当成 Trace 丢失**：transcript 仍可能已落库；反过来 Trace 异步写入失败也不应回滚用户消息。
5. **把 MetricsHook 进程内字典当成可观测平台**：重启即丢，且无法跨实例聚合。

## 业内对照

OpenAI Agents SDK / Codex 类产品强调 append-only rollout 或 session transcript 供回放与评测；OpenTelemetry 则是跨语言通用信号。LeAgent 同时保留产品向 durable agent trace 与可选 OTLP：前者懂 tool/approval/subagent 语义，后者接入现有 SRE 栈。LangSmith、Phoenix、Langfuse 等偏“追踪即产品”；本仓库选择“追踪是一等公民遥测，但与聊天 SSOT 解耦”。

## 生产检查表与总结

- [ ] 每个入口只铸造一个 `ExecutionRun`，子作用域设置 `parent_run_id`
- [ ] SQLite 部署保持 `LEAGENT_WORKERS=1`；多 worker + PostgreSQL 时启用 sticky sessions
- [ ] Trace 默认不落敏感全文；预览开关有明确运维文档
- [ ] OTLP endpoint、采样率、环境名已配置或有意关闭
- [ ] 告警同时覆盖 HTTP 指标与 Agent 级错误/超时率
- [ ] 排障手册要求先拿 `session_id` 再拿 `run_id`，再下钻 span 树
- [ ] 暂停 run 的 resume 路径与同一 worker / sticky 策略一致

可观测性不是“多打几行 log”，而是给每次执行一个可关联、可导出、可与父子作用域对齐的身份。下一篇用这些轨迹做评测，而不是只比对最终字符串。

继续阅读：

- [46｜Agent 轨迹评测与回归测试](46-trajectory-evaluation.md)
- [执行拓扑](../../technical/execution-topology_zh.md)
- [Agent Trace 技术说明](../../technical/agent-trace_zh.md)
- 源码：[`backend/leagent/runtime/execution_registry.py`](../../../backend/leagent/runtime/execution_registry.py)、[`backend/leagent/telemetry/`](../../../backend/leagent/telemetry/)
