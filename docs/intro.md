# LeAgent：真正完成工作的开源桌面 AI 智能体

<p align="center">
  <strong>将自主规划与纠错、智能化可视工作流、Generative UI 和 100+ 工具整合进一套可本地运行、可私有化部署的智能体平台。</strong>
</p>

## LeAgent 是什么

LeAgent 是一款开源桌面 AI 智能体。它不止回答问题，还能围绕目标自主规划、调用工具、检查结果并修正执行过程，真正完成文档处理、资料研究、数据分析、代码开发和内容生成等任务。

与只提供对话界面的云端助手或专注代码操作的 CLI 不同，LeAgent 将三类能力统一在一个产品中：

1. **可自我纠错的 Agent 运行时**  
   在统一的「思考—行动」循环中完成规划、工具调用、结果检查和恢复。聊天、后台任务、子智能体与工作流节点共享同一执行内核。

2. **由智能体参与设计的可视工作流**  
   智能体可以创建、运行和迭代优化 ReactFlow DAG。每个注册工具都会自动成为带类型的工作流节点，无需额外编写胶水代码。

3. **直接进入对话的 Generative UI**  
   KPI 看板、幻灯片、画廊和步骤卡等交互界面可以实时流式渲染在聊天中，并可导出为 PDF 或 PPTX。

LeAgent 默认使用 SQLite 和单进程架构，本地启动不依赖外部数据库或消息队列。你可以接入 DeepSeek、通义千问、OpenAI、Anthropic、Azure OpenAI 等云端模型，也可以连接本地 Ollama 或 vLLM，在模型与工具均支持的前提下构建完全离线的工作环境。

## 为什么选择 LeAgent

### 数据由你掌控

文档、会话、凭据和任务状态默认保存在本机。只有当你主动配置远程模型或外部服务时，相关请求才会发送到对应供应商。对于需要更高数据控制能力的个人、团队和组织，LeAgent 可以部署在自己的设备或基础设施中。

### 从对话到执行，而不止生成文字

LeAgent 内置 100+ 工具，覆盖文档、网页、数据、代码、数据库、图表、媒体、工作流和系统集成。智能体可以读取输入、执行操作、生成文件，并把结果作为可预览、可下载的产物返回。

### 自动化能力可以复用

一次对话中验证有效的任务过程，可以进一步沉淀为可视工作流、定时任务、规则或 Agent Skill。工作流支持并发分支、重试与退避、节点超时，以及可持久化的暂停和恢复。

### 从本地体验平滑走向团队部署

默认配置适合个人电脑快速体验；需要扩展时，可以切换到 PostgreSQL，并按需接入 Milvus 提供向量记忆。LeAgent 同时提供 Web 应用、Electron 桌面客户端、HTTP API、CLI 和版本化 Agent SDK。

## 主要能力

### Agent 运行时与记忆

- 支持多轮会话、Token 流式输出、工具调用和子智能体委派。
- 结合 ReAct 式工具循环与 plan-and-execute 执行方式。
- 通过持久化检查点暂停等待用户输入，并从中断位置恢复。
- 提供情景、语义和程序性三类记忆，兼顾历史回合、抽取事实和工具使用经验。
- 采用分层、按相关性门控的提示词组装，控制上下文规模并减少无关策略干扰。
- 支持按成本分层的模型路由和跨供应商故障转移。

### 文档与办公自动化

- 读取和生成 Word、Excel、PPTX 与 PDF。
- 支持 OCR、文档分类、文本提取、压缩包处理和模板填充。
- 可将原始资料整理为报告、清单、表格或演示文稿。
- 文件通过统一文件层管理，并提供签名的预览与下载地址。

### 研究论文模式

打开 PDF 后，LeAgent 可以围绕论文内容完成：

- 文档结构与大纲提取；
- 章节摘要和全文摘要；
- 参考文献与 LaTeX 公式提取；
- 选区翻译；
- 基于原文内容的分析与问答。

PDF 文本提取可在本地完成。

### 数据分析与代码执行

- 处理 CSV、Excel 和结构化数据，完成清洗、合并、校验、转换与聚合。
- 执行 SQL 查询和向量检索，并生成图表解释结果。
- 提供面向轻量脚本的进程内受限沙箱，以及面向复杂任务的子进程执行环境。
- 支持创建编码项目、跨目录编辑文件、运行开发服务器和预览应用。

### 可视工作流

- 使用 ReactFlow 编辑 DAG，并支持工作流模板与 YAML 导出。
- 自动将注册工具提升为 `Tool.<name>` 类型节点。
- 按就绪批次调度节点，并发执行相互独立的分支。
- 集中处理重试、退避、超时和运行状态持久化。
- 同一执行器支撑已保存流程、聊天步骤卡、定时任务和智能体生成的工作流。

### Generative UI

智能体可以流式生成声明式 UI，并在对话中持续增量更新。适合呈现：

- KPI 与指标看板；
- 幻灯片与叙事型报告；
- 图片或资产画廊；
- 多步骤任务进度；
- 需要用户查看或操作的交互式结果。

### 游戏美术资产流水线

