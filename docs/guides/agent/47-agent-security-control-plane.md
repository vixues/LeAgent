# 47｜Agent 安全控制面：认证、配额与纵深防御

## 定位、难度与先修

- **定位**：治理篇。把 Agent 安全从“提示词里写一句不要越权”提升到可配置的控制面：谁可以访问实例、谁拥有数据、哪些诊断口暴露、配额如何限制。
- **难度**：★★★☆☆
- **先修**：[43｜Hooks 与 Guardrails](43-hooks-and-guardrails.md)、[25｜Session Identity](25-session-identity.md)；了解局域网部署与反向代理基本概念。

## 学习目标

完成本篇后，你应该能：

1. 说明 `LEAGENT_SECURITY_ENFORCE_AUTH` 三态及桌面例外。
2. 列出强制认证后自动联动的限流、文档与 metrics 门禁。
3. 区分实例访问密码、JWT、命名用户与工具审批四层。
4. 在 SQLite / 多用户场景下选择正确的 workers 与并发配额。
5. 用现有测试与运维清单验收局域网暴露是否可控。

## 核心心智模型：控制面 vs 数据面

```text
控制面（本篇）
  认证 / 会话 JWT / 用户管理 / CORS / Host / 限流 / 配额 / 文档与 metrics 门禁

数据面（Agent 执行）
  工具权限 / Approval / 沙箱 / 文件所有权 / 审批 checkpoint
```

Hooks 只能观察；控制面决定请求是否进入系统，权限层决定工具是否执行。两层都 fail-open 或只靠提示词时，局域网 Agent 会变成“带工具的开放代理”。

纵深防御顺序建议：网络暴露面 → HTTP 认证 → 资源配额 → 工具权限与审批 → 沙箱与路径遏制 → 审计 Trace。

## LeAgent 的真实实现

权威细节见 [`docs/technical/security-control-plane_zh.md`](../../technical/security-control-plane_zh.md)；设置类在 `backend/leagent/config/settings.py` 的 `SecuritySettings`（环境前缀 `LEAGENT_SECURITY_`）。

### 强制认证

| 组件 | 位置 |
|------|------|
| 实例访问密码 | `$LEAGENT_HOME/security.json`（PBKDF2） |
| 会话 JWT | `LEAGENT_SECRET_KEY` / `$LEAGENT_HOME/secrets/.secret_key` HMAC |
| HTTP API | `/api/v1/auth/setup|login|logout`，`/me`，`/status` |
| 命名用户 | `users` 表 + `/api/v1/admin/users` |

`enforce_auth` 三态：

- 未设置 / `null` → **auto**：绑定主机非 loopback 且非桌面时强制；
- `true` → 始终强制；
- `false` → 永不强制（仅本地开发/测试）。

桌面（`LEAGENT_DESKTOP=1`）默认免密码，除非 setup 时要求解锁；可在 loopback 调用 `desktop-bootstrap`。

### 联动硬化

强制认证生效时通常联动：

- 限流（`LEAGENT_SECURITY_RATE_LIMIT_*`，也可 `rate_limit_auto_with_auth`）；
- `gate_diagnostics`：metrics / meta 需 bearer；
- `gate_openapi`：禁用或限制 OpenAPI 文档；
- 工作流 prompt/execution 与工作流 WebSocket 的所有权校验；
- 拒绝弱签名 URL 回退密钥 `"leagent-local-secret"`。

另有 `max_concurrent_per_user`（默认 5）限制每用户并发 Agent/沙箱；`cors_allow_origins`、`trusted_hosts`、可选 HSTS。

### 与 Agent Guardrail 的衔接

控制面挡住未认证请求后，执行路径仍依赖：

- 工具权限与 `approval_requirement`（见 43）；
- 文件层 `is_path_inside` 与 FileScope；
- Session 所有权：知道 `session_id` ≠ 可跨用户读历史。

不要把 `RateLimitHook` 当成集群限流：Hook 异常被吞，且状态在进程内。HTTP 限流与安全配额才是控制面一部分。

### SQLite 与 workers

默认 `LEAGENT_WORKERS=1`。认证策略日志会在 **开放绑定 + 弱密钥** 以及 **SQLite + workers > 1** 时告警。多用户写密集时应切 PostgreSQL（`DATABASE_URL`），并配合 sticky sessions——因为 `ExecutionRunRegistry` 与审批热状态仍是进程内的。

## 验证命令

```bash
cd backend
uv run pytest tests/test_security_control_plane.py -v
```

覆盖 auto enforce 在 `0.0.0.0` vs loopback 的行为，以及 setup/login 往返等。另可运行审批与所有权相关用例：

```bash
uv run pytest tests/test_approval_flow.py -v
```

局域网验收清单（运维）：

1. `openssl rand -hex 32` 写入强 `LEAGENT_SECRET_KEY`；
2. 优先 `127.0.0.1` 绑定或反向代理 + TLS；
3. 打开 UI 完成 **setup**；
4. 需要时在 Admin → Users 建命名用户；
5. 把 `LEAGENT_SECURITY_CORS_ALLOW_ORIGINS` 收窄到真实 UI origin。

## 常见误区

1. **开发时 `enforce_auth=false` 原样上生产**。
2. **以为 Hooks / 提示词能替代 HTTP 认证**。
3. **开放 `0.0.0.0` 却保留弱 secret 与公开 `/docs`**。
4. **SQLite 上盲目 `LEAGENT_WORKERS>1`**。
5. **用 session UUID 猜测代替所有权检查**。
6. **把桌面免密行为照搬到服务器部署**。

## 业内对照

OWASP LLM Top 10 强调不安全输出处理、过度代理、权限过宽与提示注入。MCP / 工具投毒场景要求把外部工具描述当不可信输入。成熟控制面接近 API Gateway + IdP + policy engine；LeAgent 在单机/局域网产品形态下提供“够用的强制认证 + 配额 + 工具审批”组合，而不是完整企业 IAM。与仅依赖 prompt firewall 的演示 Agent 相比，本控制面把决策放在服务配置与中间件。

## 生产检查表与总结

- [ ] 生产绑定与 `enforce_auth` 策略已明确（勿依赖偶然 auto）
- [ ] 强 `LEAGENT_SECRET_KEY`；无弱 signed-URL 回退
- [ ] CORS / Trusted Host 收窄；文档与 metrics 门禁开启
- [ ] 限流与 `max_concurrent_per_user` 已按容量设置
- [ ] SQLite → `workers=1`；多写 → PostgreSQL + sticky
- [ ] 高风险工具默认审批或拒绝，且有自动化测试
- [ ] 审计可关联到 `user_id` + `run_id`
- [ ] 启动告警（开放绑定 / 弱密钥 / SQLite 多 worker）有人认领

安全控制面决定谁能进来；Guardrail 决定进来之后能做什么。两者缺一，Agent 的工具能力就会变成攻击面。

继续阅读：

- [48｜成本、延迟、扩展与生产检查表](48-production-cost-latency-scaling.md)
- [24｜MCP 与工具投毒](24-mcp-and-tool-poisoning.md)
- 技术参考：[安全控制平面](../../technical/security-control-plane_zh.md)
- 测试：[`backend/tests/test_security_control_plane.py`](../../../backend/tests/test_security_control_plane.py)
