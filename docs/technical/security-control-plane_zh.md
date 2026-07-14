# 安全控制平面

LeAgent 的安全控制平面用于阻止未认证的局域网访问、减少信息泄露，并提供轻度的多用户隔离/配额。

英文版：[security-control-plane.md](./security-control-plane.md)

## 强制认证

| 组件 | 位置 |
|------|------|
| 实例访问密码 | `$LEAGENT_HOME/security.json`（PBKDF2 哈希） |
| 会话 JWT | 经 `LEAGENT_SECRET_KEY` / `$LEAGENT_HOME/secrets/.secret_key` 的 HMAC |
| HTTP API | `POST /api/v1/auth/setup`、`/login`、`/logout`，`GET /me`、`/status` |
| 命名用户 | `users` 表 + `GET/POST /api/v1/admin/users` |

### Enforce-auth 策略

`LEAGENT_SECURITY_ENFORCE_AUTH` 为三态：

- 未设置 / `null` → **auto**：当绑定主机不是 loopback（且非桌面）时强制认证
- `true` → 始终强制
- `false` → 永不强制（本地/开发/测试）

桌面端（`LEAGENT_DESKTOP=1` / `LEAGENT_DESKTOP_MODE=1`）默认免密码，除非在 setup 时设置了
`require_unlock_on_desktop`；可在 loopback 上调用
`POST /api/v1/auth/desktop-bootstrap`。

## 纵深防御

- 强制认证时自动启用限流（`LEAGENT_SECURITY_RATE_LIMIT_*`）
- 当认证 + `gate_diagnostics` 开启时，Metrics 需要 bearer 门禁
- 强制认证时禁用 OpenAPI 文档（`gate_openapi`）
- 工作流 prompt/execution 生命周期与工作流 WebSocket 需要所有权 / 认证
- 强制认证时，签名 URL secret 拒绝弱回退值 `"leagent-local-secret"`

## 多用户性能

- 使用 SQLite 时保持 `LEAGENT_WORKERS=1`；并发写请用 PostgreSQL
- 每用户沙箱并发：`LEAGENT_SECURITY_MAX_CONCURRENT_PER_USER`（默认 5）
- 启动日志会在开放绑定 + 弱密钥、以及 SQLite + workers > 1 时告警

## 运维清单（局域网）

1. 设置强 `LEAGENT_SECRET_KEY`（`openssl rand -hex 32`）
2. 优先使用 `ports: ["127.0.0.1:8000:8000"]`，或在前面加反向代理 + TLS
3. 打开 UI 一次并完成 **setup**（访问密码）
4. 可选：在管理后台 → Users 创建命名用户（`/api/v1/admin/users`）
5. 将 `LEAGENT_SECURITY_CORS_ALLOW_ORIGINS` 设为你的 UI origin(s)