LeAgent 提供可组合的图像、视频、3D 网格、VFX 和音频生成能力。工作流可通过质量门控检查结果，并在有界循环中根据反馈重新生成，最终导出面向 Unity、Unreal 或 Godot 的资产包。

生成服务支持重试、故障转移和确定性的离线兜底后端。离线后端主要用于无凭据演示与流程验证；实际生成质量取决于所配置的模型或媒体服务。

### Skills、MCP 与自动化集成

- 支持 Agent Skills v1.0 `SKILL.md` 技能包，可按需发现、安装和加载。
- 可通过 Model Context Protocol 连接外部工具服务器。
- 支持入站 Webhook、Cron 定时任务和后台任务。
- 可向钉钉、飞书、企业微信及控制台等渠道发送结果。
- 使用声明式 YAML 规则为自动化流程增加匹配条件与行为约束。

### 桌面体验

Electron 桌面客户端内置 Python 运行时和后端，安装后无需另外准备 Python、Node.js 或 Docker。侧栏桌宠可使用 PNG、SVG、GIF 或精灵图，并通过动作和气泡反馈聊天与会话状态。

桌面客户端目前仍处于测试阶段。Windows 10/11（x64）提供 NSIS 安装包；macOS 提供 Apple 芯片和 Intel 版本的 DMG，目前未签名，安装后可能需要处理 Gatekeeper 隔离属性；Linux（x64）提供 AppImage 与 DEB，其中 AppImage 需要添加可执行权限。各平台的实际安装包和支持情况以 GitHub Releases 页面为准。

## 工具目录

每个工具都会自动暴露为带类型的工作流节点，因此智能体能够调用的能力，也可以直接编排进可视化流程。

- **文档工具**：读写 Word、Excel、PPTX 和 PDF，支持 OCR、分类、压缩包与文本处理。
- **网页工具**：通过 DuckDuckGo、SearXNG 或 Bing 搜索，抓取网页并下载图片和原生媒体。
- **数据工具**：清洗、合并、校验、转换和聚合数据，执行 SQL 与向量检索。
- **代码工具**：运行受限的进程内脚本，以及面向复杂任务的子进程代码执行智能体。
- **数据库工具**：依据数据库 Schema 执行查询。
- **生成工具**：生成 Word、Excel、PPTX、PDF、报告、清单并完成模板填充。
- **Canvas 与 GenUI 工具**：流式生成、增量更新和发布声明式 UI。
- **图表与图像工具**：生成图表并完成常见图像处理。
- **媒体工具**：接入图像、视频、3D、VFX 和音频生成后端。
- **技能工具**：发现、安装和调用 Agent Skills。
- **工作流工具**：在智能体回合内保存、运行和检查工作流。
- **集成工具**：连接 MCP、Webhook、消息渠道与外部服务。
- **实用工具**：管理 Cron、后台任务、规则匹配、文件夹、文本切分和桌宠气泡等能力。

## 典型使用场景

### 办公资料批处理

把发票、合同或报告交给智能体，由它完成 OCR、分类和字段提取，将结构化结果写入 Excel，再生成 Word 或 PPTX 汇总。

### 研究与行业简报

通过 DuckDuckGo、SearXNG 或 Bing 搜索资料，抓取并整理来源，生成包含引用、图表和关键指标的 PDF 报告。

### 数据分析

加载 CSV、Excel 或数据库数据，完成清洗、合并、聚合和 SQL 查询，再用图表与自然语言说明结论。

### 编码与应用原型

从模板创建项目，编辑代码并运行开发服务器；也可以让智能体生成交互式页面，在预览环境中快速验证想法。

### 持续运行的业务自动化

使用 Cron 定时执行任务，以 Webhook 触发流程，将结果发送到 IM 渠道，并通过规则控制执行条件。

## 技术架构

LeAgent 由异步 Python 后端和 React 19 前端组成，以模块化单体形式交付。后端遵循 **File → Code → Project** 的单向分层领域模型，并以统一持久化层保存会话、检查点和工作流状态。

所有智能体入口最终汇聚到同一个执行内核：

```text
入口      HTTP/SSE · WebSocket · Cron · 后台任务 · GenUI
  │
  ▼
运行门面  ServiceManager.runtime_context · AgentRuntime · WorkflowService
  │
  ▼
执行内核  run_loop → QueryEngine → ToolExecutor
  │
  ▼
持久状态  TieredSessionStore · CheckpointStore · WorkflowStateStore
  │
  ▼
可观测性  EventManager · OpenTelemetry · Prometheus
```

这一设计保证聊天、SDK 调用、后台任务、子智能体和工作流 Agent 节点遵循一致的执行、恢复与观测语义。

## 支持的模型与部署方式

LeAgent 支持以下模型接入方式：

- **DeepSeek**：当前验证最充分，适合作为首次使用的默认选择；配置密钥后可自动映射为 `tier1` 推理层和 `tier2` 快速层；
- **通义千问（DashScope）**：支持思考与搜索相关能力；
- **OpenAI、Anthropic、Azure OpenAI**：接入相应云端模型；
- **Ollama、vLLM**：连接本地或自托管的 OpenAI 兼容推理服务。

