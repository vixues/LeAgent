# 13. 设计分层提示词系统

## 定位与先修

本文位于“提示词与上下文工程”的入口。建议先读[把最小 Agent 补成工程化 Agent](12-production-ready-agent.md)，并知道一次请求最终会进入 `QueryEngine → query`。这里的“分层”不是把一个 Markdown 文件切成八段，而是把不同生命周期、优先级和渲染位置的信息建模为独立 `ContextSource`，再统一组装。

对应实现主要在 [`prompts/builder.py`](../../../backend/leagent/prompts/builder.py)、[`context/manager.py`](../../../backend/leagent/context/manager.py)、[`context/types.py`](../../../backend/leagent/context/types.py) 与 [`context/recipe.py`](../../../backend/leagent/context/recipe.py)。

## 目标

学完后你应能：

1. 解释 `PromptBuilder` 为什么是 façade，而不是实际的分层调度器；
2. 区分模板、recipe、source、block、attachment 与 transcript；
3. 沿真实数据流定位系统提示词的来源；
4. 不把旧的 L0～L7 注释或独立 renderer 误认为当前主路径的执行模型。

## 心智模型：提示词是一条装配流水线

当前主路径可概括为：

```text
PromptContext
  → PromptBuilder.build()                 # 薄 façade
  → ContextManager.prepare_turn()
  → ContextRecipe.entries
  → ContextSource.resolve()（并发）
  → ContextBlock[]
  → 单 source 硬上限 + 全局预算
  → SYSTEM / ATTACHMENT_USER 分流
  → 稳定前缀、普通块、易变尾部排序
  → BuiltPrompt + attachment_messages + ContextLedger
  → QueryEngine 将附件放在 transcript 前，再调用 query()
```

最重要的事实是：[`PromptBuilder.build()`](../../../backend/leagent/prompts/builder.py) 只检查 `context_manager`、传递 query/persona/template vars 等参数，并返回 `turn.built_prompt`。没有 manager 会直接抛出 `ValueError`；旧的“仅凭 registry 自己收集各层”的 fallback 已删除。单元测试 [`test_prompts_package.py`](../../../backend/tests/test_prompts_package.py) 固化了这个契约。因此，`PromptBuilder` 是兼容调用者的组合 façade，真正的 source 调度、预算、排序、hash 和附件分流都在 `ContextManager`。

## 实现路径

### 1. 模板只负责 Persona 与元数据

[`prompts/templates/default_agent.md`](../../../backend/leagent/prompts/templates/default_agent.md) 的正文由 `IdentitySource` 读取，front matter 中的 `policies` 列表由 `PoliciesSource` 使用。`PromptRegistry` 负责定位、解析和缓存模板；它不是每轮上下文调度器。

### 2. Recipe 决定“邀请谁参加”

`ContextRecipe.entries` 是 source ID 的有序配置。例如 `default_agent` 包含 `identity`、`capabilities`、`policies`、多个门控指南、环境、项目记忆、召回、working set 与工具历史。recipe 仅声明候选 source；source 可以因条件不满足而返回 `None`。

### 3. Source 把状态解析成统一 Block

每个 source 实现 `id/scope/priority/weight/render_target`、`invalidation_key()` 和异步 `resolve()`，输出不可变 `ContextBlock`。其中：

- `SYSTEM` 块进入 `system_text`；
- `ATTACHMENT_USER` 块成为带 metadata 的 user-role 附件；
- `priority` 与 `weight` 参与预算；
- `signature` 用于附件去重；
- `scope` 影响 source cache。

这比把 recall、环境和工具说明直接拼进 persona 更容易测试，也使“信息在哪里出现”成为显式契约。

### 4. Manager 才执行装配

`prepare_turn()` 并发 resolve recipe 中所有 source，先执行 source 硬截断，再运行全局 minimiser。保留下来的系统块按三档排序：固定顺序的 pinned 前缀、普通 session 块、易变 turn 块。附件单独渲染并按 `(source_id, signature)` 去重，最多记住 256 个签名。最后返回 `TurnContext`，其中不仅有 `BuiltPrompt`，还有 ledger、环境快照、项目记忆来源和 recall handle。

## 分步示例：追踪一次“生成 PDF 报告”

1. 调用方提供 query“生成中文 PDF 报告”。
2. `IdentitySource` 从 `default_agent.md` 得到 persona。
3. `PoliciesSource` 加载该模板声明的常驻 policy。
4. `DocumentGenerationSource` 与 `DocumentFontsSource` 的 gate 命中 query，返回系统块；不相关的 email guide 返回 `None`。
5. `RecallSource` 若有结果，将其渲染成 user attachment，而不是直接塞入系统提示词。
6. budget 可能截断或丢弃低性价比 block。
7. `QueryEngine` 使用 `turn.built_prompt.system_text`，并把 `turn.attachment_messages` 放到会话消息之前。

这个例子说明“分层”同时包含来源、生命周期、预算和角色边界，而不只是 Markdown 标题。

## 验证

以下验证离线可运行：

```bash
cd backend
uv run pytest tests/test_context/test_manager.py \
  tests/test_context/test_prompt_builder_integration.py \
  tests/test_prompts_package.py -q
```

还可查看聊天 prompt preview API 的测试与 [`ContextLedger`](../../../backend/leagent/context/ledger.py)：它记录 source 的 bytes/tokens、cache hit、skip、truncated、dropped 与 hash，适合定位“为什么某块没有进入请求”。

## 常见误区

- **把 `PromptBuilder` 当 orchestration engine。** 它只是 façade；canonical path 是 `ContextManager.prepare_turn()`。
- **把 `PromptVariant.layers` 当当前 source 开关。** registry 仍解析该字段，但 manager 按 recipe 选择 source，当前主路径没有据此过滤 recipe。
- **认为所有上下文都属于 system prompt。** recall、working set、tool history、recent reads 等可走 user attachment。
- **认为 recipe 中出现就必定注入。** source 可因无数据、gate 未开、工具缺失、异常或预算而消失。
- **相信注释中的 L0～L7 就等于当前实现。** 这是历史术语；应以 `ContextBlock`、render target 和三档排序为准。

## 与 Anthropic 等业内方案对照

Anthropic 的实践强调把稳定指令放在提示词前部、动态输入置后，并可通过 prompt caching 标记可缓存前缀；OpenAI、DashScope 也会从重复前缀中获得自动缓存收益。LeAgent 当前 manager 的三档排序遵循相同的“稳定前缀、易变尾部”原则，但 canonical manager 只生成普通 system message，并未调用 `AnthropicRenderer` 写入显式 `cache_control`。LangGraph 常把上下文装配放入 graph state/node；Google ADK、OpenAI Agents SDK 更偏向 instruction + runtime context。LeAgent 的特点是把 source、预算、附件和审计 ledger 集中到一个 session-scoped manager。

## 总结与延伸

分层提示词系统的核心不是层数，而是职责边界：registry 管模板，recipe 选候选来源，source 解析状态，budget 做取舍，manager 组装并审计，builder 提供 façade。下一篇将继续解释为什么 Persona 与 Context Recipe 必须解耦，以及同一角色如何复用另一套上下文配方：[解耦 Persona 与 Context Recipe](14-persona-and-context-recipe.md)。
