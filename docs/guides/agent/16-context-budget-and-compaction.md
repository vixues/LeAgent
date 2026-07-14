# 16｜上下文预算、裁剪与压缩

## 定位、难度与先修

- **定位**：管理有限 context window，避免「塞满再爆炸」。
- **难度**：★★★☆☆
- **先修**：[14 Recipe](14-persona-and-context-recipe.md)、[15 Source](15-context-source.md)、[13 分层提示词](13-layered-prompts.md)

上下文工程有两条体积轴：**本轮装配**（sources → blocks → minimise）与**跨 turn 历史**（session compaction）。本篇主攻前者，并指向第 28 篇后者。目标不是「塞进更多字」，而是「在窗口内保住任务推进信号」。

## 学习目标

1. 区分 source 级 hard cap 与全局 `minimise()`。  
2. 说明会话历史压缩（compaction）与门控卸载的不同。  
3. 知道超长时可能的 `prompt_too_long` / autocompact 恢复。  
4. 用测试观察预算行为，而不是凭感觉加长窗口。  
5. 能用 prompt preview / ledger 解释「谁把窗口吃满了」。

## 核心心智模型：两道闸门

```text
各 ContextSource.resolve()
        │
        ▼
per-source 截断 / 省略
        │
        ▼
全局预算 minimise（按成本函数丢弃或缩短低价值块）
        │
        ▼
装配 system + attachments + messages
```

另有一条时间轴：**对话历史压缩**——当 turn 很多时摘要旧消息，不同于本轮 recipe 裁剪。门控（第 17 篇）决定「重手册进不进候选」；预算决定「候选里谁留下来」。

## 数据流：硬上限 → 性价比竞争 → 恢复

```text
get_recipe(recipe) → 并发 resolve 邀请的 sources
        │
        ▼
enforce_source_hard_budgets（单源天花板）
        │
        ▼
minimise(max_chars / 成本函数 / priority&weight)
  · priority ≥ PINNED_THRESHOLD 的块更不易被丢
        │
        ▼
ledger：谁留下、谁裁切、谁丢弃
        │
        ▼
若仍触发 provider 过长 → query 恢复 / autocompact（见测试）
```

相邻篇：[15](15-context-source.md) 写可计量 `ContextBlock`；[17](17-relevance-gated-prompts.md) 先减候选；[18](18-prompt-cache-and-context-hygiene.md) 讲稳定前缀；[28](28-history-compaction.md) 讲 transcript 压缩。

## LeAgent 的真实实现

- 预算：`backend/leagent/context/budget.py`（`minimise`、`enforce_source_hard_budgets`；测试见 `test_budget_cost.py`）  
- 组装：`ContextManager.prepare_turn`（注释写明先硬上限再全局最小化）  
- Recipe：`max_chars`（如默认 24000 量级，以代码为准）  
- 历史压缩：session compaction 相关逻辑与 `tests/test_session_compression.py`  
- 查询恢复：上下文过长时 `query()` 可走 recovery/autocompact 分支（见 `test_query_engine.py`）  
- `FileState` / `WorkingSet`：减少重复注入大文件全文  
- `pre_compact` hooks：压缩前扩展点（对照 Claude PreCompact）  

路径解释：ledger / prompt preview API（`tests/test_chat_prompt_preview_api.py`）是排障主入口——不要只靠「感觉模型变笨」。召回、工具 stdout、门控手册三类最常吃预算；把大结果外置为文件引用通常比内嵌全文划算。

## 分步：排障思路

1. 看 prompt preview / ledger：哪些 source 进了、各多少字符。  
2. 过重：收紧 recipe、加强 gate、降低 recall limit、截断工具结果。  
3. 仍爆：触发 compaction；必要时换更大窗口模型而不是无限加 history。  
4. 工具结果是否该外置为文件引用：经常比内嵌全文更划算。  
5. 确认 pinned 块是否被滥用：优先级过高会挤掉真正相关的动态资料。  
6. 区分「system 前缀膨胀」与「attachments 膨胀」：后者更应截断，前者影响 cache。

## 验证命令

```bash
cd backend
uv run pytest tests/test_context/test_budget_cost.py tests/test_session_compression.py tests/test_query_engine.py -k "length or compact or budget or prompt" -v
uv run pytest tests/test_chat_prompt_preview_api.py -v
```

构造：同一 query 下打开/关闭 canvas gate，观察 ledger 中手册块是否出现；再人为塞大 recall，看 minimise 是否丢低权重块。

## 常见误区与排障

1. **只加 `max_output_tokens`**：解决不了输入膨胀。  
2. **压缩掉仍需的 tool_call 配对**：历史整理必须保持对话合法性。  
3. **把预算当安全控制**：预算防溢出，安全靠权限与沙箱。  
4. **每次打乱 system 前缀顺序**：损害 prompt cache 命中（第 18 篇）。  
5. **关掉 gate 指望「模型自己忽略长手册」**：既贵又不稳。  
6. **WorkingSet 重复灌全文**：应依赖文件状态增量，而不是每轮粘贴。  

症状：间歇性失忆偏好 → 可能被裁掉 recall；工具参数幻觉 → 可能工具结果被截断过度；帐单突增 → 查门控假阳性或 recipe 过全。

## 业内对照

Anthropic compaction / context editing、ADK context compaction、通用「摘要旧轮次」——同属上下文工程。目标：保留任务推进信号，丢掉可再获取的噪声。LeAgent 把成本函数最小化做成显式模块，而不是埋在某一个巨型 prompt builder 里。

## 总结与延伸阅读

预算让 Agent 在现实窗口里活得更久；门控与压缩是手段，任务成功率才是目标。

- [17｜门控](17-relevance-gated-prompts.md)
- [18｜Cache 与卫生](18-prompt-cache-and-context-hygiene.md)
- [28｜历史压缩](28-history-compaction.md)
