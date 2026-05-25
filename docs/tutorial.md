# LeAgent Tutorial

A comprehensive guide to getting started with LeAgent, from installation to building your first automated workflow.

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Chat Interface](#chat-interface)
5. [Building Workflows](#building-workflows)
6. [Using Tools](#using-tools)
7. [Creating Rules](#creating-rules)
8. [Channel Integration](#channel-integration)
9. [API Usage](#api-usage)
10. [Advanced Topics](#advanced-topics)

---

## Introduction

LeAgent is a local-first intelligent office automation platform that combines the power of Large Language Models (LLMs) with a comprehensive toolset for enterprise workflow automation. This tutorial will guide you through:

- Setting up LeAgent
- Using the chat interface for natural language queries
- Building visual workflows with ReactFlow
- Integrating with enterprise messaging platforms
- Automating business processes
- Installing and using agent skills

### Key Concepts

| Concept | Description |
|---------|-------------|
| **QueryEngine** | The core agent orchestrator that processes queries and coordinates tool use |
| **Tool** | A capability the agent can use (e.g., read PDF, send email), with aliases, validation, path sandboxing, and concurrency control |
| **Workflow** | A visual or YAML-defined sequence of automated steps (ReactFlow editor) |
| **Rule** | Declarative YAML business logic for validation and decision-making |
| **Channel** | Communication interface (Web, DingTalk, Feishu, WeChat Work, Console) |
| **Skill** | Installable agent capability packages that extend what the agent can do |
| **Memory** | Cognitive three-store system (episodic, semantic, procedural) for agent context |

### Supported LLM Providers

LeAgent supports multiple LLM providers out of the box:

- **OpenAI** — GPT-4, GPT-4o, etc.
- **Anthropic** — Claude 3.5, Claude 4, etc.
- **DeepSeek** — DeepSeek-V3, DeepSeek-R1, etc.
- **DashScope** — Alibaba Qwen models
- **Ollama** — Local open-source models
- **vLLM** — Self-hosted model serving

---

## Installation

### Prerequisites

| Dependency | Version | Purpose |
|------------|---------|---------|
| **git** | Any recent | Clone the repository |
| **uv** | Latest | Python package management |
| **Node.js** | 20.19+ or 22.12+ | Frontend toolchain (Vite 7) |
| **npm** | Bundled with Node | Frontend dependencies |
| **Python** | 3.11+ | Backend runtime |

### Option 1: Quick Start Script (Recommended)

The `start.sh` script handles dependency checking, Python environment setup, database migrations, and launching both services.

```bash
# Clone the repository
git clone https://github.com/your-org/leagent.git
cd leagent

# Check prerequisites and install missing deps
./start.sh fix-deps

# First-time setup: seed ~/.leagent config
cd backend && uv run leagent init && cd ..

# Start both backend and frontend
./start.sh
```

This starts:
- **Backend** at `http://localhost:7860` (FastAPI + Uvicorn)
- **Frontend** at `http://localhost:5173` (React 19 + Vite)

Other useful commands:

```bash
./start.sh backend        # Start backend only
./start.sh frontend       # Start frontend only
./start.sh --prod         # Production mode (builds frontend, multi-worker backend)
./start.sh check          # Run environment readiness check
./start.sh status         # Show running services
./start.sh stop           # Stop all LeAgent processes
./start.sh log            # Tail all service logs
```

### Option 2: Docker

```bash
# Clone the repository
git clone https://github.com/your-org/leagent.git
cd leagent

# Set required secret key
export LEAGENT_SECRET_KEY=$(openssl rand -hex 32)

# Start the container (SQLite, no external deps)
docker compose -f deploy/docker-compose.yml up -d --build

# Check status
docker compose -f deploy/docker-compose.yml ps

# View logs
docker compose -f deploy/docker-compose.yml logs -f leagent
```

Access the backend API at: `http://localhost:8000`

### Option 3: Manual Local Development

#### Backend Setup

```bash
cd backend

# Sync Python environment with uv (includes dev + browser extras)
uv sync --extra dev --extra browser

# Initialize ~/.leagent config directory
uv run leagent init

# Run database migrations
uv run alembic upgrade head

# Start the backend (dev mode with auto-reload)
uv run leagent run --reload --port 7860
```

#### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server (proxies API to backend)
npm run dev
```

### Initial Configuration

After installation, configure your LLM provider:

```bash
cd backend

# List configured providers
uv run leagent models list

# Check system health
uv run leagent doctor
```

Provider API keys can be set via environment variables:

```bash
export DEEPSEEK_API_KEY="sk-your-key"
export OPENAI_API_KEY="sk-your-key"
export ANTHROPIC_API_KEY="sk-your-key"
```

Or add them to the `~/.leagent/.env` file created by `leagent init`.

---

## Quick Start

### Your First Chat (CLI)

The fastest way to start using LeAgent is the built-in CLI agent:

```bash
cd backend

# Interactive REPL
uv run leagent

# One-shot message
uv run leagent -m "What tools are available?"

# Verbose output (shows tool calls)
uv run leagent -v
```

### Your First Chat (Web)

1. Start LeAgent with `./start.sh`
2. Open `http://localhost:5173` in your browser
3. Click "New Chat" in the sidebar
4. Try example queries:

```
"Help me analyze this PDF document" (attach a PDF)
"Generate a bar chart from this CSV data"
"Create a Word report summarizing these notes"
```

### Your First Workflow

1. Navigate to "Flows" in the sidebar
2. Click "Create New Flow"
3. Drag components from the sidebar:
   - **Start** node → receives input
   - **Tool Call** node → e.g., PDF Reader
   - **LLM Call** node → analyze content
   - **End** node → returns results
4. Connect the nodes by dragging edges
5. Click "Save" then "Run"

---

## Chat Interface

The chat interface provides a ChatGPT-like experience with enhanced capabilities.

### Basic Usage

```
User: Read the attached invoice and extract the total amount
Agent: I'll analyze the invoice for you.
       [Calling tool: pdf_reader]
       [Calling tool: image_ocr]
       
       The invoice shows:
       - Invoice Number: INV-2024-001
       - Total Amount: ¥5,280.00
       - Due Date: 2024-03-15
```

### File Attachments

Supported file types:
- **Documents**: PDF, DOCX, XLSX, TXT, CSV, JSON, Markdown
- **Images**: PNG, JPG, JPEG (OCR enabled)
- **Archives**: ZIP, TAR, GZ

Simply drag and drop files or click the attachment button.

### Advanced Queries

**Multi-step tasks:**
```
"Download the expense report from the OA system, 
validate all entries against our travel policy, 
and send a summary to the finance team"
```

**Data analysis:**
```
"Analyze the attached Excel file, identify outliers 
in the 'Amount' column, and create a visualization"
```

**Code execution:**
```
"Run a Python script to calculate the standard deviation 
of the sales data in the attached CSV"
```

### Session Management

- **New Chat**: Start a fresh conversation
- **History**: Access previous conversations in the sidebar
- **Folders**: Organize chats into folders
- **Export**: Download chat history

---

## Building Workflows

The visual workflow builder (powered by ReactFlow) lets you create automated processes without code.

### Node Types

| Node | Description | Example Use |
|------|-------------|-------------|
| **Start** | Entry point | Receive input data |
| **End** | Exit point | Return results |
| **Tool Call** | Execute a tool | Read PDF, send email |
| **LLM Call** | AI reasoning | Analyze, summarize, classify |
| **Condition** | Branch logic | If amount > 1000 |
| **Parallel** | Concurrent execution | Process multiple files |
| **Human Review** | Manual approval | Manager sign-off |
| **Script** | Run Python code | Custom data transforms |
| **Script Agent** | Agent-powered script | Complex reasoning in a step |
| **Coding Agent** | Code generation agent | Generate and execute code |
| **Subworkflow** | Nested workflow | Reuse existing flows |
| **Transform** | Data transformation | Map, filter, reshape data |
| **Wait** | Pause execution | Delay or await event |
| **Error Handler** | Error recovery | Catch and handle failures |

### Example: Expense Approval Workflow

```yaml
name: expense_approval
description: Automated expense report approval

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

### Creating a Workflow

1. **Design Phase**
   - Identify the process steps
   - Determine decision points
   - List required tools

2. **Build Phase**
   - Drag nodes onto the canvas
   - Configure node parameters
   - Connect nodes with edges

3. **Test Phase**
   - Use "Test Run" with sample data
   - Review execution logs
   - Verify outputs

4. **Deploy Phase**
   - Save the workflow
   - Set trigger conditions (cron, webhook, manual)
   - Enable for production

---

## Using Tools

LeAgent provides 80+ built-in tools across 15 categories.

### Tool Categories

| Category | Tools | Description |
|----------|-------|-------------|
| **doc** | pdf_reader, excel_reader, word_reader, image_ocr, csv_processor, html_processor, markdown_processor, text_processor, archive_manager, config_file_tool, doc_classifier | Document reading and processing |
| **web** | scraper, web_search, image_search, form_fill, screenshot, click, login, image_download | Web interaction and scraping |
| **data** | data_validate, data_clean, data_merge, data_transform, data_aggregate, sql_query, vector_search | Data processing and analysis |
| **gen** | report_generator, excel_generator, word_generator, pdf_generator, pptx_generator, template_filler, checklist_generator | Document generation |
| **code** | code_execution, artifact, syntax_validator, deepseek_fim, uv_pip_install, operations, pipeline | Code execution and development |
| **db** | database_tool, sql_guard, inspector_ops | Database operations |
| **image** | image_generate | Image generation |
| **chart** | chart_generator | Chart and visualization creation |
| **canvas** | canvas_publish, html_guide, genui_guide, ui_components | Interactive canvas / gen-UI |
| **integration** | email_send, notification, oa_api, oa_adapter, oa_import, oa_export, external_api, speech_to_text | External system integration |
| **project** | read, write, edit, grep, glob, tree, outline, shell, patch | Project file operations |
| **util** | rule_matcher, task_tools, cron_tools, date_calculator, file_manager, folder_tool, json_parser, text_splitter, cache_manager, ask_user, plan_tools, pet_bubble | Utility functions |
| **skills** | install, loader, script, resource, package_skill | Skill management |
| **workflow** | workflow_crud, chat_workflow, workflow_embed_emit | Workflow management |
| **coding_project** | coding project tools | Coding project management |

### Document Tools

**PDF Reader**
```
# Via chat
"Read the attached PDF and summarize the key points"

# Supports text extraction, table extraction, and page-level processing
```

**Excel Reader**
```
# Via chat
"Analyze the sales data in the attached Excel file"

# Returns structured data with sheet names, columns, and values
```

**OCR (Image to Text)**
```
# Via chat
"Extract text from this scanned document"

# Supports RapidOCR (default) and PaddleOCR (optional)
```

### Code Execution

The `code_execution` tool runs Python code in a subprocess sandbox sharing the backend's virtual environment:

```
# Via chat
"Write a Python script to calculate compound interest for 5 years at 7%"

# The agent writes and executes code, returning stdout + any generated files
```

Available in the sandbox: `pandas`, `matplotlib`, `seaborn`, `scipy`, `sympy`, `openpyxl`, and more.

### Web Tools

**Web Scraper**
```
"Get the latest news from example.com/news"
```

**Web Search**
```
"Search the web for Python best practices 2025"
```

**Form Fill (RPA)**
```
"Fill out the leave request form on the OA system"
# Automates web form interactions via Playwright
```

### Generation Tools

**Report Generator**
```
"Generate a monthly sales report from this data"
# Creates formatted Word/PDF reports
```

**Chart Generator**
```
"Create a bar chart comparing Q1 vs Q2 revenue"
# Generates charts with matplotlib / seaborn
```

**Template Filler**
```
"Fill out the contract template with this client's information"
# Jinja2-based template population
```

---

## Creating Rules

The rule engine enables declarative business logic without code, defined in YAML files.

### Rule Types

| Type | Description | Example |
|------|-------------|---------|
| `compare` | Value comparison | `category in [travel, meals, supplies]` |
| `date_range` | Date validation | `expense_date between 2020-01-01 and today` |
| `threshold` | Numeric limits | `amount between 1 and 5000` |
| `contains_all` | Required values | `all required fields present` |
| `date_diff` | Date difference | `submitted within 30 days of expense` |
| `regex_match` | Pattern matching | `description at least 10 chars` |
| `cross_validate` | Field relationships | `receipt required if amount > 100` |
| `llm_judge` | AI-based evaluation | `description is professional` |

### Example Rule Set

```yaml
# ~/.leagent/rules/expense_validation.yaml
id: expense_validation
name: Expense Validation Rules
description: Rules for validating expense reports and reimbursement requests
version: "1.0.0"
enabled: true
tags:
  - finance
  - expense

rules:
  - id: max_single_expense
    name: Maximum Single Expense
    description: Individual expense must not exceed the maximum limit
    severity: error
    condition:
      type: threshold
      params:
        value: "{{amount}}"
        max: 5000
    message: "Expense amount {{amount}} exceeds maximum allowed (5000)"
    tags:
      - amount

  - id: valid_category
    name: Valid Expense Category
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
    message: "Unknown expense category: {{category}}"

  - id: date_not_future
    name: No Future Dates
    severity: error
    condition:
      type: date_range
      params:
        date: "{{expense_date}}"
        start: "2020-01-01"
        end: "{{evaluation_date}}"
    message: "Expense date {{expense_date}} cannot be after {{evaluation_date}}"

  - id: submission_timeliness
    name: Timely Submission
    severity: warning
    condition:
      type: date_diff
      params:
        from_date: "{{expense_date}}"
        to_date: "{{submission_date}}"
        max_days: 30
    message: "Expense submitted more than 30 days after occurrence"

  - id: required_fields_present
    name: Required Fields
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
    message: "Missing required fields: {{missing}}"

metadata:
  author: LeAgent System
  department: finance
```

### Using Rules in Workflows

```yaml
# In a workflow node
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

### Managing Rules via CLI

```bash
cd backend
uv run leagent rules list          # List all rule sets
uv run leagent rules show <id>     # Show rule details
uv run leagent rules validate <id> # Validate rule syntax
```

---

## Channel Integration

Connect LeAgent to enterprise messaging platforms. Channel configuration lives in `~/.leagent/config.yaml`.

### DingTalk (钉钉)

1. Create a DingTalk robot in your group
2. Get the webhook URL and secret
3. Configure in LeAgent:

```bash
cd backend
uv run leagent channels add dingtalk \
  --webhook-url "https://oapi.dingtalk.com/robot/send?access_token=xxx" \
  --secret "SEC..."
```

### Feishu (飞书)

1. Create a Feishu bot in your workspace
2. Configure via the channels CLI or directly in `~/.leagent/config.yaml`

### WeChat Work (企业微信)

1. Create an application in the WeChat Work admin console
2. Configure via the channels CLI

### Channel Configuration (YAML)

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

### Channel Message Flow

```
User → Channel → LeAgent Backend → QueryEngine → Tools → Response → Channel → User
```

---

## API Usage

LeAgent exposes a REST API under `/api/v1/` (and `/api/v2/` for newer endpoints). The default auth mode is single-user passthrough (no login required).

### Health Check

```bash
curl http://localhost:7860/health
```

### Chat API

```bash
# Create a chat session
curl -X POST http://localhost:7860/api/v1/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "My Chat"}'

# Send a message (SSE streaming)
curl -X POST http://localhost:7860/api/v1/chat/sessions/{session_id}/messages \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "content": "Analyze the quarterly sales report",
    "stream": true
  }'

# List sessions
curl http://localhost:7860/api/v1/chat/sessions
```

### OpenAI-Compatible Completions

```bash
# Chat completions (OpenAI format)
curl -X POST http://localhost:7860/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'
```

### Workflow API

```bash
# List workflows
curl http://localhost:7860/api/v1/workflow/flows

# Execute a workflow
curl -X POST http://localhost:7860/api/v1/workflow/flows/{flow_id}/run \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "expense_id": "EXP-001",
      "amount": 2500,
      "category": "travel"
    }
  }'

# Check execution status
curl http://localhost:7860/api/v1/workflow/executions/{execution_id}
```

### Tools API

```bash
# List available tools
curl http://localhost:7860/api/v1/tools

# Get tool schema
curl http://localhost:7860/api/v1/tools/{tool_name}
```

### Other API Endpoints

| Endpoint Prefix | Description |
|-----------------|-------------|
| `/api/v1/chat/` | Chat sessions, messages, completions |
| `/api/v1/workflow/` | Flows, executions, prompts |
| `/api/v1/tools/` | Tool listing and schemas |
| `/api/v1/rules/` | Rule management |
| `/api/v1/models/` | LLM provider configuration |
| `/api/v1/tasks/` | Background task monitoring |
| `/api/v1/files/` | File upload/download |
| `/api/v1/skills/` | Skill management |
| `/api/v1/channels/` | Channel configuration |
| `/api/v1/cron/` | Scheduled job management |
| `/api/v1/templates/` | Workflow templates |
| `/api/v1/webhooks/` | Webhook endpoints |
| `/api/v1/mcp/` | MCP server management |
| `/api/v1/coding-projects/` | Coding project workspaces |
| `/api/v1/canvas/` | Canvas / gen-UI hosting |
| `/api/v1/health/` | Health checks |
| `/api/v1/meta/` | Server metadata |

### Python Client Example

```python
import httpx

class LeAgentClient:
    def __init__(self, base_url: str = "http://localhost:7860"):
        self.base_url = base_url
    
    async def create_session(self, name: str = "My Chat") -> dict:
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

# Usage
client = LeAgentClient()
session = await client.create_session("Analysis Session")
result = await client.send_message(session["id"], "Summarize the attached document")
```

---

## Advanced Topics

### Custom Tools

Create a custom tool by extending `BaseTool`:

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
    description = "Does something useful for my business"
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
                    "description": "The input to process",
                },
                "strict_mode": {
                    "type": "boolean",
                    "description": "Enable strict validation",
                    "default": False,
                },
            },
            "required": ["input_data"],
        }

    async def validate_input(
        self, params: dict[str, Any], context: ToolContext
    ) -> ValidationResult:
        """Semantic validation beyond JSON schema."""
        data = params.get("input_data", "")
        if len(data) > 100_000:
            return ValidationResult(valid=False, message="Input exceeds 100KB limit")
        return ValidationResult(valid=True)

    async def execute(
        self, params: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        if context.is_aborted:
            return ToolResult.fail("Task was aborted")

        input_data = params["input_data"]
        strict_mode = params.get("strict_mode", False)

        result = self._process(input_data, strict=strict_mode)
        return ToolResult.ok(data={"output": result})

    def _process(self, data: str, strict: bool = False) -> str:
        # Your business logic here
        return f"Processed: {data}"
```

**Key points:**
- `parameters` is a `@property` returning a JSON Schema dict
- `execute()` receives `params: dict` and `context: ToolContext` (not unpacked kwargs)
- Use `ToolResult.ok()` and `ToolResult.fail()` factory methods
- Use `context.is_aborted` to check for cancellation
- `ValidationResult` uses the `message` field (not `reason`)
- Place tools under any category directory; the `ToolRegistry` auto-discovers them

### Agent Memory

LeAgent includes a cognitive three-store memory system:

| Store | Purpose | Persistence |
|-------|---------|-------------|
| **Working Memory** | Current conversation context, scratchpad | Session-scoped |
| **Short-term Memory** | Recent session cache, compression | Temporary |
| **Episodic Memory** | Past conversation summaries and events | Long-term |
| **Semantic Memory** | Extracted facts, entity knowledge | Long-term |
| **Procedural Memory** | Learned task patterns and workflows | Long-term |

Memory is managed by `AgentMemory` and supports:
- Automatic session compression to stay within context windows
- Recall of relevant past episodes during new conversations
- Promotion of repeated patterns into procedural memory

### Agent Skills

Skills are installable packages that extend the agent's capabilities:

```bash
cd backend

# List installed skills
uv run leagent skills list

# Install a skill
uv run leagent skills install <skill-name>
```

Skills are discovered from `~/.leagent/skills/` and can include:
- Custom tool definitions
- Resource files
- Python scripts
- Bundled dependencies

### MCP Integration

Connect to Model Context Protocol servers by configuring `~/.leagent/config.yaml`:

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

MCP tools appear alongside built-in tools and are automatically available to the agent.

### Prompt System

LeAgent uses a layered prompt architecture:

- **PromptBuilder** — assembles system prompts from registered templates
- **Prompt Registry** — stores and retrieves named prompt templates
- **Context Sources** — dynamic prompt sections injected based on session state (active tools, rules, memory, etc.)

### Cron / Scheduled Jobs

Automate recurring tasks with the cron system:

```bash
cd backend
uv run leagent cron list              # List scheduled jobs
uv run leagent cron add <schedule>    # Add a new job
```

Cron jobs can trigger workflows, send notifications, or run agent queries on a schedule.

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PORT` | Backend port | 7860 |
| `FRONTEND_PORT` | Frontend dev server port | 5173 |
| `HOST` | Backend bind address | 0.0.0.0 |
| `DATABASE_URL` | PostgreSQL connection string | SQLite (zero-config) |
| `LEAGENT_SECRET_KEY` | JWT / signing secret | — |
| `DEEPSEEK_API_KEY` | DeepSeek provider | — |
| `OPENAI_API_KEY` | OpenAI provider | — |
| `ANTHROPIC_API_KEY` | Anthropic provider | — |
| `LEAGENT_DEBUG` | Enable debug mode | false |
| `LEAGENT_LOG_DIR` | Log file directory | ./logs |
| `UV_SYNC_EXTRAS` | uv extras to install | dev browser |

### Database

LeAgent defaults to **SQLite** (zero-config, stored in `~/.leagent/`). For production, set `DATABASE_URL` to a PostgreSQL connection string.

Migrations are managed with Alembic:

```bash
cd backend

# Apply migrations
uv run leagent upgrade

# Create a new migration
uv run leagent migrate "Add new table"

# Rollback
uv run leagent downgrade -r -1
```

---

## Troubleshooting

### Common Issues

**Issue: LLM not responding**
```bash
cd backend

# Check provider and tool health
uv run leagent doctor

# Check model configuration
uv run leagent models list
```

**Issue: Tool execution failed**
```bash
# List available tools (CLI)
uv run leagent doctor  # Shows tool count in diagnostics

# Check backend logs
./start.sh log monolith
```

**Issue: Workflow stuck**
```bash
# Check task status via API
curl http://localhost:7860/api/v1/tasks

# View workflow execution logs
./start.sh log monolith
```

**Issue: Frontend not loading**
```bash
# Check Node.js version (needs 20.19+ or 22.12+)
node -v

# Fix dependencies
./start.sh fix-deps

# Check frontend logs
./start.sh log frontend
```

**Issue: Database migration errors**
```bash
cd backend
uv run leagent upgrade          # Apply pending migrations
uv run leagent downgrade -r -1  # Roll back one step
```

### CLI Reference

```bash
leagent                    # Interactive agent REPL
leagent -m "message"       # One-shot agent turn
leagent chat               # Interactive agent (explicit)
leagent init               # First-time ~/.leagent setup
leagent run                # Start HTTP API (Uvicorn)
leagent app start          # Start with more flags (SSL, workers, reload)
leagent serve              # Start with Gunicorn (production)
leagent doctor             # Health / dependency check
leagent version            # Show version info
leagent models list        # List LLM providers
leagent rules list         # List rule sets
leagent skills list        # List installed skills
leagent workflows list     # List workflows (requires running server)
leagent tasks list         # List background tasks
leagent cron list          # List cron jobs
leagent channels list      # List configured channels
leagent templates list     # List workflow templates
leagent webhooks list      # List webhooks
leagent config show        # Show runtime config
leagent shell              # Python REPL with config loaded
leagent upgrade            # Apply database migrations
leagent downgrade          # Revert database migrations
leagent clean              # Clean temporary files
leagent prune              # Prune old data
```

### Getting Help

- **GitHub Issues**: Report bugs and feature requests
- **`leagent doctor`**: Run diagnostics locally
- **Logs**: `./start.sh log` or check `logs/` directory
- **Architecture docs**: See `docs/technical/` for deep subsystem documentation

---

## Next Steps

1. **Explore the Tool Catalog** — Browse all 80+ available tools across 15 categories
2. **Build a Workflow** — Create your first automated process in the visual editor
3. **Install Skills** — Extend the agent with installable skill packages
4. **Integrate Channels** — Connect to your team's messaging platform
5. **Define Rules** — Encode your business policies as declarative YAML
6. **Configure Memory** — Enable episodic/semantic memory for persistent context
7. **Set Up MCP** — Connect external MCP servers for additional capabilities
8. **Schedule Jobs** — Automate recurring tasks with cron
9. **Read the Architecture Docs** — See `docs/technical/` for detailed subsystem documentation
