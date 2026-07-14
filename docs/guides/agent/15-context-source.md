# 15｜编写 Context Source

## 定位与先修

Recipe 只是「邀请谁上台」；真正把运行时状态变成提示词块的是 `ContextSource`。先修 [13](13-layered-prompts.md)、[14](14-persona-and-context-recipe.md)。协议与句柄见 [`context/sources/base.py`](../../../backend/leagent/context/sources/base.py)；注册表见 [`context/sources/__init__.py`](../../../backend/leagent/context/sources/__init__.py)；块类型见 [`context/types.py`](../../../backend/leagent/context/types.py)。

写好 Source 的标准是：输入只依赖本轮 `ResolveContext`，输出要么跳过（`None`），要么给出一块可计量、可排序、可审计的 `ContextBlock`。

## 学习目标

完成本篇后，你应该能：

1. 实现满足 `ContextSource` Protocol 的类：元数据字段、`invalidation_key`、异步 `resolve`。
2. 正确选择 `RenderTarget.SYSTEM` 与 `ATTACHMENT_USER`，避免把易变材料塞进稳定前缀。
3. 从 `ResolveContext` 读取 query、tools、session、memory、`template_vars` 等，而不另开全局状态。
4. 将 source 登记进 `SOURCE_REGISTRY`，并加入对应 `ContextRecipe` 的 entries。

## 心智模型：每个 Source 是可单测的异步投影

```text
ResolveContext（本轮只读句柄）
  → ContextSource.resolve()
      → ContextBlock | None
```

- 返回 `None`：本轮跳过（无数据、gate 关闭、缺依赖、策略不允许）。
- 返回 `ContextBlock`：携带 `body`、`tokens`/`cost`、`signature`、`priority`/`weight`、`metadata`。
- `invalidation_key`：喂给 `SourceCache`；`PROCESS`/`SESSION` 可能命中缓存，`TURN` scope 强制不缓存。

不要在普通 source 里直接再调一次 LLM 写长摘要——那是 compaction / recall 形成阶段的职责。Source 应尽量纯粹，才能在单元测试里用假句柄覆盖分支。

## 真实实现路径

1. `ContextManager.prepare_turn` 取出 recipe → `get_all_sources()` → 对启用条目并发 `resolve`。
2. `IdentitySource`：读模板或 override，`priority=2000`，目标为 SYSTEM，属于强钉扎前缀。
3. `PoliciesSource`：每轮加载小而关键的安全/权限政策；`GatedPolicySource`：按 `RelevanceGate` 加载重型手册。
4. `RecallSource` / `WorkingSetSource` / `ToolHistorySource` 等常走 `ATTACHMENT_USER`，减少对 system 前缀的扰动。
5. 全部块收集后：先 `enforce_source_hard_budgets`，再 `minimise`，再做三档排序与 ledger 记账。

`ResolveContext` 携带 cwd、query、variant、persona_override、workflow_hint、template_vars、tools、agent_memory、session_manager、file_state、working_set、project_roots、prompt_registry 等。新 Source 应只通过该句柄取数，保持与引擎解耦。

## 分步示例：自定义「发布标签」Source

### 第 1 步：实现类

```python
from leagent.context.sources.base import ResolveContext
from leagent.context.types import ContextBlock, ContextScope, RenderTarget

class ReleaseNotesSource:
    id = "release_notes"
    kind = "state"
    scope = ContextScope.SESSION
    priority = 400
    weight = 1.0
    render_target = RenderTarget.ATTACHMENT_USER

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"release_notes:{ctx.session_id}:{ctx.template_vars.get('release_tag', '')}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        tag = (ctx.template_vars or {}).get("release_tag")
        if not tag:
            return None
        body = f"当前发布标签：{tag}\n涉及发版问题时请引用此标签。"
        return ContextBlock(
            source_id=self.id,
            kind=self.kind,
            render_target=self.render_target,
            body=body,
            tokens=ContextBlock.approx_tokens(body),
            cost=len(body),
            signature=ContextBlock.content_signature(self.id, body),
            priority=self.priority,
            weight=self.weight,
            metadata={"scope": self.scope.value},
        )
```

