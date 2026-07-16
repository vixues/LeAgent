<p align="center">
  <img src="docs/assets/logo.svg" alt="LeAgent Logo" width="120" height="120">
</p>

<h1 align="center">LeAgent</h1>

<p align="center">
  <strong>能成事之开源桌面智能体 —— 一栈可自设，统能自筹谋而自纠之 Agent、智能可视之流程、Generative UI 与百余离线工具。</strong>
</p>

<p align="center">
  <a href="../../actions/workflows/ci.yml"><img src="../../actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="../../releases/latest"><img src="https://img.shields.io/github/v/release/vixues/LeAgent?display_name=tag&sort=semver&color=blue" alt="Latest Release"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776ab.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/React-19-61dafb.svg" alt="React 19">
  <img src="https://img.shields.io/badge/Database-SQLite%20%7C%20PostgreSQL-003b57.svg" alt="SQLite / PostgreSQL">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-green.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen.svg" alt="PRs Welcome">
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README_zh.md">简体中文</a> ·
  <a href="./docs/tutorial_zh.md">使用教程</a> ·
  <a href="AGENTS.md">贡献者指南</a> ·
  <a href="https://github.com/vixues/LeAgent/releases">版本发布</a>
</p>

<p align="center">
  <img src="docs/assets/screenshots/hero.png" alt="LeAgent 之概貌" width="720">
</p>

---

> 此卷以**汉文**述之，取其简严雅正；若涉术语之细，仍以 [English](README.md) 与 [简体中文](README_zh.md) 二本为准。

**LeAgent** 者，开源桌面之智能体也——非徒能言，乃能成事。异于云端之问答、专于代码之 CLI，LeAgent 合众家所分之三长于一身：于一「思—行」之环中**自筹谋、调工具、且自纠其失**之流式运行时；由智能体**亲为擘画、运行而迭善**之 ReactFlow DAG，是谓**智能可视之流程**（且每一工具皆自成带型之节点）；又有 Generative UI 之能，使 KPI 之版、幻灯之集、图廊之属等**可即时交互之界面，径流于会话之中**。内置**百余离线工具**（文牍、网页、数据、代码、数据库、媒体、游戏美术之生成），兼具声明式规则引擎、Agent Skills 与 Model Context Protocol；**默认无外部依赖**（SQLite、单进程）即可行于本机。用户可自携模型密钥，亦可接本地 Ollama / vLLM 端点，**全程离线**而用之。

其为重私密、可改造、可自部署者而作：非用户自将供应商指向远端 API，则文牍、会话与凭据，皆不出本机。

## 核心之长

