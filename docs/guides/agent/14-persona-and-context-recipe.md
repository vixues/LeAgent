# 14｜解耦 Persona 与 Context Recipe

## 定位与先修

[13｜分层提示词](13-layered-prompts.md) 已经说明：系统提示词由 `ContextManager.prepare_turn` 装配，`PromptBuilder` 只是 façade。本篇回答一个更具体的设计问题——为什么「角色怎么说」与「本轮装哪些上下文源」必须拆成两个旋钮。建议先修 12–13。

对照代码：[`AgentDefinition.resolved_recipe()`](../../../backend/leagent/runtime/definition.py)、[`ContextManager.recipe`](../../../backend/leagent/context/manager.py)、[`RECIPE_REGISTRY`](../../../backend/leagent/context/recipe.py)、[`IdentitySource`](../../../backend/leagent/context/sources/identity.py)。

## 学习目标

完成本篇后，你应该能：

1. 区分 `prompt_variant`（persona 模板）与 `context_recipe`（source 清单）。
2. 解释 Definition 与 ContextManager 上的 recipe 回落规则。
3. 阅读 `RECIPE_REGISTRY` 中 default / coding / script / subagent / rule_judge 的裁剪差异。
4. 在不改人设模板的情况下切换配方，并理解 `merge_recipes` 在项目绑定会话中的作用。

## 心智模型：同一张脸，可以换一套工具台

把一次 turn 的系统侧上下文想象成舞台：

- **Persona（IdentitySource）**：演员的台词与人设，通常来自 `prompts/templates/<variant>.md`，也可被 `persona_override` 或短 `append_system_prompt` 补充。
- **Recipe（ContextRecipe.entries）**：允许上台的道具清单——常驻 policies、门控指南、环境、召回、working set、工具历史等。
- **Source**：每个道具如何把运行时状态投影成 `ContextBlock`。

若强行绑死「一个人设文件 = 一套完整装配」，则每做一个领域角色都要复制二十多个 source；反过来，想给 coding 会话加项目记忆却不得不改人设文案。解耦之后可以这样组合：

```text
prompt_variant  = finance_expert   # 人设模板名
context_recipe  = default_agent    # 仍使用完整办公上下文 sources
```

`ContextManager` 构造时写明：`recipe` 默认等于 prompt variant，但允许显式解耦。

## 真实实现路径

1. **Definition**：`context_recipe: str | None = None`；`resolved_recipe()` 返回 `context_recipe or prompt_variant`。
2. **Runtime 物化**：写入 `QueryEngineConfig.context_recipe`，再进入 `ContextManager.recipe`。
3. **prepare_turn**：`get_recipe(self.recipe)`；若本轮绑定了 `project_roots` 且当前 recipe 是 `default_agent`，则 `merge_recipes` 并入 `coding_agent` 的 sources——这是「单体 coding 会话」路径，不必立刻委派子引擎。
4. **IdentitySource**：只读取 `ctx.variant` / `template_variant`（或 override），**不读取** recipe 列表。
5. **RECIPE_REGISTRY**：`subagent` 极简（identity/capabilities/policies）；`script_agent` 去掉 recall 等；`rule_judge` 更短；`default_agent` 最完整。

因此出现两个独立失败模式：人设空白通常是 variant/模板问题；「某本手册没出现」可能是 recipe 未邀请、gate 未开或预算丢掉。

## 分步示例

### 第 1 步：显式解耦

```python
from leagent.sdk import AgentBuilder

finance = (
    AgentBuilder("finance_agent")
    .variant("default_agent")
    .recipe("default_agent")
    .append_system_prompt("你是财务核对助手，所有数字必须给出引用出处。")
    .build()
)
assert finance.resolved_recipe() == "default_agent"
```

### 第 2 步：故意使用精简 recipe

```python
judge = (
    AgentBuilder("rule_judge_agent")
    .variant("default_agent")
    .recipe("rule_judge")  # 仅 identity / policies / environment
    .memory(enabled=False)
    .runtime(max_turns=4)
    .build()
)
assert judge.resolved_recipe() == "rule_judge"
```

同一句「生成 PDF」，在 `default_agent` recipe 下仍可能邀请 `document_generation` 等 gated source；在 `rule_judge` recipe 下根本不会 resolve 这些 id——gate 再怎么匹配也无济于事，因为候选人名单由 recipe 决定。

### 第 3 步：理解 merge_recipes

当父会话保持 `default_agent` 人设、同时又绑定了 coding project roots 时，manager 可合并 coding 特有 source（项目记忆、recent reads 等），让「像办公助理说话，却看得见工程上下文」成为一等能力。

## 验证命令

```bash
cd backend && uv run pytest \
  tests/test_context/test_manager.py \
  tests/test_context/test_sources_identity.py \
  tests/test_sdk_surface.py -k builder -q
```

手工核对方略：只改 `context_recipe`、保持 `prompt_variant` 不变，则 identity 正文应稳定，而 ledger 中的 source 集合应变化。

## 常见误区

1. **以为改 recipe 就会换人设。** Identity 走 variant；recipe 只影响 entries。
2. **以为 recipe 列出就必定注入。** Source 仍可返回 `None`，并受 gate 与 budget 影响。
3. **把历史字段 `PromptVariant.layers` 当执行开关。** 当前主路径按 recipe 选源。
4. **给子 Agent 塞满 default recipe。** 内置 `subagent` 刻意极简，防止上下文泄漏与成本爆炸。
5. **把长篇第二人设写进 `append_system_prompt`。** 短约束合适；长文案应进模板或独立 source。

## 业内对照

Anthropic 实践强调静态 instruction 与动态资料分离，以便前缀缓存；对应 persona 求稳、易变块后置。LangGraph 可用不同 node 换 context builder；此处用 recipe 名切换 source 集合。OpenAI Agents 的 instructions 与 input files / tool results 分工，也近似「人设 vs 附件/召回」。

## 总结与延伸

Persona 决定「像谁」；Recipe 决定「看见什么」。下一篇动手实现投影逻辑：[15｜编写 Context Source](15-context-source.md)。
