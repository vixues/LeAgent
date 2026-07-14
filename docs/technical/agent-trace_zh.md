# Agent 运行追踪（Running Trace）

面向 Agent 轮次的持久化**调试 / 评测**遥测。该平面与以下平面分离：

| 平面 | 用途 | 所有者 |
|------|------|--------|
| 聊天 transcript | 用户可见的 SSOT | `TieredSessionStore` |
| 恢复（Resume） | 暂停 / 继续 | `CheckpointStore` |
| **运行追踪** | 评测、模型对比、缺陷定位 | `leagent.telemetry.trace` |

灵感来自 Hermes（OTel / OpenInference span kinds）、Codex（`trace.jsonl` + 外联 payload）以及 Claude session transcripts（只追加事件）。

英文版：[agent-trace.md](./agent-trace.md)

## 捕获

- `begin_execution` / `end_execution*` 打开与关闭根 `agent` span（`trace_id` = `run_id`）。
- `run_loop` 从 `AgentEvent` 追加 tool / result / error spans（仅观察）。
- `TraceHook` 记录 compact / subagent 边界。
- `LLMService._record_request_log` 写入 `llm_request_logs.run_id` 以及一个 `llm` span。

## 设置

| 环境变量 | 默认值 | 含义 |
|----------|--------|------|
| `LEAGENT_TRACE__ENABLED` | `true` | 总开关 |
| `LEAGENT_TRACE__CAPTURE_PAYLOADS` | `false` | 将完整 I/O 写入 `LEAGENT_HOME/traces/` |
| `LEAGENT_TRACE__PREVIEW_CHARS` | `4096` | 截断预览长度 |
| `LEAGENT_TRACE__RETENTION_DAYS` | `30` | 计划保留天数（清理任务待定） |

## API

- `GET /api/v1/traces` — 列表 / 过滤
- `GET /api/v1/traces/{id}` — 摘要 + span 树
- `GET /api/v1/traces/{id}/export` — Codex 风格 JSONL
- `GET /api/v1/traces/stats/by-model` — 按模型聚合记分卡
- `POST /api/v1/traces/experiments` + `/run` — 同提示词多模型对比
- `GET /api/v1/chat/sessions/{id}/traces` — 会话范围列表

## UI

- 聊天执行面板：运行瀑布图 + JSONL 导出
- 管理后台 → **Agent Traces**：运行列表、按模型统计、对比实验
