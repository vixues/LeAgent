# 如何把微信接到自己的 Agent

> 一篇面向开源爱好者的通用技术分享：说明「个人微信 → 自建 Agent」这条链路到底怎么走，协议长什么样，哪些坑几乎人人会踩。  
> LeAgent 的实现可作为参考实现；文中思路同样适用于你自己的 Agent runtime。

| | |
|---|---|
| **受众** | 想给自建 Agent 加上 IM 入口、愿意读一点协议细节的开发者 |
| **协议** | 腾讯微信 **iLink Bot API**（个人微信 / ClawBot 能力） |
| **参考** | [协议说明](https://www.wechatbot.dev/en/protocol)、[Hermes Weixin 文档](https://hermes-agent.nousresearch.com/docs/zh-Hans/user-guide/messaging/weixin)、LeAgent `leagent/channels/weixin/` |

---

## 1. 先分清三种「微信」

很多人一上来搜「微信机器人」，会撞进三类完全不同的产品：

| 类型 | 典型场景 | 入站方式 | 身份 |
|------|----------|----------|------|
| **企业微信 (WeCom)** | 公司内部应用、群机器人 | 多为 **Webhook / 回调 URL**（要公网） | 企业应用 |
| **公众号 / 开放平台** | 服务号、客服消息 | 服务器 URL + Token 校验 | 公众号 / 开放平台 App |
| **个人微信 iLink Bot** | 扫码把 *个人账号* 接到 Agent | **HTTP 长轮询**（可不上公网） | iLink bot 身份（如 `…@im.bot`） |

本文只讲第三种：**用个人微信号扫码，把私信接到你自己的 Agent**。  
它和「企业微信出站机器人」不是一条路——LeAgent 里对应的是 `weixin`，而不是 `wechat_work`。

为什么很多人选 iLink：

- **无需公网 IP / 反向代理**就能收消息（桌面端、家里 NAS、本机开发都友好）
- 扫码绑定，配置路径短
- 文本可带 Markdown（标题、表格、代码块），媒体走加密 CDN

代价也很明确：扫码得到的是 **iLink bot 身份**，**普通微信群通常推不过来**；可靠场景基本是 **私信 (DM)**。这点不是你代码写错了，是平台侧身份限制。

---

## 2. 目标架构（通用模板）

无论框架叫 Cursor Agent、Hermes、还是自研 loop，接到微信时建议拆成三层：

```text
微信客户端
    │  (用户发私信 / 扫码登录)
    ▼
┌───────────────────────────────────────┐
│  Channel Adapter（通道适配器）         │
│  · QR 登录，保存 token / account_id   │
│  · 长轮询 getupdates                  │
│  · 维护 context_token                 │
│  · AES CDN 收发媒体                   │
│  · typing / 去重 / 分块               │
└──────────────────┬────────────────────┘
                   │ 标准化 InboundMessage
                   ▼
┌───────────────────────────────────────┐
│  Agent Bridge（Agent 桥）              │
│  · peer → session_id 映射             │
│  · 调用你的 think-act / run_loop      │
│  · 只把「最终回复」回推通道            │
└──────────────────┬────────────────────┘
                   │
                   ▼
              你的 Agent 内核
```

要点：

1. **通道适配器不要写业务逻辑**——只负责「微信 ↔ 结构化消息」。
2. **Agent 桥是薄的**：拼 prompt、选 agent、把终态文本/附件回填。
3. **不要把 stream_delta 直接刷到微信**——iLink 不能原地编辑气泡；半截字会刷屏。等一轮跑完再发（或按块智能分包）。

---

## 3. 协议速览：三阶段

官方与社区文档把协议拆成三段（Base：`https://ilinkai.weixin.qq.com`，CDN：`https://novac2c.cdn.weixin.qq.com/c2c`）：

### 3.1 登录：二维码状态机

```text
get_bot_qrcode  →  用户扫码  →  get_qrcode_status 轮询
                     wait → scanned → confirmed
                              ↘ expired（换新码）
```

成功时你会拿到：

- `bot_token`（后续一切业务请求的 Bearer）
- `account_id`（bot 账号）
- 可能返回不同于默认的 `baseurl`——**永远以返回值为准**

业务请求公共头大致为：

```http
Content-Type: application/json
AuthorizationType: ilink_bot_token
Authorization: Bearer <bot_token>
X-WECHAT-UIN: <base64(随机 uint32 的十进制字符串)>
```

正文里常带：

```json
{ "base_info": { "channel_version": "2.2.0" } }
```

### 3.2 消息：长轮询 + 发送

- **收**：`POST …/getupdates`，超时约 35s；服务端hold住直到有消息或超时。
- **游标**：`get_updates_buf` —— 第一次传 `""`，之后每次响应当不透明游标存盘，**重启后接着传**。
- **发**：`POST …/sendmessage`，每条回复必须带上该对话方的 `context_token`。

`context_token` 是整条链路最容易翻车的点：

| 规则 | 说明 |
|------|------|
| 入站必有 | 每条用户消息都带 `context_token` |
| 出站必回 | 回复必须 echo 该 peer 的最新 token |
| 按人缓存 | `key = (account_id, peer_user_id)` |
| 持久化 | 进程重启后仍要能回得上话 |
| 过期清掉 | `errcode = -14`（会话过期）后清缓存并重新扫码 |

没有它，消息要么发不出去，要么进错会话。

### 3.3 媒体：AES-128-ECB CDN

图片 / 视频 / 文件 / 语音在 CDN 上是 **密文**：

1. 入站：按 `encrypt_query_param` 下载 → 用消息里的 `aes_key` 解密  
2. 出站：本地随机 16 字节密钥 → PKCS7 填充 → AES-128-ECB 加密 → `getuploadurl` → CDN `upload` → `sendmessage` 带媒体引用  

`aes_key` 编码可能是：raw base64、base64(hex 字符串)、或 32 位 hex——解析时要兼容三种。  
另外对下载 URL 做 **SSR F 白名单**（只允许微信 CDN 域），避免被投毒去打内网。

---

## 4. 一条消息的生命周期

用伪代码把「用户说你好」串起来：

```text
[轮询] getupdates(sync_buf)
         │
         ├─ 更新 sync_buf 到磁盘
         ├─ msg_id 去重（建议 5 分钟滑动窗口）
         ├─ 跳过 bot 自己发的消息
         ├─ 解析 item_list → 文本 / 媒体
         ├─ 保存 context_token[peer]
         └─ enqueue(InboundMessage)

[消费] typing=start
         │
         ├─ Agent.run(session=uuid5(ns, "weixin:"+peer), prompt=text)
         ├─ 取最终 assistant 文本（不要边流边发）
         ├─ 按 ≤4000 字在段落/代码围栏边界拆分
         ├─ sendmessage(+ context_token) × N（块间短延迟防频控）
         └─ typing=stop
```

### 4.1 Session 怎么映射

微信 peer id 是字符串，你的 Agent 内核往往吃 UUID。常见做法：

```python
session_id = uuid5(NAMESPACE_DNS, f"weixin:{peer_user_id}")
```

同一微信用户永远落到同一会话，多轮上下文才能连续。  
不要每次 `uuid4()`——否则 Agent「失忆」。

### 4.2 访问策略

至少实现 DM 策略（群默认关掉更稳妥）：

| 策略 | 行为 |
|------|------|
| `open` | 任意人可私信（默认适合自用） |
| `allowlist` | 仅白名单 user id |
| `disabled` | 忽略私信 |

群策略再开也无妨，但要在日志里明确：**iLink bot 往往收不到普通群事件**，避免用户空调 `GROUP_POLICY`。

---

## 5. 最小可行实现清单

如果你从零做一个适配器，按这个清单打勾即可跑通私信 Agent：

| # | 能力 | 没有会发生什么 |
|---|------|----------------|
| 1 | QR 登录 + 持久化 token/account | 无法鉴权 |
| 2 | 长轮询 + sync buf 落盘 | 重启丢消息 / 重复位点 |
| 3 | context_token 落盘 | 无法可靠回复 |
| 4 | send_text + 分块 | 长回复失败或被截断难看 |
| 5 | typing（getconfig + sendtyping） | 体验「卡住」 |
| 6 | msg_id 去重 | 重复执行 Agent |
| 7 | `-14` 会话过期处理 | 静默死亡 |
| 8 | （可选）AES 媒体 | 只能纯文本 |

可选增强：热加载（UI 扫码成功后 **不重启进程** 就 `replace_channel` / 重启 poll task）、限流熔断、多实例 token 锁。

---

## 6. 参考实现：LeAgent 怎么落地

下面用 LeAgent 说明「同一套模板」如何落到工程里（路径便于跳读，不必捆绑框架）。

### 6.1 模块划分

```text
leagent/channels/weixin/
  client.py   # iLink HTTP：getupdates / sendmessage / typing / upload
  crypto.py   # AES-128-ECB + 多种 aes_key 解码
  media.py    # CDN 上下载
  store.py    # account / context_token / sync_buf
  login.py    # QR 会话、状态归一化、凭据落盘
  channel.py  # BaseChannel：轮询入队、consume、回发
leagent/channels/agent_bridge.py
              # ChannelMessage → AgentRuntime.stream → 终态 ChannelEvent
```

通道层 **只生产/消费** `ChannelMessage`；桥接层调用统一内核 `AgentRuntime`（最终进 `run_loop`）。

### 6.2 启动与热加载

- 进程启动时：若 `config.yaml` 里 `channels.weixin.enabled` 且凭据齐全 → `ensure_weixin_running()`
- UI 扫码确认后：API `POST/GET …/channels/weixin/login/*` 写凭据 → 同一方法 **热启 poller**，无需重启前后端

对开源项目这很关键：**桌面用户厌恶每次改配置就重启整栈**。

### 6.3 你也可以只借鉴协议层

若你已有 Agent，不必 fork 整个项目。可复用思路：

1. 抄协议常量与错误码语义（`-14`、`context_token`、长轮询游标）  
2. 把适配器接到你自己的 `async for event in agent.stream(...)`  
3. 会话映射用确定性 ID  

Hermes Agent 的 Weixin 适配器、以及 [wechatbot.dev 协议页](https://www.wechatbot.dev/en/protocol) 是很好的交叉对照材料。

---

## 7. LeAgent 里怎么用（实操）

### 7.1 前端扫码（推荐）

1. 启动 LeAgent（`./start.sh`）  
2. 打开 **消息通道**  
3. 点 **扫码连接** → 微信扫码 → 手机确认  
4. 面板显示「运行中」后，直接给 bot 发私信即可  

确认成功即热启长轮询，**不必**再重启服务。

### 7.2 CLI

```bash
cd backend
uv run leagent channels login weixin
# 若服务已在跑：到 UI 点「启动监听」，或调用 POST /api/v1/channels/weixin/start
```

凭据位置：

- `$LEAGENT_HOME/weixin/accounts/<account_id>.json`
- `$LEAGENT_HOME/weixin/accounts/<account_id>.context-tokens.json`
- `$LEAGENT_HOME/config.yaml` → `channels.weixin`

### 7.3 相关环境变量（可选覆盖）

| 变量 | 含义 |
|------|------|
| `WEIXIN_ACCOUNT_ID` / `WEIXIN_TOKEN` | 凭据 |
| `WEIXIN_DM_POLICY` | `open` / `allowlist` / `disabled` |
| `WEIXIN_ALLOWED_USERS` | DM 白名单 |
| `WEIXIN_GROUP_POLICY` | 默认建议 `disabled` |
| `WEIXIN_BASE_URL` | 覆盖 iLink base（一般不必） |

---

## 8. 安全与运维备忘

- **Token 等价于账号会话**：文件权限建议 `0600`，勿提交到 git。  
- **单 token 单 poller**：多个网关抢同一 token 会互相踢或启动失败；多机部署要么 sticky，要么独立账号。  
- **会话过期**：出现 `-14` 时清空 token 状态并提示重新扫码，不要死循环狂打。  
- **媒体 SSRF**：外链只允许微信 CDN 域名。  
- **不要把 Agent 的工具执行日志全文怼进微信**：频道适合「人话结果」；细节回你自己的 Web UI / Trace。

---

## 9. 常见问题

| 现象 | 排查 |
|------|------|
| 扫码成功但不回消息 | 看 poller 是否 `running`；是否 `-14`；context_token 是否落盘 |
| 群里 @ 没反应 | 大概率 iLink **根本不下发**群事件；别空调 group policy |
| 媒体失败 | 是否安装 `cryptography`；CDN 是否可达；aes_key 解析 |
| 重复回复 | 去重窗口；是否双实例在同 token 上轮询 |
| 回复进错人 | context_token 是否按 peer 隔离、有无交叉污染 |

---

## 10. 延伸阅读

- 协议：<https://www.wechatbot.dev/en/protocol>  
- Hermes 用户指南（中文）：<https://hermes-agent.nousresearch.com/docs/zh-Hans/user-guide/messaging/weixin>  
- LeAgent 教程渠道章节：[`docs/tutorial_zh.md`](../tutorial_zh.md)（个人微信小节）  
- 执行拓扑（Agent 内核入口）：[`docs/technical/execution-topology.md`](../technical/execution-topology.md)  
- 本仓库实现：`backend/leagent/channels/weixin/`、`backend/leagent/channels/agent_bridge.py`

---

## 11. 小结

把微信接到 Agent，本质不是「调一个 SDK 完事」，而是：

1. 理解 **iLink = 长轮询 + context_token + 加密 CDN**；  
2. 用一层 **瘦适配器** 把 IM 事件变成你 Agent 认识的输入；  
3. 用一层 **桥** 把 Agent 终态变成合规出站消息；  
4. 接受产品边界：**个人微信 iLink 优先服务私信**。

把这四层想清楚，换任何 Agent 框架都只是换「桥」后面的那一截内核。
