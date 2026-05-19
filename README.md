<p align="center">
  <img src="docs/assets/logo.svg" alt="LeAgent Logo" width="120" height="120">
</p>

<h1 align="center">LeAgent</h1>

<p align="center">
  <strong>本地优先的智能办公自动化平台 — 对话式 AI、可视化工作流、百余项工具，一处部署。</strong>
</p>

<p align="center">
  <a href="../../actions/workflows/ci.yml"><img src="../../actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="../../releases/latest"><img src="https://img.shields.io/github/v/release/vixues/LeAgent?display_name=tag&sort=semver&color=blue" alt="Latest Release"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776ab.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/React-19-61dafb.svg" alt="React 19">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-green.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen.svg" alt="PRs Welcome">
</p>

<p align="center">
  <a href="README_en.md">English</a>
</p>

<p align="center">
  <img src="docs/assets/screenshots/hero.png" alt="LeAgent 产品概览" width="720">
</p>

---

**LeAgent** 是可自托管的 LLM 自动化平台，将对话助手、拖拽式工作流、声明式规则、技能与各类集成整合在同一套栈里，无需再拼凑多款零散产品。

- **Agent 运行时** — 多轮对话、流式输出、工具调用、分层模型路由与提示词，以及情景 / 语义 / 程序性认知记忆
- **100+ 工具** — 文档、网页、数据、代码执行、数据库、Generative UI、编码项目等
- **可视化工作流** — ReactFlow 编辑器，支持 YAML 导出与模板；每个工具自动映射为带类型的工作流节点
- **多供应商 LLM** — 支持 DeepSeek、通义千问、OpenAI、Ollama、vLLM 等（当前以 DeepSeek 完成深度验证，推荐优先使用）
- **侧栏桌宠** — 可定制形象与背景、行走/跳跃动画与人格气泡；支持上传 PNG / SVG / GIF 或精灵图，并随聊天流式输出与会话状态联动
- **零配置起步** — 默认 SQLite，单容器 Docker 即可运行；可按需接入 PostgreSQL / Milvus

---

## 快速开始

### 本地开发（适合二次开发）

**环境要求：** git、[uv](https://docs.astral.sh/uv/)、Node.js 20+ 或 22+

```bash
git clone https://github.com/vixues/LeAgent.git
cd LeAgent
./start.sh                # 后端 :7860 + 前端 :5173
```

### Docker

```bash
cd LeAgent/deploy
cp .env.example .env      # 配置 LEAGENT_SECRET_KEY 与模型提供商密钥
docker compose up -d --build
```

API 文档：`http://localhost:8000/docs`

### 手动安装

```bash
# 后端
cd backend
uv sync --extra dev
uv run leagent init
uv run leagent app

# 前端（另开终端）
cd frontend
npm install && npm run dev
```

### 一键安装

```bash
curl -fsSL https://vixues.com.cn/install.sh | bash
```

### 桌面客户端（测试版，功能仍在完善）

各平台安装包随 GitHub Release 发布，下载即可使用，无需单独安装 Python、Node 或 Docker。

| 平台 | 下载 | 说明 |
| --- | --- | --- |
| **Windows 10/11（x64）** | [`LeAgent-Setup-*.exe`](../../releases/latest) | NSIS 安装包，自动创建桌面与开始菜单快捷方式 |
| **macOS（Apple 芯片）** | [`LeAgent-*-arm64.dmg`](../../releases/latest) | 未签名 — 安装后执行 `xattr -dr com.apple.quarantine /Applications/LeAgent.app` |
| **macOS（Intel）** | [`LeAgent-*.dmg`](../../releases/latest) | 同上，需处理 Gatekeeper 提示 |
| **Linux（x64）** | [`LeAgent-*.AppImage`](../../releases/latest) / [`LeAgent-*.deb`](../../releases/latest) | AppImage：`chmod +x` 后运行；`.deb`：`sudo dpkg -i` |

桌面版内置 Python 运行时与后端，安装后即可独立运行。

全部历史版本：**<https://github.com/vixues/LeAgent/releases>**

---

## 参与贡献

欢迎提交 Issue 与 Pull Request：

1. 较大改动或范围不明确的修改，请先开 Issue 讨论。
2. 请为涉及改动的部分运行测试（`cd backend && uv run pytest tests/ -v` / `cd frontend && npm run test`）。
3. 遵循 [`AGENTS.md`](AGENTS.md) 中的代码规范与 i18n 规则。

更多说明见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

---

## 许可证

Apache License 2.0 — 详见 [`LICENSE`](LICENSE)。
