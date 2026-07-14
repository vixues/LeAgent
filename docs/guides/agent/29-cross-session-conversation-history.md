# 29｜跨会话对话历史：conversation_history 工具

## 定位、难度与先修

- **定位**：在授权属主范围内，跨 session **只读**抽取真实聊天证据（如周报）。
- **难度**：★★★☆☆
- **先修**：[25 Session](25-session-identity.md)、[27 消息生命周期](27-message-lifecycle.md)、[31 记忆边界](31-memory-boundaries.md)

用户常问“根据我这周各个聊天，写周报”。这需要读 **transcript**，不是翻长期 memory，也不是恢复某个 checkpoint。实现：`backend/leagent/tools/util/conversation_history.py`（bootstrap curated 列表已注册 `ConversationHistoryTool`）。

## 学习目标

1. 分清 `list` / `get` / `extract` 三种操作。  
2. 理解 `resolve_effective_user_id` + 所有权校验。  
3. 知道默认角色过滤与字符预算如何防止上下文爆炸。  
4. 再次强调：跨会话历史 ≠ 语义记忆召回 ≠ checkpoint resume。  
5. 能设计「先 list 再 get/extract」的省 token 剧本。

## 核心心智模型：只读、属主范围、有界抽取

```text
当前 turn 的 ToolContext.user_id / session_id
  → resolve_effective_user_id
  → 仅扫描该 user 拥有的 sessions
  → operation:
       list    → 窗口内会话元数据
       get     → 单个 session 消息（默认可回落到当前会话）
       extract → 多会话 user/assistant 回合拼装（周报推荐）
  → 截断：max_sessions / max_messages_per_session / max_chars_per_message
```

这是在读 **TieredSessionStore / Chat 服务中的 transcript**，不会写入 memory，也不会创建 checkpoint。

## 数据流：安全检查落在何处

```text
模型发起 conversation_history
        │
        ▼
ToolExecutor（只读、可并发）
        │
        ▼
解析 operation / 时间窗 / 预算参数
        │
        ▼
effective_user_id；缺 user → error
        │
        ▼
list：按时间窗枚举属主 sessions
get/extract：chat.get_session(..., user_id=) 或比对 state.user_id
        │
        ▼
按 roles 过滤（默认 user+assistant）→ 截断 → 返回结构化数据
        │
        ▼
进入 tool_result → 下一轮模型写作（仍受本轮上下文预算约束）
```

相邻篇：[27](27-message-lifecycle.md) 讲单会话写入；[28](28-history-compaction.md) 讲单会话压缩；[32](32-three-store-memory.md)/[33](33-memory-formation.md) 讲有损长期记忆——**周报证据不要指望 recall**。

## LeAgent 的真实实现要点

- 文件：`backend/leagent/tools/util/conversation_history.py`  
- `is_read_only=True`、`is_concurrency_safe=True`  
- 别名：`chat_history`、`extract_conversation` 等（以工具定义为准）  
- 时间窗：`since`/`until` 或 `days`（1–365，默认 7）  
- `roles` 默认只要 `user`+`assistant`，降低 tool 噪声  
- `get` / `extract` 路径校验 session 归属：`chat.get_session(..., user_id=)`；若经 session_manager，则比较 `state.user_id`  
- 缺 `user_id` 直接返回 error——避免“知道 UUID 就能读”  
- 描述中明确：**总结已完成/进行中工作前应调用，禁止编造历史。**

路径解释：工具读的是会话服务真相，不是前端本地缓存。compaction 后的 transcript 才是抽取原料——若旧细节已被摘要替换，周报只能基于摘要+保留窗口，这是预期而非 bug。跨用户 session_id 探测应稳定失败。

## 示例：周报抽取参数

```json
{
  "operation": "extract",
  "days": 7,
  "include_current": true,
  "max_sessions": 20,
  "max_messages_per_session": 80,
  "max_chars_per_message": 1500,
  "roles": ["user", "assistant"],
  "query": "发布"
}
```

推荐剧本：

1. `list` 看窗口内有哪些会话标题/时间。  
2. 对可疑 `session_id` 做 `get` 深挖。  
3. 需要拼装多会话证据时再 `extract`，并收紧 `query` / 预算。  
4. 模型基于工具结果写作；禁止「没抽到就编」。

## 验证命令

```bash
cd backend
uv run pytest tests/test_tools/test_conversation_history.py -v
```

重点看：无 user 失败、跨 user session 拒绝、时间窗与截断字段、默认 roles 过滤。

## 常见误区与排障

1. **用 AgentMemory.recall 代替周报。** recall 是有损筛选；周报需要对话证据。  
2. **把 session_id 当能力证明。** 必须属主校验。  
3. **extract 不设预算。** 多会话全文会撑爆上下文，触发 compaction 或模型截断。  
4. **默认带上 tool/system。** 噪声大且可能含敏感工具输出。  
5. **写入工具结果到另一个用户的 session。** 本工具是只读；越权写是更严重 bug。  
6. **以为 include_current=false 仍能看到本轮尚未持久化的半截流。** 以已落盘 transcript 为准。  

排障：工具 error 文案是否指向缺 user / 越权 → 时间窗是否过窄 → 预算是否把关键回合裁光 → 模型是否跳过工具直接编造（应用评测/提示约束）。

## 业内对照

ChatGPT “记忆”偏长期偏好；Cursor/IDE agent 常限当前 workspace 线程。企业助手则常提供 “search my past tickets”。LeAgent 用显式只读工具暴露跨会话 transcript，并把安全放在 user 范围，而不是塞进无边界的 system prompt。

## 总结与延伸阅读

`conversation_history` 让模型在**授权属主**内拉取真实聊天证据。它连接的是 session transcript 平面，与 checkpoint 恢复、长期 memory 召回并列但不可互换。做总结类任务时：先抽取，再写作，并尊重截断边界。

- [27｜消息生命周期](27-message-lifecycle.md)
- [31｜记忆边界](31-memory-boundaries.md)
- [32｜三存储](32-three-store-memory.md)
