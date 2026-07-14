# 44｜错误恢复与自校正：失败如何重新进入 Think–Act 循环

## 定位、难度与先修

- **定位**：生产可靠性篇。解释工具瞬时失败、校验失败与产物质量失败如何被消化成下一轮观察，而不是静默丢弃。
- **难度**：★★★☆☆
- **先修**：[02｜Think–Act Loop](02-think-act-loop.md)、[43｜Hooks 与 Guardrails](43-hooks-and-guardrails.md)；了解 `ToolResult` 会序列化回消息列表。

## 学习目标

完成本篇后，你应该能：

1. 区分瞬时重试（ErrorRecovery）与语义自校正（把失败交给模型）。
2. 说明 `ResultProcessor` 如何把异构工具输出压成 LLM 可读字符串。
3. 解释 `ArtifactErrorTracker` 如何把 dirty 产物写成下一轮系统提示指令。
4. 判断何时该重试执行器、何时该返回错误让模型改参数、何时该提示重置工作区。
5. 用离线测试验证恢复策略与再生 directive，而不依赖真实模型。

## 核心心智模型：三层恢复栈

Agent 面对的“失败”并不都一样：

```text
工具执行瞬间失败（超时、429）
  → ErrorRecovery：执行器侧有界重试
  → 仍失败：序列化为 tool 结果 → 模型在下一轮观察并改计划

产物语义失败（编译错、质量门未过、UI JSON 非法）
  → ArtifactErrorTracker：标记 dirty
  → ContextManager：注入 regeneration directive
  → 模型在同一或下一 turn 修补 / 重跑

不可恢复（校验错误、not found、越权）
  → 不盲目重试
  → 明确错误回到 transcript，由模型或用户处理
```

关键不变量：**恢复不得掩盖安全拒绝**；**重试必须有上限**；**自校正必须把失败变成可见观察**，否则模型会在脏状态上继续打补丁。

好的恢复不是吞掉异常，而是：

```text
失败 → 结构化错误（含如何修）→ 回填消息 → 模型再决策（edit / 换工具 / 问人 / 结束）
```

预算（`max_turns`、token）防止无限自救；审批暂停（`awaiting_user_input`）是控制流，不是错误。

## LeAgent 的真实实现

### 1. `ResultProcessor`：统一工具观察形状

`backend/leagent/agent/recovery.py` 中的 `ResultProcessor` 负责：

- `normalize()`：把任意返回值压成统一 dict；
- `serialize_for_llm()`：生成 query 循环真正追加到消息里的字符串（失败时带 `tool_ok: false` 与 detail）；
- `extract_files()`：从常见键与 `produced_files` 中抽出产物路径，供遥测使用；
- 对超长输出施加约 96KB 截断提示，引导模型缩小查询。

它与 `query._serialize_result` 共用算法，保证 QueryEngine 路径与遗留路径对模型“说同样的话”。

### 2. `ErrorRecovery`：执行器侧有界重试

`ErrorRecovery` 可挂到 `query._dispatch_tools`：

| 失败类型 | 行为 |
|----------|------|
| `ToolTimeoutError` / timeout 文案 | **重跑一次**，超时加倍；`coding_agent` / `script_agent` **跳过**（自管内部恢复） |
| Rate limit / 429 | 最多 3 次，延迟约 1s / 2s / 5s + jitter |
| `ToolValidationError` | **不重试**，交给模型看错误 |
| 错误含 `not found` | **不重试** |
| 自定义 handler | 按错误子串匹配（遗留扩展点） |

`as_middleware()` 先 `executor.run_tool`，失败再 `attempt_recovery`；恢复成功则返回新结果，否则保留原失败信封。瞬时抖动在执行器层消化，语义失败仍回流给模型。

### 3. `ArtifactErrorTracker`：产物脏状态与再生指令

`backend/leagent/context/artifact_error_tracker.py` 按 session 跟踪 dirty artifact。`QueryEngine` 在工具结果回流时调用 `_track_artifact_error`。覆盖类型包括 GenUI、canvas、code、workflow、spreadsheet、document，以及显式 `quality_passed=False` 的可下载产物。

特别约定：`workflow_run` 即使 `success=True`，若 `quality_passed is False` 或分数低于阈值，仍记 dirty——这样 Agent 可在**同一 turn** 内关闭 save → run → evaluate → re-run 环。

`get_regeneration_directives()` 生成高优先级指令注入系统提示，例如：

- GenUI JSON 非法 → 要求重发完整 `emit_ui_tree`，禁止对坏树打 patch；
- code 语法/运行错误 → 优先 `code_workspace_edit` + `workspace_file` 最小修补；连续失败 ≥ 3 次 → 建议 `reset_workspace: true`；
- workflow 质量不足 → 检查 `workflow_status`，改图后 `workflow_save` 再 `workflow_run`。

