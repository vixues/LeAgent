# 48｜成本、延迟、扩展：从单机 SQLite 到可运维生产

## 定位、难度与先修

- **定位**：生产系列收官。把预算、延迟、扩展拓扑与此前讲过的 Trace、安全、恢复收成一张可执行检查表。
- **难度**：★★★★☆
- **先修**：已读 43–47；了解默认端口与 `LEAGENT_HOME`；浏览 `deploy/.env.example`。

## 学习目标

完成本篇后，你应该能：

1. 指出默认单机拓扑的正确性条件：`SQLite` + `LEAGENT_WORKERS=1`。
2. 解释为何 `ExecutionRunRegistry` 与进程内事件总线强制 sticky sessions。
3. 从 turn / token / 工具 / 模型四层控制成本与尾延迟。
4. 设计扩容阶梯：垂直 → PostgreSQL → sticky 多 worker →（未来）durable run store。
5. 用生产检查表做上线前走查，而不假设仓库已具备无限水平扩展。

## 核心心智模型：预算闭环

```text
请求进入
  → 并发配额（每用户 / 全局）
  → Agent 循环预算（max_turns、每 turn 工具数、token）
  → 模型与工具产生延迟 / 费用
  → Trace / metrics 回流
  → 告警与降级（换模型、减工具、拒新任务）
```

没有预算的 Agent 会在错误恢复与自我纠错环里**花更多钱做错事**。延迟优化若只砍工具次数却不测成功率，会造成虚假“变快”。

扩展不是“把 workers 调大”：SQLite 单写者、进程内 Registry、进程内 EventManager 共同决定了当前安全扩展边界。

## LeAgent 的真实实现

### 默认拓扑

| 组件 | 默认 | 含义 |
|------|------|------|
| 数据库 | SQLite WAL @ `LEAGENT_HOME` | 零配置；单写者 |
| `LEAGENT_WORKERS` | `1` | 与 SQLite / Registry 匹配 |
| 后端端口 | 开发 `:7860`；镜像常 `:8000` | 见 deploy 与 start 脚本 |
| 向量记忆 | 无 Milvus 可跑 | 回退 lexical；写向量 no-op |

`AgentSettings`（`LEAGENT_AGENT__*` / 嵌套配置）提供 `max_turns`、`max_tool_calls_per_turn`，以及 long/extended profile 的更大预算与更长工具超时。运行时另受 tool timeout、sandbox 并发、`max_concurrent_per_user` 约束。

### 进程内状态与 sticky

`ExecutionRunRegistry`（`backend/leagent/runtime/execution_registry.py`）保存活跃 `ExecutionRun`、暂停 token、按 `prompt_id` / session 的查询。多 worker 时：

- worker A 上的 pause/resume、审批热状态、output stream 关联，worker B 不可见；
- 同理，进程内事件总线订阅者也不能跨进程扇出。

因此：**SQLite → 保持 workers=1**；**PostgreSQL 多 worker → 负载均衡启用 sticky sessions（会话亲和）**；长期方案才是 durable run store（仓库尚未将其标为已完成能力）。

会话 transcript 写路径也有进程内锁（见 TieredSessionStore 相关教程）：多 worker 同时写同一 session 仍可能最后写入者覆盖——又一个 sticky 理由。

### 成本与延迟杠杆

| 杠杆 | 位置 | 注意 |
|------|------|------|
| 模型分层 | tier1/tier2、Provider 配置 | 简单 turn 走快模型 |
| 上下文预算 / 压缩 | context manager、compaction | 降输入 token，但压缩本身耗时 |
| Prompt cache / fingerprint | 上下文卫生篇 | 避免无谓 cache miss |
| 工具并发与超时 | ToolExecutor | 防尾延迟爆炸 |
| 产物自校正上限 | ArtifactErrorTracker 升格重置 | 避免无限 regenerate |
| Trace 预览关闭 | `record_previews=false` | 热路径 I/O |
| Hook 轻量 | 见 43 | Hook 同步 await 计入延迟 |

成本指标优先看 **cost per successful task**，而不是裸 token；结合 46 的成功率定义，避免“更便宜但几乎完不成任务”。

### 扩容阶梯（诚实）

