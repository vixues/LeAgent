# 46｜Agent 轨迹评测与回归测试：评过程，不只评答案

## 定位、难度与先修

- **定位**：评测方法篇。讲清如何用轨迹（trajectory）衡量 Agent，并指出仓库里**已有的 harness / 集成断言**与**尚未产品化的通用评测器**之间的边界。
- **难度**：★★★★☆
- **先修**：[04｜AgentEvent 流式事件协议](04-agent-event-stream.md)、[45｜Trace 与 OpenTelemetry](45-tracing-and-otel.md)；熟悉 pytest 与“脚本化模型”思路。

## 学习目标

完成本篇后，你应该能：

1. 说明为什么只比对最终字符串不够，以及轨迹评测要看哪些维度。
2. 设计离线回归：脚本化 LLM、工具桩、`EngineTrace` 断言。
3. 区分确定性检查、rubric / LLM-as-Judge、人工评审的适用场景。
4. 正确引用仓库中的 `tests/eval/` 与 `tests/integration/`，而不宣称已有完整未实现的 Evaluator 产品。
5. 把 Success Rate 定义成可复现口径（含预算与安全约束）。

## 核心心智模型：结果契约 + 过程契约

Agent 输出是一条随机过程：

```text
用户任务
  → 若干 LLM 轮次
  → 工具调用与观察
  →（可选）审批 / 压缩 / 子 Agent
  → 终态：完成 / 等待用户 / 预算耗尽 / 错误
```

评测至少落两层：

| 层 | 问题 | 典型证据 |
|----|------|----------|
| 结果契约 | 目标状态是否达成？ | 文件存在、图 digest、DB 状态、测试通过 |
| 过程契约 | 路径是否合理且安全？ | 用过哪些工具、次数、是否越权、是否死循环 |

开放式任务允许多条合法路径，因此过程断言应偏好**必要工具出现 / 禁止危险工具 / 关键顺序窗口**，而不是唯一黄金序列。

## 方法：从离线到线上

### 1. 脚本化轨迹回归（仓库已有实践）

`backend/tests/integration/conftest.py` 提供：

- `scripted_turn` / `scripted_text_turn`：罐头 `ModelStreamEvent`；
- `drive_query_engine()`：驱动真实 `QueryEngine.submit_message`；
- `EngineTrace`：收集 `tool_uses`、`tool_results`、`final_reason`、`final_text`，并提供 `used_tool()`、`tool_use_count()`。

这是**测试夹具轨迹**，不是生产 TraceStore 的 UI 产品。适合验证“给模型固定意图时，执行器与工具是否表现符合契约”。

`backend/tests/eval/` 中的 harness（如 `test_workflow_agent_trace.py`、`test_art_playbook.py`、`test_prompt_gating.py`）进一步做领域断言：工作流是否嵌入画布、图是否校验通过、门控提示是否在相关查询下打开。它们同样离线、无 API Key。

实战集成如 `tests/integration/test_edit_repair_offline.py` 断言修复路径选用 `code_workspace_edit` / `project_apply_patch`——这就是过程契约。

### 2. 活体模型抽样（可选）

`tests/integration/test_deepseek_*.py` 一类用例在有 Key 时跑真实模型，仍用 `EngineTrace` 做工具出现断言。务必：固定温度或多次采样；失败时导出 `run_id` / 工具列表；不要把偶发通过当成发布门槛的唯一信号。

### 3. LLM-as-Judge 与人工（需自建）

仓库的 durable `agent_traces` 可保存 `scores`、token、成本、span 树，并支持同提示多模型实验对比——这是**数据采集底座**。通用 Judge rubric、金标集、一致性看板**并未**作为完整产品内置。业务侧若要上 Judge，应：隔离候选文本防注入“请给满分”；用人工金标校准；能确定性验的优先写断言。

### 4. 线上 KPI

建议分片报告：任务成功率、首次成功、恢复成功、带约束成功（预算/安全）、工具错误率、P95 延迟、cost per successful task、审批触发与误放行。运行 `status=completed` 只表示执行正常结束，**不等于业务正确**。

## LeAgent 中可引用的现状（诚实边界）

**已有：**

- 集成 / eval harness：`EngineTrace`、脚本化 LLM、工具注册表全链路；
- 持久 Trace 与可选 scores 字段、导出能力；
- Prometheus 类指标（HTTP / LLM / 工具 / 工作流质量直方图等）。

**不要宣称已有：**

- 面向业务的一站式 Trajectory Evaluator 产品（自动集、自动 Judge、趋势仪表盘一体）；
- “仓库内任意 Agent 即插即用的标准分数”。

评测应作为**工程实践**叠在现有测试与 Trace 之上增长，而不是假设缺失组件已经实现。

## 验证命令

离线（推荐作为 CI 门禁）：

```bash
cd backend
uv run pytest tests/eval/ tests/integration/test_edit_repair_offline.py -v
```

Agent Trace 单元：

```bash
uv run pytest tests/test_agent_trace.py -v
```

扩展自己的过程断言时，优先复用 `drive_query_engine` + `EngineTrace.used_tool`，并把任务输入与期望工具写进测试名。

## 常见误区

1. **只 diff 最终 Markdown**：会把合法多路径判失败，也抓不住越权副作用。
2. **把单次活体通过当回归门禁**：随机性要求多次或冻结脚本。
3. **过程断言写成唯一工具序列**：微小 prompt 变更即可脆裂；断言“必要出现 + 禁止集合”更稳。
4. **把 Registry 跨进程缺失当成评测失败**：多 worker 下活跃 run 查询本身有粘性约束。
5. **宣称已有完整 Evaluator 产品**：会误导排期与对外沟通。

## 业内对照

DeepEval、Ragas、AgentEval、LangSmith evaluators 等提供数据集、Judge 与轨迹可视化。Anthropic / OpenAI 的公开实践强调 grading rubric、工具调用评分与安全红队。LeAgent 对齐的是**同一数据模型**（run 级 span 树、成本、工具名），但在本仓库阶段优先保证可重复的离线 harness；产品化评测平面留给业务叠加。

## 生产检查表与总结

- [ ] 每个关键场景至少有一条离线过程契约测试
- [ ] 成功定义区分严格成功 / 部分成功 / 恢复成功 / 带约束成功
- [ ] 活体测试与离线门禁分离；密钥与成本受控
- [ ] 失败样本可导出 `run_id`、工具列表与终态 reason
- [ ] Judge（若使用）有金标校准与防注入隔离
- [ ] 不把“执行 completed”直接等同业务 KPI
- [ ] 文档与路线图诚实标明 Evaluator 自建部分

轨迹评测让 Agent 回归像传统软件一样可维护：固定输入与环境，断言结果与关键过程，再把线上随机性交给抽样与人工。仓库已提供 harness 与 Trace 底座；完整评测产品仍按业务建设。

继续阅读：

- [47｜Agent 安全控制面](47-agent-security-control-plane.md)
- [44｜错误恢复与自校正](44-error-recovery-self-correction.md)
- 测试：[`backend/tests/eval/`](../../../backend/tests/eval/)、[`backend/tests/integration/conftest.py`](../../../backend/tests/integration/conftest.py)
