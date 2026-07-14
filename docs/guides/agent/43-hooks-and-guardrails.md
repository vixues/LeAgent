# 43｜Hooks 与 Guardrails：把可观测扩展和强制控制分开

## 定位、难度与先修

- **定位**：生产可靠性系列入口。讲清生命周期扩展点与强制策略执行点的边界，避免把“看见违规”误当成“拦住违规”。
- **难度**：★★★☆☆
- **先修**：已读 [02｜Think–Act Loop](02-think-act-loop.md) 与 [21｜ToolRegistry 与 ToolExecutor](21-tool-registry-and-executor.md)；了解一次 turn 会经过 `run_loop → QueryEngine → query → ToolExecutor`。

## 学习目标

完成本篇后，你应该能：

1. 区分生命周期 Hook、运行事件、权限策略和审批暂停。
2. 知道默认 Hook 在何处装配、按什么顺序运行、失败后如何处理。
3. 为日志、指标、Trace、记忆形成等旁路功能选择正确扩展点。
4. 避免把会被吞掉异常的 Hook 误当成安全拦截器。
5. 用测试证明 Hook 被调用，同时用独立测试证明危险工具被真正拒绝或暂停。

## 核心心智模型：观察者 vs 执行点

可以把一次 Agent 回合画成四层：

```text
用户输入
  → Kernel / QueryEngine 生命周期
  → Hook：观察 start、step、tool、complete、error、compact、subagent
  → ToolExecutor：权限与审批判定
  → Tool 本体 / sandbox：执行与资源边界
```

Hook 解决“发生了什么、我要附加什么旁路行为”；Guardrail 解决“这件事是否允许发生”。可靠控制通常遵循纵深防御：

| 层级 | 作用 | 失败时应 |
|------|------|----------|
| 提示词软约束 | 引导模型偏好 | 仍可能被模型违背 |
| 工具 Schema | 缩小输入空间 | 校验失败则不执行 |
| 权限 / Approval | 主体与动作判定 | 拒绝或 `awaiting_user_input` |
| 循环预算 | `max_turns`、工具次数、token | 直接终止 turn |
| Sandbox / 超时 | 限制最坏影响 | 返回失败给模型观察 |
| Hook / Trace | 审计与旁路 | 异常隔离，主链路继续 |

**Hook 默认是观察者；权限检查、审批、超时、调用上限和沙箱才是强制边界。**

## LeAgent 的真实实现

对应源码：`backend/leagent/agent/hooks.py`、`backend/leagent/sdk/kernel/loop.py`、`backend/leagent/agent/query.py`、`backend/leagent/tools/base.py`、`backend/leagent/tools/executor.py`。

`AgentHook` 提供 `on_start`、`on_step`、`on_tool_call`、`on_tool_result`、`on_plan_created`、`on_complete`、`on_error`、`on_cancel`，以及 `on_code_artifact`、`on_pre_compact`、`on_subagent_start/stop`。`HookManager` 按 `priority` 从小到大排序并逐个 `await`，还支持 `filter_by_names()`，让 Agent 定义选择进程级 Hook 集合的子集。

关键契约：`HookManager._dispatch()` 捕获所有异常，只写 `hook_error` 日志，**不中止主流程**。这是正确的可观测性策略——日志或指标故障不应拖垮用户请求——但也意味着 Hook 不是天然的 fail-closed 安全边界。仓库虽定义了会抛出 `RateLimitError` 的 `RateLimitHook`，默认 `create_default_hooks()` 实际只装配 `LoggingHook`、`MetricsHook`、`TraceHook`，可选装配 `TaskHistoryHook`；即便手工注册 `RateLimitHook`，其异常也会被管理器捕获。因此不能宣称当前 Hook 层已经强制执行限流。

默认 Hook 职责清晰：

- `LoggingHook`：记录任务、步骤、工具与完成状态。
- `MetricsHook`：进程内累计时长、步骤类型和工具成功率。
- `TraceHook`：补录压缩与子 Agent 边界。
- `TaskHistoryHook`：完成时调用记忆形成策略。

真正的工具控制在权限检查与执行器路径。`query.py` 在派发前调用 `approval_requirement()`；需要确认时返回 `AWAITING_USER_INPUT`，由 Kernel 保存 checkpoint；用户允许后产生一次性或会话级 grant，再由模型重新发起调用。`max_turns`、`max_tool_calls_per_turn`、总 Token 预算、abort 状态都在主循环中直接判断，不依赖 Hook。

