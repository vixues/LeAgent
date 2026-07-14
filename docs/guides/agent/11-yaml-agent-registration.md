# 11｜从 YAML 加载和注册 Agent

## 定位与先修

当领域 Agent 变多，或希望运维与产品在不改 Python 的情况下调整温度、工具白名单或轮次预算时，应把 `AgentDefinition` 落到 YAML。先修：[09｜AgentBuilder](09-agent-builder.md)、[10｜领域 Agent](10-domain-agent-definition.md)。核心实现集中在 [`runtime/registry.py`](../../../backend/leagent/runtime/registry.py)：`AgentRegistry`、`register_builtin_agents`、`get_agent_registry` 与 `load_agents_from_yaml`。

YAML 不是另一套「运行时语言」，它只是同一份声明契约的文件作者；最终仍由 `AgentRuntime` 物化进统一内核。

## 学习目标

完成本篇后，你应该能：

1. 使用 `AgentRegistry` 完成 `register` / `get` / `try_get` / `names` / `all`。
2. 按「顶层 key = agent 名」的结构写出合法 YAML，并与 Pydantic 字段对齐。
3. 理解 `load_agents_from_yaml` 的 `replace`、跳过非法项、失败不中断整文件，以及返回的已加载名列表。
4. 把内置注册与 YAML 扩展组合成进程级名字空间，再交给 Runtime。

## 心智模型：Registry 是名字空间，YAML 是批量作者

```text
YAML 文件
  → yaml.safe_load → {name: fields}
    → AgentDefinition(**fields)
      → AgentRegistry.register(..., replace=...)
        → AgentRuntime.resolve("name")
```

内置四个 agent（`default_agent`、`coding_agent`、`script_agent`、`subagent`）在首次 `get_agent_registry()` 时惰性注册。Builder 适合代码与单测；YAML 适合部署差异与环境覆盖。两条路径收敛到同一类对象，避免「配置世界」与「代码世界」各写一套 schema。

## 真实实现路径

`load_agents_from_yaml(path, registry=None, replace=True)` 的行为可以逐条对照源码：

1. 打开文件并用 `yaml.safe_load` 解析；根节点必须是 mapping，否则抛 `ValueError`。
2. 遍历每个 `(name, fields)`；若 `fields` 不是 dict，打 `agent_yaml_skip` 警告并跳过。
3. `fields.setdefault("name", name)`，再用 `AgentDefinition(**fields)` 做校验。
4. 单条校验失败只记 `agent_yaml_load_failed`，不中断整文件加载——这对「多 agent 配置包」很友好，但也要求你检查返回列表。
5. `target.register(definition, replace=replace)`；未传 `registry` 时写入全局 `get_agent_registry()`。
6. 返回成功加载的名字列表。

`AgentRegistry.register` 在同名且 `replace=False` 时抛 `ValueError`。`get` 失败会在异常消息中列出已注册名字，便于排查拼写错误。测试重置可用 `reset_agent_registry()`。

## 分步示例

### 第 1 步：编写 `agents.yaml`

```yaml
support_agent:
  description: 客户支持专家
  prompt_variant: default_agent
  tools:
    allow: [web_search, knowledge_*]
    max_tools: 12
  model:
    temperature: 0.3
  memory:
    recall_limit: 8
  runtime_profile: standard
  max_turns: 12
  subagents: [script_agent]

invoice_agent:
  description: 发票核对
  prompt_variant: default_agent
  context_recipe: default_agent
  tools:
    allow: [pdf_*, knowledge_*]
    deny: [email_*]
  model:
    task: chat
    temperature: 0.1
  memory:
    enabled: true
    formation: false
  max_turns: 15
```

字段名必须匹配 `AgentDefinition` 与嵌套 Policy（`tools`、`model`、`memory`），例如运行预算字段是 `runtime_profile` 而不是臆造的顶层 `profile`。

### 第 2 步：加载并检查

```python
from leagent.sdk import AgentRegistry, load_agents_from_yaml, register_builtin_agents

reg = AgentRegistry()
register_builtin_agents(reg)
loaded = load_agents_from_yaml("/path/to/agents.yaml", registry=reg, replace=True)
print(loaded)       # ['support_agent', 'invoice_agent']
print(reg.names())  # 同时包含内置与 YAML 名
print(reg.get("support_agent").tools.allow)
```

### 第 3 步：接入 Runtime

```python
from leagent.sdk import AgentRuntime

runtime = AgentRuntime.from_service_manager(service_manager, registry=reg)
result = await runtime.run("support_agent", "查一下退货政策并给出三点摘要。")
```

也可在应用启动钩子加载 YAML，再把同一 registry 注入 Runtime / ServiceManager 工厂。关键是「名字解析」与「物化」使用同一张表。

## 验证命令

```bash
cd backend && uv run pytest tests/test_sdk_surface.py -k "yaml or load_agents or registry" -v
```

该组测试会写临时 YAML、加载到独立 registry，并断言名称列表与基础字段。离线可跑，无需模型 API Key。

## 常见误区

1. **根节点写成 list。** 实现要求 mapping；list 会立刻 `ValueError`。
2. **以为文件名就是 agent 名。** 名称取自顶层 key（及 `name` 字段），与路径无关。
3. **忽视默认 `replace=True`。** 它会覆盖同名内置定义；扩展时优先使用唯一名字，或按需设 `replace=False` 并处理冲突。
4. **YAML 键名照搬 Builder 方法名。** 应以 `AgentDefinition` 字段为准（例如 `runtime_profile`、`max_turns`）。
5. **把局部加载失败当成整体成功。** 失败条目只警告；务必核对返回的 `loaded` 长度与内容。

## 业内对照

Kubernetes 用 YAML 声明 workload 期望状态；此处用 YAML 声明 agent 契约，真正的循环仍由内核执行。LangGraph / Crew 生态也有 yaml/json agent 配置；LeAgent 的特点是与 `AgentBuilder`/`AgentDefinition` 字段一一对应，不另造第二套 schema。MCP 服务配置偏 JSON 连接信息，而 Agent 定义更偏产品策略，用 YAML 更利于评审与 diff。

## 总结与延伸

YAML + Registry 解决「多 Agent 配置分发」；真正执行仍靠 Runtime 物化。把最小定义补齐 hooks、上下文治理、会话与可观测后，才算工程化：[12｜把最小 Agent 补成工程化 Agent](12-production-ready-agent.md)。