### 第 2 步：注册并加入 recipe

将实例登记到 `SOURCE_REGISTRY`（模式对齐现有 Identity/Policies 源），并在目标 recipe（例如 `default_agent` 或专用 recipe）的 `source_ids` 中加入 `"release_notes"`。只注册不邀请，manager 永远不会 resolve 它。

### 第 3 步：调用侧注入

在 `prepare_turn(..., template_vars={"release_tag": "v1.2.0"})` 或引擎等价路径传入。无 tag 时返回 `None`，不占预算。

### 第 4 步：单测

构造假 `ResolveContext`，断言有无 tag 时的行为；再用 manager 集成测查看 ledger 是否出现该 `source_id`。

## 验证命令

```bash
cd backend && uv run pytest \
  tests/test_context/test_sources_identity.py \
  tests/test_context/test_sources_state.py \
  tests/test_context/test_manager.py -q
```

新增 source 后应补齐自己的单测，模式对齐 `tests/test_context/`。

## 常见误区

1. **把巨型易变资料塞进 SYSTEM。** 应优先 ATTACHMENT_USER，保护可缓存前缀。
2. **`invalidation_key` 过粗或过细。** 过粗返回过期块；过细导致 cache 永 miss。
3. **在 resolve 里吞掉异常却不记日志。** 现有实现通常 warning 后返回 `None`，避免拖垮整轮。
4. **注册了却忘改 recipe。** 未邀请的 id 不会进入并发 resolve 列表。
5. **误以为任意高 priority 都能钉死。** `PINNED_THRESHOLD = 1000`；低于阈值参与性价比竞争，见第 16 篇。

## 业内对照

LangChain 常用 runnable 拼装上下文；LlamaIndex 用 node/postprocessor 做投影与过滤。LeAgent 选择显式 Protocol + registry，使每个来源的字符数、跳过原因与是否截断都能进入 `ContextLedger`，利于预览 API 与线上排障。Anthropic 强调工具结果与资料的角色边界，正对应 `render_target` 分流。

## 数据流：Source 在 prepare_turn 中的位置

```text
get_recipe → 过滤启用的 source_ids
  → 并发 await source.resolve(ResolveContext)
  → 收集 ContextBlock（跳过 None）
  → 硬预算 → minimise → 按 render_target 分区
  → system 字符串 + attachment 消息 + ledger
```

`ResolveContext` 是本轮只读句柄：query、tools、session、memory、file_state、template_vars、workflow_hint 等。Source 不应另开全局单例偷读请求，否则无法单测，也会在子 Agent / 工作流节点里读到错误作用域。相邻篇 [14](14-persona-and-context-recipe.md) 决定谁被邀请，[16](16-context-budget-and-compaction.md) 决定谁留下，[17](17-relevance-gated-prompts.md) 决定重政策何时 resolve。

### 排障清单

1. **注册了但 ledger 没有**：recipe 未列入 id。  
2. **有时有有时无**：gate / template_vars / 数据空返回 None。  
3. **块进了却总被裁**：提高 priority（注意 `PINNED_THRESHOLD`）或减正文、提 weight。  
4. **缓存命中过期内容**：`invalidation_key` 过粗；TURN scope 本就不缓存。  
5. **污染 cache**：把易变正文放到 `RenderTarget.SYSTEM`——应改 `ATTACHMENT_USER`。

### 与真实内置源对照学习

建议阅读并对照测试：`IdentitySource`、`PoliciesSource`、`GatedPolicySource`、`RecallSource`、`WorkingSetSource`。新源的 PR 应包含：Protocol 字段齐全、None 路径、异常降级为 warning、recipe 变更、单测。勿在 resolve 里再调一次完整 Agent 循环写摘要。

## 总结与延伸

Source 是上下文系统的可测试边界。下一批块如何竞争有限窗口：[16｜上下文预算、裁剪与压缩](16-context-budget-and-compaction.md)。