- **Agent 运行时** —— 多轮会话、Token 流式输出、工具调用、模型分层路由、提示分层构造，并具情景 / 语义 / 程序三藏之认知记忆。`QueryEngine` 以一「思—行」之环统摄会话与后台任务；持久检查点使回合可止可复。
- **百余离线工具** —— 文牍处理、网研检索、数据治理、代码执行、数据库、Generative UI、图表、媒体与代码项目，皆入一统之工具体系（详见下之[工具目录](#工具目录)）。
- **可视流程** —— ReactFlow 编辑器可导 YAML、复用模板，并为每一工具自生带型节点。引擎按就绪批次调度，独立分支并行，重试、退避与超时之制一以贯之。
- **Agent Skills** —— 合 [Agent Skills v1.0](https://agentskills.my/specification) 之 `SKILL.md` 技能包，渐进披露，按需加载；可用内置技能，自链接或封包安装，亦可接 HTTP 技能注册表。
- **论文模式** —— 启一 PDF，则智能体化为据文献而论之研究助理：析结构纲目，撮章节与全文之要，抽参考文献与 LaTeX 公式，并译选区文句。阅读器标签页与 Agent 工具同源；文本抽取可全然离线。（[指南](docs/research-paper-mode.md)）
- **Generative UI** —— 智能体可流式输出声明式 UI 树（KPI 榜、幻灯集、画廊、步骤），内联呈于会话，并可导为 PDF 或 PPTX。
- **游戏美术资产流水线** —— 一等可组合之生成节点（图像 / 视频 / 三维网格 / VFX），具带型媒体插槽、质量门与有界自纠环，且于画布中预览；无凭据亦可端到端离线运行。（[文档](backend/docs/workflow-engine/art-asset-nodes.md)）
- **多供应 LLM** —— 兼容 DeepSeek、通义千问（DashScope）、OpenAI、Anthropic、Azure OpenAI、Ollama 与 vLLM，具成本分层路由与故障转移。DeepSeek 之集成验之最详，可先试之。
- **侧栏桌宠** —— 形象可定，具行走、跳跃之态与人格气泡，随会话流与状态而动；可上传 PNG / SVG / GIF 或精灵图。
- **集成能力** —— MCP 服务器、入站 Webhook、定时 Cron、出站通道（IM / 控制台）及声明式 YAML 规则引擎，皆可纳入自动化链路。
- **零配置起步** —— 默认 SQLite 与单容器 Docker 即可运行；需扩展时，可接 PostgreSQL 与 Milvus（向量记忆）。

## 可用以何事

LeAgent 乃成器之台，非草创之架也。下列诸能，皆开箱即用、互相贯通；默认亦可离线而行。

- **办公自动化** —— 指向发票、契约、报表所在之目录，系统可行 OCR、分类、抽取结构化字段入 Excel，并于一回合内生成排版妥帖之 Word 或 PPTX 摘要。
- **研究与简报** —— 跨 DuckDuckGo / SearXNG / Bing 搜索，抓取并下载来源，汇为具引用、图表与 KPI 榜之 PDF 报告。
- **数据分析** —— 载入 CSV/Excel 或查询数据库，清洗、合并、聚合，运行 SQL 与向量检索，并以图表叙其所得。
- **编码协作** —— 由模板立项，跨目录修订文件，经预览代理运行实时开发服务，并于隔离沙箱中执行代码。
- **游戏美术制作** —— 化文字简报为图像、视频、三维网格与 VFX 精灵图；节点图依质量门自校，导出可入 Unity / Unreal / Godot 之资产包。
- **实时交互答复** —— 将 Generative UI（KPI 榜、幻灯、画廊、步骤）流入会话，亦可导为 PDF 或 PPTX。
- **常驻自动化** —— 由 Cron 调度，受入站 Webhook 触发，分发至 IM 通道（钉钉 / 飞书 / 企业微信），并以声明式 YAML 规则约束其行。

## 架构

LeAgent 由异步 Python（FastAPI）后端与 React 19 单页应用而成，以模块化单体（modular monolith）封装。后端循严格之单向分层领域模型 —— **File → Code → Project**，立于统一持久层上；凡请求自会话、SDK、后台任务、子智能体、流程节点而入，每一 Agent 回合皆汇于**同一「思—行」内核**。

```text
LeAgent/
├── backend/                 # FastAPI 后端（Python 3.11+，uv 所管）
│   └── leagent/
│       ├── agent/           # QueryEngine 编排、规划、子智能体
│       ├── sdk/             # 版本化之公共 Agent SDK（运行时、内核、协议）
│       ├── api/             # FastAPI 路由（v1 + 孵化之 v2）
│       ├── llm/             # LLM 之服、供应、传输、流式、生成
│       ├── tools/           # 十三类下之百余工具
│       ├── workflow/        # 流程引擎、节点、美术资产流水线、模板
│       ├── context/         # 源驱动、按相关门控之提示组装
│       ├── prompts/         # 分层之 PromptBuilder、注册、范式
│       ├── memory/          # 情景 / 语义 / 程序之 Agent 记忆
│       ├── skills/          # Agent Skills v1.0 之加载与注册
│       ├── rules/           # 声明式 YAML 规则引擎
│       ├── mcp/             # Model Context Protocol
│       ├── file/ code/ project/   # 分层之 file → code → project 领域模型
│       ├── db/              # 持久：引擎、SQLModel 之模、仓储
│       └── services/        # DB、鉴权、会话、gen-ui、cron 等
├── frontend/                # React 19 + TypeScript SPA（Vite、Zustand、React Query）
├── desktop/                 # Electron 之壳（内置 Python 运行时）
├── deploy/                  # Dockerfile + 仅 SQLite 之 Compose
├── config/                  # 演示流程 + 流程模板
├── docs/                    # 架构、指南、部署之文
└── start.sh / start.ps1     # 开发编排（uv + npm）
```

完整子系统图见 [`AGENTS.md`](AGENTS.md)；Agent 循环 / 流程引擎之状态契约，见 [`docs/technical/execution-topology_zh.md`](docs/technical/execution-topology_zh.md)。

## 工具目录

每一工具皆自动显为带型流程节点，故 Agent 所能调用者，皆可编入可视化流程。

| 类 | 所涵 |
| --- | --- |
| **文牍** | 读写 Word、Excel、PPTX、PDF；OCR；分类；归档；文本处理 |
| **网页** | 搜索（DuckDuckGo / SearXNG / Bing）、抓取、图像与原生媒体下载 |
| **数据** | 清洗、合并、校验、转换、聚合、SQL 与向量检索 |
| **代码** | 进程内沙箱脚本，及子进程代码执行智能体 |
| **数据库** | 面向托管数据库之 Schema 感知查询 |
| **生成** | Word / Excel / PPTX / PDF / 报告 / 清单 / 模板填充生成器 |
| **Canvas / GenUI** | 流式而出、增量而易声明之 UI 树；发布画布 |
| **图表与图像** | 图表之生与图像之治 |
| **媒体** | 图 / 影 / 三维 / 音 之生成后端 |
| **技能** | 发现、安装与调用 Agent Skills |
| **流程** | 于一 Agent 回合内保存、运行与检查流程 |
| **集成** | MCP、Webhook、通道与外部服务调用 |
| **杂项** | Cron、任务、规则匹配、目录、文本切分、桌宠气泡等 |

## 速始

### 本地开发（宜二次开发）

**所需：** git、[uv](https://docs.astral.sh/uv/)、Node.js 20+ 或 22+

```bash
git clone https://github.com/vixues/LeAgent.git
cd LeAgent
./start.sh                # 后端 :7860 + 前端 :5173
```

开发编排器以 `uv` 同步 Python 环境、安装前端依赖，并（除非显式略之）安装网页工具所需之 Playwright Chromium。

### Docker

```bash
cd LeAgent/deploy
cp .env.example .env      # 配 LEAGENT_SECRET_KEY 与至少一供应商密钥
docker compose up -d --build
```

API 与交互式文档在 `http://localhost:8000/docs`。默认镜像为单一 SQLite 容器；可选叠层可添本地 GPU vLLM 服务（`docker-compose.vllm.yml`）。

### 手动安装

```bash
# 后端
cd backend
uv sync --extra dev
uv run leagent init
uv run leagent app

# 前端（另开一终端）
cd frontend
npm install && npm run dev
```

### 一键安装

```bash
curl -fsSL https://vixues.com.cn/install.sh | bash
```

### 配置

至少配置一供应商密钥（以环境变量，或于 Web UI 之 **设置 → 环境密钥** 填之；后者写入 `~/.leagent/.env`）。常用项如下：

| 变量 | 用途 |
| --- | --- |
| `LEAGENT_SECRET_KEY` | 用以签名 URL 与会话加密之应用密钥（`openssl rand -hex 32`） |
| `DEEPSEEK_API_KEY` | DeepSeek 供应商 —— 自动别名为 `tier1`（推理）/ `tier2`（快速） |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `DASHSCOPE_API_KEY` | 其余云端供应商 |
| `VLLM_ENDPOINT` / `LLM_OLLAMA_ENDPOINT` | 本地 / 自托管 OpenAI 兼容推理端点 |
| `DATABASE_URL` | 自 SQLite 易为 PostgreSQL |
| `LEAGENT_DEBUG` | 启调试日志 |

完整带注清单，见 [`deploy/.env.example`](deploy/.env.example)。

## 桌面客户端（测试版，功能尚在完善）

各平台安装包随 GitHub Release 发布，下载即用，无须另装 Python、Node 或 Docker；包内自携 Python 运行时与后端。

| 平台 | 下载 | 说明 |
| --- | --- | --- |
| **Windows 10/11（x64）** | [`LeAgent-Setup-*.exe`](../../releases/latest) | NSIS 安装包，自动置桌面与开始菜单快捷方式 |
| **macOS（Apple 芯片）** | [`LeAgent-*-arm64.dmg`](../../releases/latest) | 未签名 —— 安装后执行 `xattr -dr com.apple.quarantine /Applications/LeAgent.app` |
| **macOS（Intel）** | [`LeAgent-*.dmg`](../../releases/latest) | 同上，需处理 Gatekeeper 提示 |
| **Linux（x64）** | [`LeAgent-*.AppImage`](../../releases/latest) / [`LeAgent-*.deb`](../../releases/latest) | AppImage：`chmod +x` 后运行；`.deb`：`sudo dpkg -i` |

历代版本总览：**<https://github.com/vixues/LeAgent/releases>**

## 技术栈

| 层 | 技术 |
| --- | --- |
| **后端** | Python 3.11+、FastAPI、Uvicorn/Gunicorn、SQLModel + Alembic、Pydantic v2、异步 I/O、OpenTelemetry |
| **前端** | React 19、TypeScript、Vite、Zustand、TanStack Query、ReactFlow、i18next（zh-CN / en-US / 汉文） |
| **桌面** | Electron（ESM 主进程）、内置 Python 后端 |
| **数据** | SQLite（默认）、PostgreSQL（可选）、Milvus（可选向量记忆） |
| **工具链** | uv（Python）、npm（前端）、Playwright、black + ruff、ESLint |

## 运维

- **端口。** 本地开发时，后端监听 `:7860`，Vite 前端监听 `:5173`（`start.sh`）；Docker 镜像将 API 发布于 `:8000`。
- **持久与备份。** 运行状态皆居于 `LEAGENT_HOME`：SQLite 数据库（WAL 模式）、上传工作目录、知识库与代码项目目录树。全量备份须同时保存数据库 **与** 此目录。
- **横向扩展。** 默认单进程 / 单 worker 适合 SQLite（单写入者）。欲扩展，则以 `DATABASE_URL` 切换 PostgreSQL，并于前置层保持粘性会话（in-process 执行注册表与事件总线皆按 worker 隔离）。Milvus 为可选，仅司向量记忆召回。
- **可观测性。** 结构化 JSON 日志（structlog）、配置 OTLP 后输出 OpenTelemetry Span，并有 Prometheus 流程 / 质量直方图。交互式 API 文档在 `/docs`；设 `LEAGENT_DEBUG=true` 可启详细追踪。

## 文档

完整文档居于 [`docs/`](docs/README.md) —— 宜自[架构总览](docs/technical/architecture.md)始。

- **由此而始** —— [架构总览](docs/technical/architecture.md) · [使用教程](docs/tutorial_zh.md)
- **运行时** —— [执行拓扑](docs/technical/execution-topology_zh.md) · [Agent 运行时](docs/technical/agent-runtime_zh.md) · [Agent SDK](docs/technical/agent_sdk_zh.md)
- **诸能** —— [论文模式](docs/research-paper-mode.md) · [流程引擎](backend/docs/workflow-engine/overview.md) · [美术资产节点](backend/docs/workflow-engine/art-asset-nodes.md) · [GenUI 标准](docs/technical/genui-rendering-standard.md)
- **工具与模型** —— [工具参数约定](docs/technical/tool-parameters_zh.md) · [DeepSeek](docs/deepseek-guide_zh.md) · [DashScope](docs/dashscope-guide_zh.md) · [自定义模型](docs/technical/custom-models_zh.md)

## 参与贡献

欢迎提交 Issue 与 Pull Request：

1. 凡较大改动，或范围未明者，请先开 Issue 议定。
2. 请为所涉之处运行测试（`cd backend && uv run pytest tests/ -v` / `cd frontend && npm run test`）。
3. 请遵 [`AGENTS.md`](AGENTS.md) 之代码规范与 i18n 之则（每新增 UI 文案，皆须同见于 `zh-CN` 与 `en-US` 二词条；界面汉文见 [`docs/lzh-style-guide.md`](docs/lzh-style-guide.md)）。

## 界面汉文译则

界面第三语种「汉文」之译法、术语表与贡献清单，见 [`docs/lzh-style-guide.md`](docs/lzh-style-guide.md)。

更多说明见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，社区准则见 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。

## 许可

Apache License 2.0 —— 详见 [`LICENSE`](LICENSE)。
