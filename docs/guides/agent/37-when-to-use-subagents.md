# 37. 什么时候应该使用子 Agent

## 定位与先修

本文是子 Agent 系列的决策篇，适合已理解 think-act 循环、工具调用与 [05 状态所有权](05-state-ownership.md) 的读者。子 Agent 不是“多叫一个模型就会更聪明”，而是把一个边界清楚的子任务放进独立的 think-act 循环，并为它单独设置提示词、工具和预算。核心收益是上下文隔离与故障隔离；代价是额外推理、信息交接和结果验收。实现细节见 [38](38-delegation-context-isolation.md)、[39](39-scoped-tools-and-handoffs.md)。

## 目标

先用下面四个问题判断是否值得委派：

1. **任务能否写成独立交付物？** 例如“阅读这三个模块并返回调用链”比“继续帮我想想”更适合委派。
2. **是否需要不同能力或工具权限？** 数据分析、代码修改、资料检索可以分别绑定不同 Agent 定义和工具白名单。
3. **隔离是否能减少噪声或风险？** 子 Agent 使用 fresh transcript，不自动继承父 Agent 的逐轮对话；敏感写工具也可从子工具集移除。
4. **父 Agent 能否验证结果？** 如果结果没有验收条件，委派只会把不确定性藏进另一层模型调用。

适合的信号包括：子任务耗时较长、需要多次工具调用、可以并行调查、失败不应污染主推理、需要专门 persona。反过来，单次计算、一个工具就能完成的查询、强依赖父对话中大量隐含信息的任务，通常直接调用工具更便宜、更可靠。

## 读写数据流

父模型可调用 `AgentTool`（工具名 `agent`，别名 `subagent`、`delegate`），也可以由代码直接调用 `AgentRuntime.delegate(parent, agent, prompt, ...)`。实际链路是：

```text
AgentTool / workflow Agent 节点
  → AgentRuntime.delegate
  → _run_subagent_core
  → ToolRegistry.scoped
  → make_child_executor
  → QueryEngine.fork
  → sdk.kernel.run_loop
```

`delegate` 先解析 `AgentDefinition`，再合并定义中的 allow/deny、模型参数和 turn budget。`_run_subagent_core` 为子 Agent 创建过滤后的 registry，并创建只从该 registry 查找工具的 child executor；因此“模型看到的工具 schema”和“运行时真正能执行的工具”一致。父级取消默认通过 abort bridge 传播到子级。

最容易误读的是状态语义。`QueryEngine.fork()` 没有把父级 `mutable_messages` 放进子配置，所以子 Agent 从 **fresh transcript** 开始；父级必须把路径、约束、输入数据和验收标准写进 `prompt`。另一方面，`ContextManager.clone()` 会复制 `file_state`，因此子级启动时得到父级文件读取缓存的一个快照。它不是与父级实时共享的同一个对象。对于 `coding_agent`，子级结束时才执行 `parent.file_state.merge_from(child.file_state)`；这是 **clone + merge-back**，不是双向实时同步。工作目录中的真实文件可能被工具直接修改，但文件状态缓存仍遵循上述快照语义。

## 示例：委派一次代码调查

下面是服务层代码可采用的形状，重点是交接包，而不是 API 语法本身：

```python
result = await runtime.delegate(
    parent_engine,
    "subagent",
    (
        "只读调查 backend/leagent/workflow。"
        "说明 Agent 节点的执行入口、输出槽顺序和暂停条件；"
        "给出文件路径与测试证据，不修改文件。"
    ),
    allowed_tools=["project_read", "project_grep", "project_glob"],
    max_turns=6,
)
if not result["success"]:
    raise RuntimeError(result.get("error") or "delegation incomplete")
```

良好的交接提示至少包含：目标、输入位置、允许/禁止动作、输出格式、完成条件。父 Agent 收到的扁平结果可包含 `text`、`success`、`steps_count`、`partial`、`error`、`activity`、`changed_files`、`produced_files`、`images`、`verification_gap` 和可选 `checkpoint_id`，不要只读 `text` 就宣布成功。

## 如何验证

仓库中的 `tests/test_subagent.py` 验证了 allow/deny、turn budget、流式文本聚合、非 completed 结果、工具步数与父取消传播；`tests/test_subagent_scoped_executor.py` 验证 child executor 确实绑定 child registry。设计自己的验收时，至少检查：

- `success is True` 且 `partial is False`；
- 工具活动与任务范围一致，没有越权工具；
- 修改任务检查 `changed_files`，产物任务检查 `produced_files`；
- coding Agent 没有 `verification_gap`，并由父级复核关键测试。

## 常见误区

- **“子 Agent 会自动知道前文。”** 不会；fresh transcript 要求显式交接。
- **“文件状态始终共享。”** 不会；是启动时 clone，coding 变体结束后 merge-back。
- **“allowed_tools 只是给模型看的提示。”** 不是；child executor 也绑定过滤后的 registry。
- **“拆得越细越好。”** 过细会让交接和验收成本超过收益。
- **“success 就等于业务正确。”** 它主要表示运行完成；业务事实仍需测试、断言或人工复核。

## 与常见框架对照

- **OpenAI Agents SDK handoff** 更像把对话控制权交给另一个 Agent；默认接收方可看到既有历史，也可用 `input_filter` 或 nested handoff history 改写。LeAgent 的子 Agent 默认是 fresh transcript，更接近显式任务包委派。
- **LangGraph supervisor** 通常用图状态和路由节点决定下一位 worker。LeAgent 可以用父 Agent、条件节点和 Agent 节点组合出该模式，但当前实现不应被描述为存在独立的 `Supervisor` 类。
- **AutoGen teams** 的 `RoundRobinGroupChat` 或 `SelectorGroupChat` 维护团队会话并广播消息，强调“谁下一位发言”。LeAgent delegation 更强调一个父级调用一个隔离子运行，并拿回结构化 envelope。

## 总结

当子任务可独立描述、需要隔离工具或上下文、而且父级有明确验收手段时使用子 Agent。若只是为了“多一个模型意见”，却没有交接契约和验证标准，单 Agent 加直接工具调用通常更合适、也更省预算。下一篇用代码钉死 fresh transcript 与 FileState 语义：[38](38-delegation-context-isolation.md)。
