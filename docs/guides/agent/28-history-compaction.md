# 28. History Compaction：上下文变短，不等于历史消失

## 定位与先修

长对话终将撞上模型上下文上限。LeAgent 用 **microcompact**、渐进压缩与可选 **LLM autocompact** 管理**送进模型的历史工作集**，而不是简单等同于“删掉用户聊天”。先修：[26](26-tiered-session-store.md)、[27](27-message-lifecycle.md)、[31](31-memory-boundaries.md)。代码主线是 `backend/leagent/memory/compact.py` 与 `backend/leagent/context/session_compression.py`。

请特别注意命名陷阱：`memory/compaction.py` 里的 `MemoryConsolidator` 负责**长期记忆**的衰减、合并与修剪，与本篇 transcript / LLM 历史压缩不是一回事。混淆二者会导致你改错子系统还以为周报记忆变少了。

再次划清三层状态：

- **transcript**：用户可见的对话 SSOT（产品是否因压缩改写 SSOT，取决于调用方是否 `replace_messages`）
- **checkpoint**：暂停 run 的消息快照，服务 resume
- **长期 memory**：formation 筛选后的认知存储

## 学习目标

区分 micro / progressive / forced LLM 三层；理解 `snap_autocompact_split` 如何避免切坏 tool 配对；知道摘要失败时为什么选择恒等降级；能向产品同学解释“模型忘了细节”往往是压缩策略而非 SessionStore 丢数据；设计重要路径时不把“赌摘要记得住”当持久化方案。

## 心智模型：给模型看的有损视图

```text
每轮送模前（session_compression 串联）
  1) microcompact：截断过长 tool_result（默认量级约数千字符预算）
  2) progressive：对仍偏长的会话做结构化挤压
  3) forced LLM autocompact：超过 token 阈值时，
     将较旧回合摘要，并保留 keep_recent 尾巴
```

压缩服务的是上下文工程。它不自动形成 Episode，也不代替 checkpoint。若某次 pause 依赖完整 `mutable_messages`，需要理清：压缩写回 session 的时机是否发生在 checkpoint 之前，避免 resume 读到不一致视图。

## 真实实现

`build_microcompact` 返回可在每轮调用的协程，对超长 tool 内容追加截断标记。`build_autocompact` / `apply_forced_autocompact` 在阈值触发时用提示词模板 `compact_summariser`（registry 缺失则回退内置 summariser）生成摘要；任何 LLM 失败都回退为恒等变换——**丢掉一轮的正确性风险高于暂时触顶报错**。

`snap_autocompact_split` 保证切分后的尾巴不以孤立 `role=tool` 开头，否则部分供应商会直接拒绝历史（tool 消息必须紧跟带匹配 `tool_calls` 的 assistant）。`session_messages_to_compact_llm_dicts` 等小工具尽量保留消息 id，便于压缩结果映回 `SessionMessage` 并与 UI projection 对齐。

具体阈值以 `settings.session` 中 `autocompact_token_threshold`、`autocompact_keep_recent` 等配置为准；不同部署可能调过默认值，请读当前配置而不是死记文档数字。

## 示例：切分安全

```python
from leagent.memory.compact import snap_autocompact_split

messages = [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "", "tool_calls": [...]},
    {"role": "tool", "content": "huge..."},
    {"role": "assistant", "content": "done"},
]
split = snap_autocompact_split(messages, len(messages) - 2)
# split 可能左移，避免尾巴以 tool 开头
```

产品建议：关键文件路径、决策与数字结果应落入产物、`todo_write` 或显式 memory，而不是赌下一轮摘要仍保留。对用户宣称“我们压缩了历史以节省费用”时，要说明哪些内容仍完整可查（例如 SSOT / 导出），哪些仅对模型变成摘要。

## 验证命令

```bash
cd backend
uv run pytest tests/test_autocompact_split.py -q
```

可再构造含 tool 对的长历史，断言压缩后仍满足供应商配对约束；并确认强制摘要失败时消息列表不变。

## 常见误区

1. **“压缩了所以数据库删了聊天。”** 默认意图是上下文工程；是否改写 SSOT 是显式调用决策。
2. **把 MemoryConsolidator 当聊天压缩。** 那是 episodic 维护。
3. **在 pause 前无序 replace。** 可能导致 checkpoint 与可见 transcript 语义错位。
4. **摘要失败就中断用户 turn。** 实现选择降级为不压缩。
5. **keep_recent 过小。** 最近工具轨迹被吃掉，模型重复劳动。
6. **用 compaction“清理敏感信息”。** 安全删除应有专门策略，摘要不是合规擦除。

## 业内对照

Anthropic 提示缓存降低重复前缀成本，但不等于自动摘要。LangGraph 常把 summarization 做成图节点。消费级聊天产品则对长线程做用户不可见的压缩。LeAgent 把 micro/auto 放进 query 依赖链，并显式处理 tool 配对不变量，这是工程上容易被忽视却会导致“偶发 400”的细节。

## 与另外两层状态的协作

压缩策略要与 transcript、checkpoint、memory 的产品承诺对齐。如果产品保证“导出聊天永远完整”，那么 LLM autocompact 写回 `replace_messages` 时必须十分谨慎，或改为只压缩进模视图而不改 SSOT。如果 pause/resume 依赖 checkpoint 内消息，压缩不应在快照之后悄悄改写那份工作集。如果业务要求“重要偏好长期可问”，应走 memory formation，而不是希望摘要句子碰巧留下偏好。反过来，也不要把 compaction 当成删除敏感信息的合规手段：摘要仍可能残留，彻底清除需要专门的删除与审计流程。团队在设计长会话体验时，应明确告诉用户：为了继续对话，早期细节可能被总结；需要永久保留的内容请收藏产物或显式存入记忆。

## 总结

Compaction 是面向模型的有损视图管理：先截断巨大工具输出，必要时再摘要旧回合，并保住近期与协议合法的尾巴。它不取代 transcript 的产品语义，更不取代 checkpoint 或长期记忆。调试“模型忘了”时，先检查是否被摘要，再怀疑存储；设计关键事实时，把它们写成产物或 memory，而不是写进会被压缩的中间 tool 日志。