1. **单机垂直**：更多 CPU/RAM；保持 `workers=1` + SQLite。
2. **PostgreSQL**：并发写；仍建议先单 worker 验证。
3. **多 worker + sticky**：HTTP sticky 到会话；监控跨实例不一致。
4. **外部对象存储 / 备份**：`LEAGENT_HOME` 树与 DB 一起备份。
5. **未来**：durable ExecutionRun、跨进程事件总线——**尚未宣称本仓库已交付**。

向量层：Milvus 可增强 recall，不自动解决执行拓扑扩展。

## 验证命令

配置与安全基线：

```bash
cd backend
uv run pytest tests/test_security_control_plane.py -v
```

运行时与 SDK 基线：

```bash
uv run pytest tests/test_runtime_sdk.py tests/test_agent_trace.py -v
```

部署前人工核对 `deploy/.env.example`：`LEAGENT_WORKERS`、`LEAGENT_SECRET_KEY`、`DATABASE_URL`、OTel endpoint、安全相关变量。启动后确认日志无 “SQLite + workers>1” 类警告。

压测建议：分场景测 P50/P95（纯问答 / 多工具 / 审批暂停恢复），并观察单成功任务成本；不要只报吞吐。

## 常见误区

1. **SQLite 上开 4 个 workers 当扩容**。
2. **多 worker 无 sticky 就上审批与 resume**。
3. **为省 token 关掉所有工具，再怪模型“不会做事”**。
4. **打开完整 Trace payload 却抱怨延迟**。
5. **把演示笔记本的 `debug=true`、宽松 CORS 带进生产**。
6. **假设 EventManager / Registry 已是分布式组件**。

## 业内对照

托管 Agent 平台通常把队列、run state、文件与计费拆到托管服务；自建栈则必须自己处理亲和与持久化。K8s 水平扩展前提是**无本地共享可变状态**——当前 LeAgent 单机默认刻意违反这一条以换零配置。这与许多“先单进程做对，再拆服务”的路径一致；问题在于文档是否诚实写出边界。本篇选择诚实：默认正确形态是单 worker；多实例是有前提的演进，不是开关。

## 生产检查表与总结

### 安全与暴露面

- [ ] 强 `LEAGENT_SECRET_KEY`；生产 enforce auth；CORS/Host 收窄
- [ ] 文档与 metrics 已门禁；反向代理 TLS

### 数据与进程模型

- [ ] SQLite → `LEAGENT_WORKERS=1`
- [ ] 多 worker 仅在 PostgreSQL + sticky sessions 下启用
- [ ] 备份包含 DB + `LEAGENT_HOME` 关键目录
- [ ] 暂停/恢复路径在亲和策略下验证通过

### 预算与性能

- [ ] `max_turns` / 工具次数 / 超时 / 每用户并发有明确值
- [ ] 模型分层与缓存策略已配置
- [ ] Trace 默认不抓敏感全文；OTel 采样合理
- [ ] 以成功任务归一化成本与 P95；有错误率护栏

### 可靠性与评测

- [ ] Hook 故障告警；强制规则不在观察型 Hook
- [ ] 关键路径有离线轨迹回归（eval/integration）
- [ ] 质量门与 ArtifactErrorTracker 防止无限自校正烧钱
- [ ] run_id 可贯穿日志、Trace、工单

---

默认把 LeAgent 当成**单进程、可恢复、可观测的桌面/局域网 Agent 运行时**是正确的。成本靠预算与模型分层降，延迟靠工具与上下文治理降，扩展靠先换存储再谈多 worker，而不是先把 `LEAGENT_WORKERS` 调大。进程内 `ExecutionRunRegistry` 是今天必须记住的架构事实：忘记它，暂停恢复与审批会在负载均衡后随机失败。

系列回顾：

- [43｜Hooks 与 Guardrails](43-hooks-and-guardrails.md)
- [44｜错误恢复与自校正](44-error-recovery-self-correction.md)
- [45｜Trace 与 OpenTelemetry](45-tracing-and-otel.md)
- [46｜轨迹评测](46-trajectory-evaluation.md)
- [47｜安全控制面](47-agent-security-control-plane.md)
- [执行拓扑](../../technical/execution-topology_zh.md)
- 配置样例：[`deploy/.env.example`](../../../deploy/.env.example)