模型是否能够完全离线运行，取决于所选模型端点以及任务是否调用网页搜索、远程媒体生成等外部服务。

数据层默认使用 SQLite。团队或多实例部署可以通过 `DATABASE_URL` 切换到 PostgreSQL；Milvus 是可选组件，仅用于增强向量记忆召回。默认 SQLite 部署应保持单 worker。

## 快速开始

### 本地开发

环境要求：Git、uv 和 Node.js 20+ 或 22+。

```bash
git clone https://github.com/vixues/LeAgent.git
cd LeAgent
./start.sh
```

启动后，后端默认监听 `http://localhost:7860`，前端开发服务器默认监听 `http://localhost:5173`。

`start.sh` 会使用 `uv` 同步 Python 环境、安装前端依赖，并在未显式跳过时安装网页工具所需的 Playwright Chromium。

### Docker

```bash
git clone https://github.com/vixues/LeAgent.git
cd LeAgent/deploy
cp .env.example .env
docker compose up -d --build
```

请在 `.env` 中设置 `LEAGENT_SECRET_KEY`，并配置至少一个云端模型密钥或可用的本地模型端点。Docker 默认发布 API 到 `http://localhost:8000`，交互式接口文档位于 `http://localhost:8000/docs`。

默认镜像使用单容器 SQLite 部署；如需本地 GPU 推理，可以使用项目提供的 vLLM Compose 叠加配置。

### 手动启动

```bash
# 后端
cd backend
uv sync --extra dev
uv run leagent init
uv run leagent app

# 前端（另开终端）
cd frontend
npm install
npm run dev
```

### 一键安装

```bash
curl -fsSL https://vixues.com.cn/install.sh | bash
```

### 常用配置

- `LEAGENT_SECRET_KEY`：签名 URL 与会话加密所需的应用密钥；
- `DEEPSEEK_API_KEY`：DeepSeek 模型密钥；
- `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`DASHSCOPE_API_KEY`：其他云端模型密钥；
- `VLLM_ENDPOINT`、`LLM_OLLAMA_ENDPOINT`：本地或自托管模型端点；
- `DATABASE_URL`：将持久化层从 SQLite 切换为 PostgreSQL；
- `LEAGENT_HOME`：数据库、上传文件、知识库和编码项目等本地状态的根目录；
- `LEAGENT_DEBUG`：启用详细调试日志。

完整配置项及注释位于 `deploy/.env.example`。

## 技术栈

- **后端**：Python 3.11+、FastAPI、Uvicorn/Gunicorn、SQLModel、Alembic、Pydantic v2、异步 I/O 与 OpenTelemetry。
- **前端**：React 19、TypeScript、Vite、Zustand、TanStack Query、ReactFlow 与 i18next。
- **桌面端**：Electron ESM 主进程，以及随客户端分发的 Python 后端运行时。
- **数据层**：默认使用 SQLite，可选 PostgreSQL；Milvus 作为可选的向量记忆后端。
- **开发工具链**：uv、npm、Playwright、black、ruff 与 ESLint。

## 运行与维护

- **端口**：本地开发时，后端默认使用 `7860`，Vite 前端默认使用 `5173`；Docker 镜像默认将 API 发布到 `8000`。
- **持久化**：SQLite 数据库、上传文件、知识库和编码项目等状态保存在 `LEAGENT_HOME` 下。
- **备份**：完整备份不仅需要复制数据库，还应同时备份 `LEAGENT_HOME` 中的文件目录。
- **扩展**：SQLite 适合默认的单进程、单 worker 模式。多 worker 部署应切换到 PostgreSQL 并配置粘性会话，因为执行注册表和事件总线目前按进程隔离。
- **可观测性**：系统提供 structlog 结构化日志；配置 OTLP 端点后可输出 OpenTelemetry Span，并可采集工作流与质量相关的 Prometheus 指标。
- **调试**：交互式 API 文档位于 `/docs`，设置 `LEAGENT_DEBUG=true` 可以启用更详细的日志。

## 开源与扩展

LeAgent 采用 Apache License 2.0 发布，适合学习、研究、二次开发和自托管部署。项目提供清晰的扩展边界：

- 新工具只需实现统一工具接口，系统会自动生成对应工作流节点；
- 新模型供应商可以接入 LLM Provider 与媒体生成服务；
- 新能力可以封装为 Agent Skill；
- 外部系统可通过 HTTP API、Webhook、MCP、CLI 或 Agent SDK 集成。

欢迎通过 Issue 和 Pull Request 参与项目。较大改动或范围不明确的修改应先通过 Issue 讨论；提交代码前应运行涉及模块的测试，并遵守 `AGENTS.md`、`CONTRIBUTING.md` 和前端国际化规则。每个新增 UI 文案都必须同时提供 `zh-CN` 与 `en-US` 词条。

---

LeAgent 的目标不是把更多功能堆进聊天框，而是让模型、工具、工作流和交互界面围绕同一个任务协同工作，让 AI 从“给出建议”走向“交付结果”。