规则可以写成一句：**必须阻止执行 → Kernel / ToolExecutor / 权限 / 沙箱；失败时应继续服务 → Hook。** 若未来需要“可拦截 Hook”，应单独设计 blocking middleware，明确超时、错误传播、默认拒绝和审计语义，而不是悄悄改变现有观察型 Hook 的契约。

## 验证命令

```bash
cd backend
uv run pytest tests/test_agent_hooks.py -v
```

至少覆盖：低 `priority` 先执行；单个 Hook 抛错后后续 Hook 仍执行；`filter_by_names()` 不修改共享管理器；默认列表包含日志、指标和 Trace。

```bash
uv run pytest tests/test_approval_flow.py tests/test_kernel_checkpoint.py -v
```

手工对比实验：

1. 定义只把事件追加到列表的 Hook，跑一轮含工具调用的脚本化 Agent，预期顺序含 start → tool_call → tool_result → complete。
2. 让 Hook 在 `on_tool_call` 抛异常：工具仍可能执行——证明它是观察者。
3. 把同一工具标为需要审批：工具本体不执行，回合以 `awaiting_user_input` 结束。

生产验证还应检查日志中的 `hook_error` 并单独告警；否则旁路观测悄悄失效、主业务仍成功，会形成监控盲区。

## 常见误区

1. **`on_tool_call` 等于执行前拦截器**：它只是执行前通知，异常被隔离。
2. **提示词里的“不要删除文件”等于权限系统**：提示词可被模型误解或注入覆盖。
3. **把所有逻辑塞进 Hook**：制造顺序依赖和共享可变状态。
4. **在 Hook 中做高延迟网络请求**：当前派发逐个 `await`，会直接拉高用户可见延迟。
5. **把 `MetricsHook` 进程内字典当成持久指标**：重启丢失，也不适合跨 worker 聚合。
6. **忽略 `on_complete` / `on_error` 的清理**：可能造成内存或句柄残留。

## 业内对照

LangChain callbacks、OpenAI Agents tracing processors、Claude Code hooks 和多数 APM instrumentation 更接近观察型 Hook。真正的安全控制更接近 policy enforcement point：工具网关、API 授权、审批工作流或执行沙箱。LeAgent 当前分层与这一实践一致：Hook 负责生命周期扩展，Query/Executor 负责审批与执行约束。与某些框架允许 callback 返回“取消执行”相比，LeAgent 契约更简单，但开发者必须主动避免把 Hook 命名成“安全策略”后给出错误保证。

## 生产检查表与总结

- [ ] 默认 Hook 列表、优先级和职责已文档化
- [ ] Hook 异常有日志、指标和告警，但不破坏主链路
- [ ] 强制规则位于 Kernel、权限层、审批或 Sandbox，而非观察型 Hook
- [ ] 危险工具默认拒绝或暂停，并有 allow once / allow session / deny 测试
- [ ] 配置了最大回合、单回合工具数、总 Token 与执行超时
- [ ] Hook 不记录密钥、完整提示词或敏感工具参数
- [ ] 高延迟旁路采用缓冲、批量或异步投递
- [ ] 多进程部署不依赖 Hook 进程内状态做全局限流
- [ ] 既有“Hook 被触发”的测试，也有“危险动作未执行”的测试
- [ ] 审批、权限拒绝和 Hook 故障都进入可检索审计链路

Hook 让系统可扩展；Guardrail 让系统可控。下一篇讨论错误在工具与产物层如何被回收为下一轮的决策输入：[44｜错误恢复与自校正](44-error-recovery-self-correction.md)。

继续阅读：

- [21｜ToolRegistry 与 ToolExecutor](21-tool-registry-and-executor.md)
- [30｜Checkpoint、暂停与恢复](30-checkpoint-pause-resume.md)
- [47｜Agent 安全控制面](47-agent-security-control-plane.md)
- 源码：[`backend/leagent/agent/hooks.py`](../../../backend/leagent/agent/hooks.py)
- 测试：[`backend/tests/test_agent_hooks.py`](../../../backend/tests/test_agent_hooks.py)