这是**提示层自校正**，不是执行器自动改图；模型仍可能忽略，因此质量门要返回 `success=False` 或显式 `quality_passed=False`，把压力放在可观察结果上。

### 4. 相关机制地图

| 机制 | 位置 | 作用 |
|------|------|------|
| 查询恢复 / 序列化 | `agent/query.py`、`agent/recovery.py` | 有界重试、工具结果归一化 |
| 产物错误跟踪 | `context/artifact_error_tracker.py` | dirty → regeneration directive |
| 工具参数 / blob 修复 | `tests/test_tool_argument_blob_recovery.py` 对应路径 | 畸形或过大参数 |
| 审批门 | `tools/approval.py` | 高风险 → pause，非“错误” |
| 工作流质量环 | Art QualityCritic / IterativeRefine | 图内引擎侧自校正 |

Integration harness：`backend/tests/integration/conftest.py` 的 `scripted_turn` 可编排「坏代码 → workspace_edit → 再执行」而无真实 LLM。

## 验证命令

```bash
cd backend
uv run pytest tests/test_artifact_error_tracker.py -v
```

重点：代码失败 directive 偏好 workspace edit；重复失败会升格为重置工作区。

```bash
uv run pytest tests/eval/test_workflow_agent_trace.py tests/integration/test_edit_repair_offline.py -v
```

前者用脚本化 LLM 驱动真实 `QueryEngine`，断言工作流闭环；后者用 `EngineTrace.used_tool(...)` 断言修复路径选择了 `code_workspace_edit` / `project_apply_patch` 等工具。审批流可另跑 `tests/test_approval_flow.py`。带 API Key 的活体修复见 `tests/integration/test_deepseek_code_repair.py`（按项目 live 标记运行）。

## 常见误区

1. **对所有失败无限重试**：校验错误、权限拒绝和 not found 越重试越浪费；还可能放大副作用。
2. **把 Recovery 放进 Hook**：Hook 异常被吞；重试应在执行器路径。
3. **只修最终文本、不管脏产物**：GenUI/canvas/code 在 dirty 时继续 patch 会放大破损。
4. **以为 directive 保证修复**：它是高优先级提示，仍需质量门与测试断言兜底。
5. **超时后盲目重启子 Agent**：仓库刻意跳过 `coding_agent` / `script_agent` 的外层超时重跑，避免双重执行。
6. **把恢复成功当成任务正确**：仍需轨迹评测与用户确认；`awaiting_user_input` 是控制流，不是失败。
7. **用无限提高 `max_turns` 当恢复策略**：成本与死循环风险一并上升。

## 业内对照

OpenAI / Anthropic 的 tool result 协议本身只提供“把失败返回给模型”的通道；应用仍需决定哪些错误可自动重试。LangGraph 常用条件边或显式 retry 节点表达恢复；LeAgent 则把瞬时重试收在 `ErrorRecovery`，把语义自校正收在 tracker + 下一轮上下文。游戏艺术管线的 `Art.QualityCritic` → `QualityGateNode` → `IterativeRefineNode` 是引擎侧闭环，与 Agent 侧 `ArtifactErrorTracker` 互补：前者改图执行态，后者改下一轮 prompt。Anthropic 长任务实践强调增量提交与 progress 文件；Agents SDK 的 guardrail tripwire 则更接近“阻止”而非“重试”。

## 生产检查表与总结

- [ ] 区分瞬时 / 校验 / 语义 / 安全四类失败，并有不同策略
- [ ] 超时与限流重试有上限，且计入延迟与成本指标
- [ ] 子 Agent 类工具不在外层盲目重启
- [ ] 产物失败会写入 tracker，并在下一轮可见 directive
- [ ] 质量门失败对 Agent 呈现为可观察的非成功信号
- [ ] 敏感错误信息不向 transcript 泄露密钥
- [ ] 有针对 directive 文案与工具选择的离线测试
- [ ] 审批暂停与真正错误在监控上分栏，避免误告警

错误恢复让瞬时抖动不中断任务；自校正让语义失败重新进入目标—动作—观察循环。没有观察回流的“自动重试”只是更吵的失败；自校正的上界由观察质量与预算共同决定。

继续阅读：

- [45｜Trace、ExecutionRun 与 OpenTelemetry](45-tracing-and-otel.md)
- [46｜Agent 轨迹评测与回归测试](46-trajectory-evaluation.md)
- [23｜文件产物与沙箱](23-files-artifacts-and-sandbox.md)
- 源码：[`backend/leagent/agent/recovery.py`](../../../backend/leagent/agent/recovery.py)、[`backend/leagent/context/artifact_error_tracker.py`](../../../backend/leagent/context/artifact_error_tracker.py)
- 测试：[`backend/tests/test_artifact_error_tracker.py`](../../../backend/tests/test_artifact_error_tracker.py)
