# LeAgent 教程

从安装到构建第一个自动化工作流的全面指南。

## 目录

1. [简介](#简介)
2. [安装](#安装)
3. [快速开始](#快速开始)
4. [聊天界面](#聊天界面)
5. [构建工作流](#构建工作流)
6. [使用工具](#使用工具)
7. [创建规则](#创建规则)
8. [渠道集成](#渠道集成)
9. [API 使用](#api-使用)
10. [进阶主题](#进阶主题)

---

## 简介

LeAgent 是一个本地优先的智能办公自动化平台，将大语言模型（LLM）的强大能力与全面的企业工作流自动化工具集相结合。本教程将引导您完成：

- 搭建 LeAgent 环境
- 使用聊天界面进行自然语言查询
- 使用 ReactFlow 构建可视化工作流
- 集成企业消息平台
- 自动化业务流程
- 安装和使用 Agent 技能

### 核心概念

| 概念 | 描述 |
|------|------|
| **QueryEngine** | 核心 Agent 编排器，处理查询并协调工具调用 |
| **工具（Tool）** | Agent 可使用的能力（如读取 PDF、发送邮件），支持别名、校验、路径沙箱和并发控制 |
| **工作流（Workflow）** | 可视化或 YAML 定义的自动化步骤序列（ReactFlow 编辑器） |
| **规则（Rule）** | 声明式 YAML 业务逻辑，用于校验和决策 |
| **渠道（Channel）** | 通信接口（Web、钉钉、飞书、企业微信、个人微信、控制台） |
| **技能（Skill）** | 可安装的 Agent 能力包，扩展 Agent 的功能 |
| **记忆（Memory）** | 认知三存储系统（情景记忆、语义记忆、程序记忆），为 Agent 提供上下文 |

### 支持的 LLM 提供商

LeAgent 开箱即用地支持多个 LLM 提供商：

- **OpenAI** — GPT-4、GPT-4o 等
- **Anthropic** — Claude 3.5、Claude 4 等
- **DeepSeek** — DeepSeek-V3、DeepSeek-R1 等
- **DashScope（通义千问）** — 阿里巴巴 Qwen 系列模型
- **Ollama** — 本地开源模型
- **vLLM** — 自部署模型服务

---

## 安装

### 前置依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| **git** | 任意近期版本 | 克隆代码仓库 |
| **uv** | 最新版 | Python 包管理 |
| **Node.js** | 20.19+ 或 22.12+ | 前端工具链（Vite 7） |
| **npm** | 随 Node 附带 | 前端依赖管理 |
| **Python** | 3.11+ | 后端运行时 |

### 方式一：快速启动脚本（推荐）

`start.sh` 脚本会处理依赖检查、Python 环境搭建、数据库迁移以及启动所有服务。

```bash
# 克隆仓库
git clone https://github.com/your-org/leagent.git
cd leagent

# 检查前置依赖并安装缺失项
./start.sh fix-deps

# 首次设置：初始化 ~/.leagent 配置
cd backend && uv run leagent init && cd ..

# 启动后端和前端
./start.sh
```

启动后的服务：
- **后端** — `http://localhost:7860`（FastAPI + Uvicorn）
- **前端** — `http://localhost:5173`（React 19 + Vite）

其他常用命令：

```bash
./start.sh backend        # 仅启动后端
./start.sh frontend       # 仅启动前端
./start.sh --prod         # 生产模式（构建前端，多 Worker 后端）
./start.sh check          # 运行环境就绪检查
./start.sh status         # 查看运行中的服务
./start.sh stop           # 停止所有 LeAgent 进程
./start.sh log            # 实时查看所有服务日志
```

### 方式二：Docker

```bash
# 克隆仓库
git clone https://github.com/your-org/leagent.git
cd leagent

# 设置必需的密钥
export LEAGENT_SECRET_KEY=$(openssl rand -hex 32)

# 启动容器（SQLite，无外部依赖）
docker compose -f deploy/docker-compose.yml up -d --build

# 检查状态
docker compose -f deploy/docker-compose.yml ps

# 查看日志
docker compose -f deploy/docker-compose.yml logs -f leagent
```

访问后端 API：`http://localhost:8000`

### 方式三：手动本地开发

#### 后端设置

```bash
cd backend

# 使用 uv 同步 Python 环境（包含 dev + browser 扩展）
uv sync --extra dev --extra browser

# 初始化 ~/.leagent 配置目录
uv run leagent init

# 运行数据库迁移
uv run alembic upgrade head

# 启动后端（开发模式，自动重载）
uv run leagent run --reload --port 7860
```

#### 前端设置

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器（API 代理到后端）
npm run dev
```

### 初始配置

安装完成后，配置 LLM 提供商：

```bash
cd backend

# 列出已配置的提供商
uv run leagent models list

# 检查系统健康状态
uv run leagent doctor
```

提供商 API 密钥可通过环境变量设置：

```bash
export DEEPSEEK_API_KEY="sk-your-key"
export OPENAI_API_KEY="sk-your-key"
export ANTHROPIC_API_KEY="sk-your-key"
```

也可以添加到 `leagent init` 创建的 `~/.leagent/.env` 文件中。

---

## 快速开始

### 第一次对话（CLI）

使用内置 CLI Agent 是最快的上手方式：

```bash
cd backend

# 交互式 REPL
uv run leagent

# 单次消息
uv run leagent -m "有哪些可用的工具？"

# 详细输出（显示工具调用）
uv run leagent -v
```

### 第一次对话（Web）

1. 使用 `./start.sh` 启动 LeAgent
2. 在浏览器中打开 `http://localhost:5173`
3. 点击侧边栏的"新建对话"
4. 尝试以下示例查询：

```
"帮我分析这份 PDF 文档"（附上 PDF 文件）
"根据这份 CSV 数据生成柱状图"
"创建一份总结这些笔记的 Word 报告"
```

### 第一个工作流

1. 在侧边栏中导航到"工作流"
2. 点击"新建工作流"
3. 从侧边栏拖拽组件到画布：
   - **开始** 节点 → 接收输入
   - **工具调用** 节点 → 例如 PDF 阅读器
   - **LLM 调用** 节点 → 分析内容
   - **结束** 节点 → 返回结果
4. 拖拽边线连接节点
5. 点击"保存"然后点击"运行"

---

## 聊天界面

聊天界面提供类似 ChatGPT 的体验，并具有增强功能。

### 基本使用

```
用户：阅读附件发票并提取总金额
Agent：我来为您分析这张发票。
       [调用工具：pdf_reader]
       [调用工具：image_ocr]
       
       发票信息如下：
       - 发票编号：INV-2024-001
       - 总金额：¥5,280.00
       - 到期日期：2024-03-15
```

### 文件附件

支持的文件类型：
- **文档**：PDF、DOCX、XLSX、TXT、CSV、JSON、Markdown
- **图片**：PNG、JPG、JPEG（支持 OCR）
- **压缩包**：ZIP、TAR、GZ

直接拖放文件或点击附件按钮即可上传。

### 高级查询

**多步骤任务：**
```
"从 OA 系统下载报销报告，
按照差旅政策验证所有条目，
并将摘要发送给财务团队"
```

**数据分析：**
```
"分析附件中的 Excel 文件，找出
'金额' 列中的异常值，并创建可视化图表"
```

**代码执行：**
```
"运行 Python 脚本，计算附件 CSV 中
销售数据的标准差"
```

### 会话管理

- **新建对话**：开始一段全新的对话
- **历史记录**：在侧边栏中查看历史对话
- **文件夹**：将对话整理到文件夹中
- **导出**：下载聊天记录

---

## 构建工作流

可视化工作流构建器（基于 ReactFlow）让您无需编写代码即可创建自动化流程。

### 节点类型

| 节点 | 描述 | 使用示例 |
|------|------|----------|
| **开始** | 入口点 | 接收输入数据 |
| **结束** | 出口点 | 返回结果 |
| **工具调用** | 执行工具 | 读取 PDF、发送邮件 |
| **LLM 调用** | AI 推理 | 分析、总结、分类 |
| **条件** | 分支逻辑 | 如果金额 > 1000 |
| **并行** | 并发执行 | 处理多个文件 |
| **人工审核** | 人工审批 | 经理签字确认 |
| **脚本** | 运行 Python 代码 | 自定义数据转换 |
| **脚本 Agent** | Agent 驱动的脚本 | 步骤中的复杂推理 |
| **编码 Agent** | 代码生成 Agent | 生成并执行代码 |
| **子工作流** | 嵌套工作流 | 复用现有工作流 |
| **转换** | 数据转换 | 映射、过滤、重塑数据 |
| **等待** | 暂停执行 | 延迟或等待事件 |
| **错误处理** | 错误恢复 | 捕获并处理失败 |

### 示例：报销审批工作流

```yaml
name: expense_approval
description: 自动化报销审批

nodes:
  - id: start
    type: start
    outputs:
      - name: expense_data
        type: object

  - id: validate_receipt
    type: tool_call
    tool: image_ocr
    inputs:
      image: "${start.expense_data.receipt_image}"
    
  - id: check_policy
    type: tool_call
    tool: rule_matcher
    inputs:
      data: "${validate_receipt.output}"
      rule_set: "expense_validation"

  - id: route_decision
    type: condition
    condition: "${check_policy.output.all_passed} == true"
    branches:
      true: auto_approve
      false: manager_review

  - id: auto_approve
    type: tool_call
    tool: oa_api
    inputs:
      action: "approve"
      expense_id: "${start.expense_data.id}"

  - id: manager_review
    type: human_review
    assignee: "${start.expense_data.department_manager}"
    timeout: "24h"

  - id: end
    type: end
    inputs:
      result: "${auto_approve.output || manager_review.output}"
```

### 创建工作流

1. **设计阶段**
   - 确定流程步骤
   - 确定决策点
   - 列出所需工具

2. **构建阶段**
   - 将节点拖拽到画布上
   - 配置节点参数
   - 用边线连接节点

3. **测试阶段**
   - 使用"测试运行"并提供示例数据
   - 查看执行日志
   - 验证输出结果

4. **部署阶段**
   - 保存工作流
   - 设置触发条件（定时任务、Webhook、手动）
   - 启用生产环境

---

## 使用工具

LeAgent 提供 80+ 内置工具，覆盖 15 个类别。

### 工具类别

| 类别 | 工具 | 描述 |
|------|------|------|
| **文档（doc）** | pdf_reader、excel_reader、word_reader、image_ocr、csv_processor、html_processor、markdown_processor、text_processor、archive_manager、config_file_tool、doc_classifier | 文档读取与处理 |
| **网页（web）** | scraper、web_search、image_search、form_fill、screenshot、click、login、image_download | 网页交互与爬取 |
| **数据（data）** | data_validate、data_clean、data_merge、data_transform、data_aggregate、sql_query、vector_search | 数据处理与分析 |
| **生成（gen）** | report_generator、excel_generator、word_generator、pdf_generator、pptx_generator、template_filler、checklist_generator | 文档生成 |
| **代码（code）** | code_execution、artifact、syntax_validator、deepseek_fim、uv_pip_install、operations、pipeline | 代码执行与开发 |
| **数据库（db）** | database_tool、sql_guard、inspector_ops | 数据库操作 |
| **图像（image）** | image_generate | 图像生成 |
| **图表（chart）** | chart_generator | 图表与可视化 |
| **画布（canvas）** | canvas_publish、html_guide、genui_guide、ui_components | 交互式画布 / 生成式 UI |
| **集成（integration）** | email_send、notification、oa_api、oa_adapter、oa_import、oa_export、external_api、speech_to_text | 外部系统集成 |
| **项目（project）** | read、write、edit、grep、glob、tree、outline、shell、patch | 项目文件操作 |
| **工具（util）** | rule_matcher、task_tools、cron_tools、date_calculator、file_manager、folder_tool、json_parser、text_splitter、cache_manager、ask_user、plan_tools、pet_bubble | 实用工具 |
| **技能（skills）** | install、loader、script、resource、package_skill | 技能管理 |
| **工作流（workflow）** | workflow_crud、chat_workflow、workflow_embed_emit | 工作流管理 |
| **编码项目（coding_project）** | 编码项目工具 | 编码项目管理 |

### 文档工具

**PDF 阅读器**
```
# 通过聊天使用
"读取附件 PDF 并总结关键要点"

# 支持文本提取、表格提取和逐页处理
```

**Excel 阅读器**
```
# 通过聊天使用
"分析附件 Excel 文件中的销售数据"

# 返回结构化数据，包含工作表名、列名和数据值
```

**OCR（图像转文字）**
```
# 通过聊天使用
"从这张扫描文档中提取文字"

# 支持 RapidOCR（默认）和 PaddleOCR（可选）
```

### 代码执行

`code_execution` 工具在共享后端虚拟环境的子进程沙箱中运行 Python 代码：

```
# 通过聊天使用
"编写一个 Python 脚本，计算 5 年期 7% 利率的复利"

# Agent 编写并执行代码，返回 stdout 和生成的文件
```

沙箱中可用的库：`pandas`、`matplotlib`、`seaborn`、`scipy`、`sympy`、`openpyxl` 等。

### 网页工具

**网页爬取**
```
"获取 example.com/news 上的最新新闻"
```

**网页搜索**
```
"搜索 Python 最佳实践 2025"
```

**表单填写（RPA）**
```
"在 OA 系统上填写请假申请表"
# 通过 Playwright 自动化网页表单交互
```

### 生成工具

**报告生成器**
```
"根据这些数据生成月度销售报告"
# 创建格式化的 Word/PDF 报告
```

**图表生成器**
```
"创建柱状图比较第一季度和第二季度的收入"
# 使用 matplotlib / seaborn 生成图表
```

**模板填充**
```
"用这位客户的信息填写合同模板"
# 基于 Jinja2 的模板填充
```

---

## 创建规则

规则引擎支持以声明式 YAML 文件定义业务逻辑，无需编写代码。

### 规则类型

| 类型 | 描述 | 示例 |
|------|------|------|
| `compare` | 值比较 | `category in [travel, meals, supplies]` |
| `date_range` | 日期校验 | `expense_date 在 2020-01-01 和今天之间` |
| `threshold` | 数值限制 | `amount 在 1 到 5000 之间` |
| `contains_all` | 必填值检查 | `所有必填字段均存在` |
| `date_diff` | 日期差异 | `提交日期在费用发生后 30 天内` |
| `regex_match` | 正则匹配 | `描述至少 10 个字符` |
| `cross_validate` | 字段关联校验 | `金额 > 100 时需附发票` |
| `llm_judge` | AI 评估 | `描述措辞是否专业` |

### 规则集示例

```yaml
# ~/.leagent/rules/expense_validation.yaml
id: expense_validation
name: 报销验证规则
description: 用于验证报销报告和报销申请的规则
version: "1.0.0"
enabled: true
tags:
  - finance
  - expense

rules:
  - id: max_single_expense
    name: 单笔最大报销金额
    description: 单笔费用不得超过最大限额
    severity: error
    condition:
      type: threshold
      params:
        value: "{{amount}}"
        max: 5000
    message: "报销金额 {{amount}} 超过最大允许金额（5000）"
    tags:
      - amount

  - id: valid_category
    name: 有效的报销类别
    severity: warning
    condition:
      type: compare
      params:
        left: "{{category}}"
        operator: in
        right:
          - travel
          - meals
          - supplies
          - equipment
          - software
          - training
    message: "未知的报销类别：{{category}}"

  - id: date_not_future
    name: 不允许未来日期
    severity: error
    condition:
      type: date_range
      params:
        date: "{{expense_date}}"
        start: "2020-01-01"
        end: "{{evaluation_date}}"
    message: "费用日期 {{expense_date}} 不能晚于 {{evaluation_date}}"

  - id: submission_timeliness
    name: 及时提交
    severity: warning
    condition:
      type: date_diff
      params:
        from_date: "{{expense_date}}"
        to_date: "{{submission_date}}"
        max_days: 30
    message: "费用在发生后超过 30 天才提交"

  - id: required_fields_present
    name: 必填字段
    severity: error
    condition:
      type: contains_all
      params:
        source: "{{fields_present}}"
        required:
          - amount
          - category
          - description
          - expense_date
    message: "缺少必填字段：{{missing}}"

metadata:
  author: LeAgent System
  department: finance
```

### 在工作流中使用规则

```yaml
# 在工作流节点中
- id: validate_expense
  type: tool_call
  tool: rule_matcher
  inputs:
    data: "${inputs.expense}"
    rule_set: "expense_validation"
  outputs:
    - name: all_passed
      type: boolean
    - name: violations
      type: array
```

### 通过 CLI 管理规则

```bash
cd backend
uv run leagent rules list          # 列出所有规则集
uv run leagent rules show <id>     # 查看规则详情
uv run leagent rules validate <id> # 验证规则语法
```

---

## 渠道集成

将 LeAgent 连接到企业消息平台。渠道配置位于 `~/.leagent/config.yaml`。

### 钉钉

1. 在群聊中创建一个钉钉机器人
2. 获取 Webhook URL 和签名密钥
3. 在 LeAgent 中配置：

```bash
cd backend
uv run leagent channels add dingtalk \
  --webhook-url "https://oapi.dingtalk.com/robot/send?access_token=xxx" \
  --secret "SEC..."
```

### 飞书

1. 在飞书工作空间中创建一个机器人
2. 通过渠道 CLI 或直接在 `~/.leagent/config.yaml` 中配置

### 企业微信

1. 在企业微信管理后台中创建一个应用
2. 通过渠道 CLI 进行配置

### 微信（个人微信 / iLink Bot）

通过腾讯 iLink Bot API 连接个人微信账号（长轮询，无需公网 webhook）。这与企业微信不同。

```bash
cd backend
uv run leagent channels login weixin   # 用微信扫码并在手机上确认
```

或在前端 **消息通道** 页使用微信扫码面板。手机确认后凭据立即保存并 **热启动长轮询**，无需重启前后端。

想系统了解「如何把微信接到任意自建 Agent」（iLink 协议、`context_token`、AES CDN、适配器/桥接分层），见开源技术分享：[`docs/guides/weixin-agent-from-scratch.md`](guides/weixin-agent-from-scratch.md)。

凭据保存在 `$LEAGENT_HOME/weixin/accounts/` 与 `config.yaml`（`channels.weixin`）。入站私信经通道桥接到 `default_agent`。

**限制：** 扫码登录绑定的是 iLink bot 身份——私信可靠；普通微信群通常不会向 bot 推送事件。

### 渠道配置（YAML）

```yaml
# ~/.leagent/config.yaml
channels:
  web:
    enabled: true
  console:
    enabled: true
  dingtalk:
    enabled: true
    webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=xxx"
    token: "SEC..."
  feishu:
    enabled: true
    endpoint: "https://open.feishu.cn/..."
    token: "xxx"
  wechat_work:
    enabled: false
    extra:
      corp_id: "xxx"
      agent_id: "xxx"
```

### 渠道消息流

```
用户 → 渠道 → LeAgent 后端 → QueryEngine → 工具 → 响应 → 渠道 → 用户
```

---

## API 使用

LeAgent 在 `/api/v1/`（以及较新的 `/api/v2/`）下暴露 REST API。默认认证模式为单用户直通（无需登录）。

### 健康检查

```bash
curl http://localhost:7860/health
```

### 聊天 API

```bash
# 创建聊天会话
curl -X POST http://localhost:7860/api/v1/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "我的对话"}'

# 发送消息（SSE 流式传输）
curl -X POST http://localhost:7860/api/v1/chat/sessions/{session_id}/messages \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "content": "分析季度销售报告",
    "stream": true
  }'

# 列出会话
curl http://localhost:7860/api/v1/chat/sessions
```

### OpenAI 兼容的补全接口

```bash
# 聊天补全（OpenAI 格式）
curl -X POST http://localhost:7860/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "你好！"}],
    "stream": true
  }'
```

### 工作流 API

```bash
# 列出工作流
curl http://localhost:7860/api/v1/workflow/flows

# 执行工作流
curl -X POST http://localhost:7860/api/v1/workflow/flows/{flow_id}/run \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "expense_id": "EXP-001",
      "amount": 2500,
      "category": "travel"
    }
  }'

# 检查执行状态
curl http://localhost:7860/api/v1/workflow/executions/{execution_id}
```

### 工具 API

```bash
# 列出可用工具
curl http://localhost:7860/api/v1/tools

# 获取工具 Schema
curl http://localhost:7860/api/v1/tools/{tool_name}
```

### 其他 API 端点

| 端点前缀 | 描述 |
|----------|------|
| `/api/v1/chat/` | 聊天会话、消息、补全 |
| `/api/v1/workflow/` | 工作流、执行、提示词 |
| `/api/v1/tools/` | 工具列表和 Schema |
| `/api/v1/rules/` | 规则管理 |
| `/api/v1/models/` | LLM 提供商配置 |
| `/api/v1/tasks/` | 后台任务监控 |
| `/api/v1/files/` | 文件上传/下载 |
| `/api/v1/skills/` | 技能管理 |
| `/api/v1/channels/` | 渠道配置 |
| `/api/v1/cron/` | 定时任务管理 |
| `/api/v1/templates/` | 工作流模板 |
| `/api/v1/webhooks/` | Webhook 端点 |
| `/api/v1/mcp/` | MCP 服务器管理 |
| `/api/v1/coding-projects/` | 编码项目工作空间 |
| `/api/v1/canvas/` | 画布 / 生成式 UI 托管 |
| `/api/v1/health/` | 健康检查 |
| `/api/v1/meta/` | 服务器元数据 |

### Python 客户端示例

```python
import httpx

class LeAgentClient:
    def __init__(self, base_url: str = "http://localhost:7860"):
        self.base_url = base_url
    
    async def create_session(self, name: str = "我的对话") -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/chat/sessions",
                json={"name": name},
            )
            return response.json()
    
    async def send_message(self, session_id: str, content: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/chat/sessions/{session_id}/messages",
                json={"content": content, "stream": False},
            )
            return response.json()
    
    async def run_workflow(self, flow_id: str, inputs: dict) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/workflow/flows/{flow_id}/run",
                json={"inputs": inputs},
            )
            return response.json()

# 使用示例
client = LeAgentClient()
session = await client.create_session("分析会话")
result = await client.send_message(session["id"], "总结附件文档")
```

---

## 进阶主题

### 自定义工具

通过继承 `BaseTool` 创建自定义工具：

```python
# backend/leagent/tools/custom/my_tool.py
from typing import Any

from leagent.tools.base import (
    BaseTool,
    ToolCategory,
    ToolContext,
    ToolResult,
    ValidationResult,
)


class MyCustomTool(BaseTool):
    name = "my_custom_tool"
    aliases = ["custom_process", "my_tool"]
    description = "为我的业务执行有用的操作"
    category = ToolCategory.UTIL
    search_hint = "custom processing business logic"

    is_concurrency_safe = True
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input_data": {
                    "type": "string",
                    "description": "要处理的输入",
                },
                "strict_mode": {
                    "type": "boolean",
                    "description": "启用严格校验",
                    "default": False,
                },
            },
            "required": ["input_data"],
        }

    async def validate_input(
        self, params: dict[str, Any], context: ToolContext
    ) -> ValidationResult:
        """超出 JSON Schema 之外的语义校验。"""
        data = params.get("input_data", "")
        if len(data) > 100_000:
            return ValidationResult(valid=False, message="输入超过 100KB 限制")
        return ValidationResult(valid=True)

    async def execute(
        self, params: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        if context.is_aborted:
            return ToolResult.fail("任务已中止")

        input_data = params["input_data"]
        strict_mode = params.get("strict_mode", False)

        result = self._process(input_data, strict=strict_mode)
        return ToolResult.ok(data={"output": result})

    def _process(self, data: str, strict: bool = False) -> str:
        # 在此处编写业务逻辑
        return f"已处理：{data}"
```

**要点说明：**
- `parameters` 是一个返回 JSON Schema 字典的 `@property`
- `execute()` 接收 `params: dict` 和 `context: ToolContext`（不是解包的 kwargs）
- 使用 `ToolResult.ok()` 和 `ToolResult.fail()` 工厂方法
- 使用 `context.is_aborted` 检查是否已取消
- `ValidationResult` 使用 `message` 字段（而非 `reason`）
- 将工具放在任意类别目录下；`ToolRegistry` 会自动发现

### Agent 记忆

LeAgent 内置认知三存储记忆系统：

| 存储类型 | 用途 | 持久性 |
|----------|------|--------|
| **工作记忆** | 当前对话上下文、暂存空间 | 会话级 |
| **短期记忆** | 近期会话缓存、压缩 | 临时 |
| **情景记忆** | 过去的对话摘要和事件 | 长期 |
| **语义记忆** | 提取的事实、实体知识 | 长期 |
| **程序记忆** | 学习到的任务模式和工作流 | 长期 |

记忆由 `AgentMemory` 管理，支持：
- 自动压缩会话以适应上下文窗口
- 在新对话中召回相关的历史事件
- 将重复出现的模式提升为程序记忆

### Agent 技能

技能是可安装的能力包，用于扩展 Agent 的功能：

```bash
cd backend

# 列出已安装的技能
uv run leagent skills list

# 安装技能
uv run leagent skills install <skill-name>
```

技能从 `~/.leagent/skills/` 目录发现，可以包含：
- 自定义工具定义
- 资源文件
- Python 脚本
- 打包的依赖

### MCP 集成

通过配置 `~/.leagent/config.yaml` 连接 Model Context Protocol 服务器：

```yaml
# ~/.leagent/config.yaml
mcp_servers:
  - name: filesystem
    url: "http://localhost:3000/mcp"
    enabled: true
    tools:
      - read_file
      - write_file

  - name: database
    url: "http://localhost:3001/mcp"
    api_key: "your-key"
    enabled: true
```

MCP 工具与内置工具并列显示，Agent 可自动使用。

### 提示词系统

LeAgent 采用分层提示词架构：

- **PromptBuilder** — 从注册的模板组装系统提示词
- **提示词注册表** — 存储和检索命名的提示词模板
- **上下文源** — 基于会话状态动态注入的提示词段落（激活的工具、规则、记忆等）

### 定时任务

使用定时任务系统自动化周期性任务：

```bash
cd backend
uv run leagent cron list              # 列出定时任务
uv run leagent cron add <schedule>    # 添加新任务
```

定时任务可以触发工作流、发送通知，或按计划运行 Agent 查询。

### 环境变量

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `PORT` | 后端端口 | 7860 |
| `FRONTEND_PORT` | 前端开发服务器端口 | 5173 |
| `HOST` | 后端绑定地址 | 0.0.0.0 |
| `DATABASE_URL` | PostgreSQL 连接字符串 | SQLite（零配置） |
| `LEAGENT_SECRET_KEY` | JWT / 签名密钥 | — |
| `DEEPSEEK_API_KEY` | DeepSeek 提供商 | — |
| `OPENAI_API_KEY` | OpenAI 提供商 | — |
| `ANTHROPIC_API_KEY` | Anthropic 提供商 | — |
| `LEAGENT_DEBUG` | 启用调试模式 | false |
| `LEAGENT_LOG_DIR` | 日志文件目录 | ./logs |
| `UV_SYNC_EXTRAS` | uv 安装的扩展 | dev browser |

### 数据库

LeAgent 默认使用 **SQLite**（零配置，存储在 `~/.leagent/` 中）。生产环境请将 `DATABASE_URL` 设置为 PostgreSQL 连接字符串。

迁移由 Alembic 管理：

```bash
cd backend

# 应用迁移
uv run leagent upgrade

# 创建新迁移
uv run leagent migrate "Add new table"

# 回滚
uv run leagent downgrade -r -1
```

---

## 故障排除

### 常见问题

**问题：LLM 无响应**
```bash
cd backend

# 检查提供商和工具健康状态
uv run leagent doctor

# 检查模型配置
uv run leagent models list
```

**问题：工具执行失败**
```bash
# 列出可用工具（CLI）
uv run leagent doctor  # 诊断信息中显示工具数量

# 查看后端日志
./start.sh log monolith
```

**问题：工作流卡住**
```bash
# 通过 API 检查任务状态
curl http://localhost:7860/api/v1/tasks

# 查看工作流执行日志
./start.sh log monolith
```

**问题：前端无法加载**
```bash
# 检查 Node.js 版本（需要 20.19+ 或 22.12+）
node -v

# 修复依赖
./start.sh fix-deps

# 查看前端日志
./start.sh log frontend
```

**问题：数据库迁移错误**
```bash
cd backend
uv run leagent upgrade          # 应用待处理的迁移
uv run leagent downgrade -r -1  # 回滚一步
```

### CLI 参考

```bash
leagent                    # 交互式 Agent REPL
leagent -m "message"       # 单次 Agent 对话
leagent chat               # 交互式 Agent（显式调用）
leagent init               # 首次 ~/.leagent 设置
leagent run                # 启动 HTTP API（Uvicorn）
leagent app start          # 带更多参数启动（SSL、Worker、重载）
leagent serve              # 使用 Gunicorn 启动（生产环境）
leagent doctor             # 健康/依赖检查
leagent version            # 显示版本信息
leagent models list        # 列出 LLM 提供商
leagent rules list         # 列出规则集
leagent skills list        # 列出已安装的技能
leagent workflows list     # 列出工作流（需要运行中的服务）
leagent tasks list         # 列出后台任务
leagent cron list          # 列出定时任务
leagent channels list      # 列出已配置的渠道
leagent templates list     # 列出工作流模板
leagent webhooks list      # 列出 Webhook
leagent config show        # 显示运行时配置
leagent shell              # 加载配置的 Python REPL
leagent upgrade            # 应用数据库迁移
leagent downgrade          # 回滚数据库迁移
leagent clean              # 清理临时文件
leagent prune              # 清除旧数据
```

### 获取帮助

- **GitHub Issues**：报告 Bug 和功能请求
- **`leagent doctor`**：本地运行诊断
- **日志**：`./start.sh log` 或查看 `logs/` 目录
- **架构文档**：查看 `docs/technical/` 获取详细的子系统文档

---

## 下一步

1. **浏览工具目录** — 探索 15 个类别中的 80+ 可用工具
2. **构建工作流** — 在可视化编辑器中创建第一个自动化流程
3. **安装技能** — 使用可安装的技能包扩展 Agent
4. **集成渠道** — 连接到团队的消息平台
5. **定义规则** — 将业务策略编码为声明式 YAML
6. **配置记忆** — 启用情景/语义记忆以实现持久上下文
7. **设置 MCP** — 连接外部 MCP 服务器获取更多能力
8. **设置定时任务** — 使用定时任务自动化周期性工作
9. **阅读架构文档** — 查看 `docs/technical/` 获取详细的子系统文档
