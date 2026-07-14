# 22. 工具并发与速率限制

## 定位与先修

同一轮模型回复里经常带多个 `tool_calls`。是否并行、并行多少、是否被用户级限流挡住，直接决定延迟与副作用安全。先修：[20](20-build-a-base-tool.md)、[21](21-tool-registry-and-executor.md)。请阅读 `BaseTool.is_concurrency_safe`、`ToolExecutor.partition_calls` / `execute_partitioned`、`backend/leagent/tools/rate_limit.py`，以及 `pipeline.py` 里的限流中间件。本文关心的不是“怎么让 gather 更快”，而是**何时并行是正确的**。

## 学习目标

理解 fail-closed 的并发默认值；读懂“安全工具并行、其余串行”的分区策略；会配置 `LEAGENT_TOOL_RATE_LIMIT_PER_MINUTE`；能区分信号量、并发安全标志、用户滑动窗口分别保护什么；并知道审批流不应与盲目并行混用。

## 心智模型：安全分类 × 全局闸门 × 每用户窗口

把一次工具批处理想成三道问题：

1. **语义上能不能一起跑？** —— `is_concurrency_safe`
2. **进程同时允许几个在飞？** —— `asyncio.Semaphore(max_parallel)`
3. **这个用户是不是在刷工具？** —— 可选滑动窗口限流

```text
一批 tool_calls
  ├─ is_concurrency_safe=True → execute_parallel（仍受 max_parallel 约束）
  └─ False / 未知工具          → 逐个 execute_call

每次真正执行前（默认 pipeline）
  ├─ PermissionMiddleware
  ├─ RateLimitMiddleware（环境变量开启时）
  └─ 遥测 / 断路器等
```

默认 `is_concurrency_safe=False`。只有你能证明：无共享可变状态、无可叠加写冲突、无“同一资源的隐藏队列”时，才打开并行。只读检索类工具常常合适；改文件树、改 todos、发信、可变 SQL、同一会话写缓存的工具通常不合适。

## 真实实现

`ToolExecutor.partition_calls` 查询注册表上的标志，缺失工具进入串行组。`execute_partitioned` 先跑并行组，再串行剩余项，从而在“能快则快”和“危险则慢”之间折中。`max_parallel` 默认 10，防止一次模型幻想出几十个调用拖垮进程。

`SlidingWindowRateLimiter` 用单调时钟维护每个 key 的命中时间戳；`tool_rate_limit_from_env()` 读取 `LEAGENT_TOOL_RATE_LIMIT_PER_MINUTE`，未设置或非正整数则关闭。键通常按用户维度构造（实现细节以 executor/pipeline 为准）。拒绝时返回失败信封，提示稍后重试，而不是静默丢弃。

需要人工确认的调用应由 query 循环先暂停整轮（见审批与 [30](30-checkpoint-pause-resume.md)），切忌在并行批次里一半写库一半弹窗，造成半提交。

部分 integration 工具内部还有面向下游 API 的局部 `rate_limit` 参数，那是对第三方的礼貌限速，与全局用户限流叠加，而不是互相替代。

## 示例：判断与配置

```python
# 无状态只读查询
is_concurrency_safe = True

# 修改同一 session 的文件树或 todos
is_concurrency_safe = False
```

```bash
# 每用户每分钟最多 120 次工具执行（进程内计数，非分布式集群配额）
export LEAGENT_TOOL_RATE_LIMIT_PER_MINUTE=120
```

自检分区逻辑可用假调用列表调用 `partition_calls`，确认写工具落入 serial 列表。压力场景下观察并行组是否受信号量钳制，而不是无限创建 task。

## 验证命令

```bash
cd backend
uv run pytest tests/test_executor.py -q
uv run python -c "from leagent.tools.rate_limit import tool_rate_limit_from_env; print(tool_rate_limit_from_env())"
```

建议补单测：同一假工具标记为安全时并行路径被调度；标记为不安全时完成顺序与提交顺序一致；开启限流后超额调用返回明确错误。

## 常见误区

1. **“只读就一定能并行。”** 共享非线程安全缓存、写同一日志文件或更新全局单例时仍可能不安全。
2. **把限流当安全边界。** 限流防过载与滥用；路径逃逸、越权读取必须靠沙箱与 permission。
3. **以为环境变量是集群全局配额。** 当前实现是进程内存窗口，多 worker 各自计数。
4. **强制全工具 True 降延迟。** 可能造成交错写、重复下单或会话状态撕裂。
5. **审批中的工具仍被并行调度。** 应先 pause，再在授权后继续。
6. **忽略工具自己的下游限速。** 全局放行不等于第三方不返回 429。

## 业内对照

Claude / Cursor 类产品对 shell、文件类工具偏串行或强审批；纯检索可以并行。OpenAI 并行 function calling 把调度交给宿主应用。某些 Agent 框架默认 `asyncio.gather` 全部工具，延迟好看但事故率更高。LeAgent 用显式布尔加执行器分区，把策略从“框架魔法”变成可代码审查的属性。

## 调参建议

并行与限流不要一上来拉满。新工具默认保持串行，先用真实负载观察是否存在写冲突或重复外部副作用；确认安全后再打开 `is_concurrency_safe`。`max_parallel` 应结合机器与下游配额：本地桌面可以略高，多租户服务端宜保守。用户级 `LEAGENT_TOOL_RATE_LIMIT_PER_MINUTE` 适合防止失控循环刷工具，但不能替代对单个危险工具的审批。若某类工具对第三方 API 敏感，优先在工具内部做礼貌限速，再叠加全局窗口。审批类工具出现在同一批调用里时，产品应整批暂停，而不是并行执行“看起来无害”的只读调用却把写操作悄悄做完。把这些规则写进代码评审清单，比依赖临场判断可靠。

## 总结

并发标志描述工具语义，信号量描述进程容量，滑动窗口描述用户配额。默认 fail-closed，只在有证据时打开并行；限流按需开启，且永远不是唯一安全层。正确的慢，往往比错误的快更接近生产可用的 Agent。
