# 17｜设计门控提示词（RelevanceGate）

## 定位与先修

常驻 prompt 应保持瘦身；Canvas/GenUI、图表、文档字体、邮件、艺术资产手册等「重型说明书」应按需注入。先修 [13](13-layered-prompts.md)–[16](16-context-budget-and-compaction.md)。核心类型：[`context/relevance.py`](../../../backend/leagent/context/relevance.py)；消费者：[`context/sources/gated_policy.py`](../../../backend/leagent/context/sources/gated_policy.py)、`art_playbook` 等。

## 学习目标

1. 说出 RelevanceGate 的三信号优先级：opt_in → workflow_hint → query。
2. 区分 `opted_in()` 与 `matches()`。
3. 为新的域手册配置 `hints` 与 `opt_in_keys`，并接到 `GatedPolicySource`。
4. 理解 recipe 邀请与 gate 开启是两道闸门。

## 心智模型：三信号开关

实现注释写明的优先级：

1. **显式 harness opt-in**：`template_vars` 中任一 `opt_in_keys` 为真——工作流步骤、`HtmlFrame`/`chat.ask` 小应用、批任务用来「强制开闸」，不依赖用户措辞。
2. **Workflow hint**：对显式 `workflow_hint` 做关键字匹配（在 `opted_in` 路径里与 hint 文本匹配）。
3. **Query 启发式**：对用户 query 做子串匹配（`matches` 在未 opted_in 时回落到 `_matches_text(query)`）。

```text
matches(query, workflow_hint, template_vars):
  if opted_in(template_vars, workflow_hint): return True
  return hints 命中 query
```

`hints` 应具体，过宽会假阳性污染无关轮次。

## 真实实现路径

`GatedPolicySource._is_relevant` 调用 `gate.matches(...)`；不相关则 `resolve` 返回 `None`。相关时才从 `prompt_registry` 加载 `policies/<name>.md`，并做 `requires_tools` 过滤与变量替换。对照：`PoliciesSource` 每轮加载小集合（如 file_access、database_tool、human_gate）。

现成例子（节选）：

- canvas：`opt_in_keys=("canvas_guide", "enable_canvas")` + genui/canvas 等 hints；
- chart、document_fonts、document_generation、email_tool、settings_setup：各自一套 hints / opt_in_keys。

Recipe 仍需包含对应 source id（如 `canvas_guide`）；否则 gate 开了也不会被并发 resolve。

## 分步示例

### 第 1 步：定义 Gate

```python
from leagent.context.relevance import RelevanceGate

GATE = RelevanceGate(
    name="canvas_guide",
    hints=("canvas", "genui", "生成界面", "htmlframe"),
    opt_in_keys=("canvas_guide", "enable_canvas"),
)
```

### 第 2 步：三种打开方式

```python
# A. 用户自然语言
assert GATE.matches("请用 GenUI 做一个 KPI 看板")

# B. 工作流提示（不依赖 query 措辞）
assert GATE.matches(
    "随便聊聊",
    workflow_hint="canvas dashboard step",
)

# C. Harness 强制
assert GATE.matches(
    "你好",
    template_vars={"enable_canvas": True},
)
assert not GATE.matches("今天天气怎么样")
```

### 第 3 步：接到 GatedPolicySource

子类设置 `id`、`gate`、`policy_names`，复用现有 markdown 政策文件，避免第二套文案源。`invalidation_key` 通常包含「是否 relevant」，避免把跳过结果与命中结果缓存混淆。

### 第 4 步：在 prepare_turn / 引擎调用传入

工作流或 HtmlFrame 在构造 `PromptContext` / `prepare_turn` 时设置 `template_vars` 或 `workflow_hint`。仅改用户可见文案而不传 harness 信号，则只能依赖 query 启发式。

## 验证命令

```bash
cd backend && uv run pytest tests/test_context/test_relevance.py -v
```

可加 gated policy / manager 集成测试，构造「query 不含关键字但 template_vars 打开」断言 block 出现。

## 常见误区

1. **hints 用过于通用的词**（如「生成」「报告」）。会误开文档或 canvas 手册。
2. **只配 gate、不改 recipe。** 候选人名单没有该 source id 时永远不会 resolve。
3. **把常驻小政策也改成 gate。** 权限与人机门禁应每轮可见。
4. **混淆 `opted_in` 与 `matches`。** 测试 harness 场景应直接测 `matches(..., template_vars=...)`。
5. **用 gate 代替 budget。** Gate 决定「解析与否」；即使打开仍可能被 minimise 丢掉——此时应提高 priority/weight 或缩小正文。

## 业内对照

- Anthropic 建议工具说明按需出现；此处升格为统一 `RelevanceGate` 原语。
- LangGraph 常用条件边跳过节点；gate 是 prompt 装配域的条件边。
- 特性开关（feature flag）≈ `opt_in_keys`；搜索相关性 ≈ query hints。

## 数据流：两道闸门如何串联

```text
Recipe.source_ids 是否邀请该 source？
  否 → 永不 resolve
  是 → RelevanceGate.matches(query, workflow_hint, template_vars)
          否 → resolve 返回 None（不占预算）
          是 → 加载 policies/<name>.md → ContextBlock
                → 仍可能被 minimise 裁掉
```

因此「手册没出现」有三种完全不同的原因：没进 recipe、gate 未开、预算丢掉。排障必须按此顺序查 ledger，而不是先怪模型「不听话」。相邻篇 [14](14-persona-and-context-recipe.md) 讲邀请名单，[16](16-context-budget-and-compaction.md) 讲裁剪，[18](18-prompt-cache-and-context-hygiene.md) 讲门控如何保护稳定前缀缓存。

### 设计新域手册的检查表

1. 写清 `hints`（中英关键词要具体，避免「生成」「报告」这类万能词）。  
2. 配齐 `opt_in_keys`，供工作流 / HtmlFrame 强制开闸。  
3. 复用 `policies/*.md` 单文案源，经 `GatedPolicySource` 加载。  
4. 把 source id 加进相关 `RECIPE_REGISTRY` 条目。  
5. 补 `tests/test_context/test_relevance.py` 风格用例：自然语言命中、hint 命中、template_vars 命中、无关 query 不命中。  
6. 若打开后仍不见块，查 priority/weight 是否过低被 minimise 淘汰。

### 路径速查

- `backend/leagent/context/relevance.py`  
- `backend/leagent/context/sources/gated_policy.py`  
- 艺术手册同模式：`art_playbook` source（经同一 `RelevanceGate` 思想）

## 总结与延伸

门控让「全面能力」与「瘦 system prompt」共存：默认不付款，域相关或 harness 声明时再付款。最后一篇把稳定前缀、fingerprint 与卫生习惯串起来：[18｜Prompt Cache 与上下文卫生](18-prompt-cache-and-context-hygiene.md)。
