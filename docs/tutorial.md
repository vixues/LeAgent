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

LeAgent is an intelligent office automation platform that combines the power of Large Language Models (LLMs) with a comprehensive toolset for enterprise workflow automation. This tutorial will guide you through:

- Setting up LeAgent
- Using the chat interface for natural language queries
- Building visual workflows
- Integrating with enterprise messaging platforms
- Automating business processes

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Agent** | The AI core that understands queries and executes tasks |
| **Tool** | A capability the agent can use (e.g., read PDF, send email), with aliases, validation, and concurrency control |
| **Workflow** | A sequence of automated steps |
| **Rule** | Business logic for validation and decision-making |
| **Channel** | Communication interface (Web, DingTalk, Feishu, etc.) |

---

## Installation

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-org/leagent.git
cd leagent

# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f leagent
```

Access the platform at: http://localhost:8080

### Option 2: Local Development

#### Backend Setup

```bash
cd leagent/backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -e ".[dev]"

# Initialize configuration
leagent init

# Start development server
leagent app --reload --port 8000
```

#### Frontend Setup

```bash
cd leagent/frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Initial Configuration

After installation, configure your LLM provider:

```bash
# Add OpenAI provider
leagent models add openai --api-key sk-your-key

# Or add local Ollama
leagent models add ollama --base-url http://localhost:11434

# Test connection
leagent models test openai
```

---

## Quick Start

### Your First Chat

1. Open the web interface at http://localhost:8080
2. Log in with default credentials:
   - Username: `admin`
   - Password: `admin123`
3. Click "New Chat" in the sidebar
4. Try these example queries:

```
"Help me analyze this PDF document" (attach a PDF)
"What expenses need approval in the last week?"
"Generate a summary report for Q1 sales"
```

### Your First Workflow

1. Navigate to "Flows" in the sidebar
2. Click "Create New Flow"
3. Drag components from the sidebar:
   - Start node
   - PDF Reader tool
   - LLM Call for analysis
   - End node
4. Connect the nodes
5. Click "Save" and "Run"

---

## Chat Interface

The chat interface provides a ChatGPT-like experience with enhanced capabilities.

### Basic Usage

```
User: Read the attached invoice and extract the total amount
Agent: I'll analyze the invoice for you.
       [Calling tool: pdf_reader]
       [Calling tool: invoice_ocr]
       
       The invoice shows:
       - Invoice Number: INV-2024-001
       - Total Amount: ¥5,280.00
       - Due Date: 2024-03-15
```

### File Attachments

Supported file types:
- Documents: PDF, DOCX, XLSX, TXT
- Images: PNG, JPG, JPEG (OCR enabled)
- Data: CSV, JSON

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

### Session Management

- **New Chat**: Start a fresh conversation
- **History**: Access previous conversations
- **Export**: Download chat history as JSON
- **Delete**: Remove a conversation

---

## Building Workflows

The visual workflow builder lets you create automated processes without code.

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
| **Loop** | Iteration | Process each item |

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
      rule_set: "expense_policy"

  - id: route_decision
    type: condition
    condition: "${check_policy.output.compliant} == true"
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
   - Set trigger conditions
   - Enable for production

---

## Using Tools

LeAgent provides 60 built-in tools across 6 categories, plus a `code_execution` tool backed by a subprocess sandbox.

### Document Tools

**PDF Reader**
```python
# Via chat
"Read the attached PDF and summarize the key points"

# Via API
POST /api/v1/tools/pdf_reader/execute
{
  "file_path": "/path/to/document.pdf",
  "extract_tables": true
}
```

**Excel Reader**
```python
# Via chat
"Analyze the sales data in the attached Excel file"

# Returns structured data with sheet names, columns, and values
```

**OCR (Image to Text)**
```python
# Via chat
"Extract text from this scanned document"

# Supports Chinese and English with PaddleOCR
```

### Web Tools

**Web Scraper**
```python
# Via chat
"Get the latest news from example.com/news"

# Extracts structured content from web pages
```

**Form Fill (RPA)**
```python
# Via chat
"Fill out the leave request form on the OA system"

# Automates web form interactions via Playwright
```

### Data Tools

**Data Validation**
```python
# Via chat
"Validate this CSV file against our data quality rules"

# Checks for: missing values, duplicates, format errors, outliers
```

**SQL Query**
```python
# Via chat
"Query the database for all orders in March"

# Executes read-only SQL on configured databases
```

### Generation Tools

**Report Generator**
```python
# Via chat
"Generate a monthly sales report from this data"

# Creates formatted Word/PDF reports with charts
```

**Template Filler**
```python
# Via chat
"Fill out the contract template with this client's information"

# Jinja2-based template population
```

---

## Creating Rules

The rule engine enables declarative business logic without code.

### Rule Types

| Type | Description | Example |
|------|-------------|---------|
| `compare` | Value comparison | `amount <= 5000` |
| `date_range` | Date validation | `date within last 90 days` |
| `threshold` | Numeric limits | `quantity > 0` |
| `contains_all` | Required values | `category in [A, B, C]` |
| `regex_match` | Pattern matching | `email matches @company.com` |
| `cross_validate` | Field relationships | `end_date > start_date` |
| `llm_judge` | AI-based evaluation | `description is professional` |

### Example Rule Set

```yaml
# config/rules/expense_policy.yaml
name: expense_policy
version: "1.0"
description: Company expense reimbursement policy

rules:
  - id: max_amount
    name: Maximum Expense Amount
    type: threshold
    condition:
      field: amount
      operator: lte
      value: 10000
    on_fail:
      action: reject
      message: "Expense exceeds maximum limit of ¥10,000"

  - id: valid_category
    name: Valid Expense Category
    type: contains_all
    condition:
      field: category
      allowed:
        - travel
        - meals
        - supplies
        - training
        - equipment
    on_fail:
      action: flag_review
      message: "Unknown expense category"

  - id: receipt_required
    name: Receipt Required for Large Expenses
    type: compare
    condition:
      when: "amount > 200"
      field: receipt_attached
      operator: eq
      value: true
    on_fail:
      action: reject
      message: "Receipt required for expenses over ¥200"

  - id: date_validity
    name: Expense Date Validity
    type: date_range
    condition:
      field: expense_date
      min_offset: -90  # days from today
      max_offset: 0
    on_fail:
      action: reject
      message: "Expense date must be within the last 90 days"

  - id: description_quality
    name: Description Quality Check
    type: llm_judge
    condition:
      field: description
      criteria: |
        The description should:
        - Clearly state the business purpose
        - Include relevant details (who, what, when, where)
        - Be professional in tone
    on_fail:
      action: flag_review
      message: "Please provide a more detailed description"
```

### Using Rules in Workflows

```yaml
# In a workflow node
- id: validate_expense
  type: tool_call
  tool: rule_matcher
  inputs:
    data: "${inputs.expense}"
    rule_set: "expense_policy"
  outputs:
    - name: is_valid
      type: boolean
    - name: violations
      type: array
```

---

## Channel Integration

Connect LeAgent to enterprise messaging platforms.

### DingTalk (钉钉)

1. Create a DingTalk robot in your group
2. Get the webhook URL and secret
3. Configure in LeAgent:

```bash
leagent channels add dingtalk \
  --webhook-url "https://oapi.dingtalk.com/robot/send?access_token=xxx" \
  --secret "SEC..."
```

4. Test the integration:
```bash
leagent channels test dingtalk --message "Hello from LeAgent!"
```

### Feishu (飞书)

1. Create a Feishu bot in your workspace
2. Configure OAuth credentials:

```yaml
# config/channels/feishu.yaml
type: feishu
app_id: "cli_xxx"
app_secret: "xxx"
verification_token: "xxx"
```

### WeChat Work (企业微信)

1. Create an application in WeChat Work admin console
2. Configure:

```yaml
# config/channels/wechat_work.yaml
type: wechat_work
corp_id: "xxx"
agent_id: "xxx"
secret: "xxx"
```

### Channel Message Flow

```
User → Channel → LeAgent → Agent → Response → Channel → User
```

Example DingTalk interaction:
```
@LeAgent 帮我查询本月的报销申请状态

LeAgent: 正在查询您的报销申请...

📋 本月报销申请状态:
- REQ-001: ¥2,500 (已批准)
- REQ-002: ¥800 (待审核)
- REQ-003: ¥1,200 (已驳回 - 缺少发票)

总计: 3笔申请, 1笔已批准, 1笔待审核, 1笔已驳回
```

---

## API Usage

### Authentication

```bash
# Login to get access token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Response
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### Chat API

```bash
# Create a chat session
curl -X POST http://localhost:8000/api/v1/chat/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Chat"}'

# Send a message (SSE streaming)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "session_id": "uuid-here",
    "message": "Analyze the Q1 sales report"
  }'
```

### Workflow API

```bash
# Execute a workflow
curl -X POST http://localhost:8000/api/v1/workflows/expense-approval/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {
      "expense_id": "EXP-001",
      "amount": 2500,
      "category": "travel"
    }
  }'

# Check execution status
curl http://localhost:8000/api/v1/tasks/task-uuid \
  -H "Authorization: Bearer $TOKEN"
```

### Python SDK Example

```python
import httpx

class LeAgentClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {token}"}
    
    async def chat(self, message: str, session_id: str = None):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/chat",
                headers=self.headers,
                json={"message": message, "session_id": session_id}
            )
            return response.json()
    
    async def execute_workflow(self, workflow_id: str, inputs: dict):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/workflows/{workflow_id}/execute",
                headers=self.headers,
                json={"inputs": inputs}
            )
            return response.json()

# Usage
client = LeAgentClient("http://localhost:8000", token)
result = await client.chat("Summarize the attached document")
```

---

## Advanced Topics

### Custom Tools

Create a custom tool with the full `BaseTool` interface:

```python
# leagent/backend/leagent/tools/custom/my_tool.py
from leagent.tools.base import BaseTool, ToolResult, ToolContext, ValidationResult

class MyCustomTool(BaseTool):
    name = "my_custom_tool"
    aliases = ["custom_process", "my_tool"]
    description = "Does something useful for my business"
    search_hint = "custom processing business logic"
    parameters = {
        "type": "object",
        "properties": {
            "input_data": {
                "type": "string",
                "description": "The input to process"
            },
            "strict_mode": {
                "type": "boolean",
                "description": "Enable strict validation",
                "default": False
            }
        },
        "required": ["input_data"]
    }

    is_concurrency_safe = True
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    async def validate_input(self, params: dict) -> ValidationResult:
        """Semantic validation beyond JSON schema."""
        data = params.get("input_data", "")
        if len(data) > 100_000:
            return ValidationResult(valid=False, reason="Input exceeds 100KB limit")
        return ValidationResult(valid=True)

    def get_activity_description(self, params: dict) -> str:
        """Text shown in UI spinner during execution."""
        return f"Processing custom data ({len(params.get('input_data', ''))} chars)"

    async def execute(
        self,
        context: ToolContext,
        input_data: str,
        strict_mode: bool = False,
        **kwargs
    ) -> ToolResult:
        if context.abort_signal and context.abort_signal.is_set():
            return ToolResult(success=False, error="Task was aborted")

        result = self._process(input_data, strict=strict_mode)
        return ToolResult(success=True, data={"output": result})
```

Tools are automatically discovered by the `ToolRegistry` when placed under any category
directory (`doc/`, `web/`, `data/`, `gen/`, `integration/`, `util/`, or a custom directory).
The tool's `aliases` allow it to be invoked by any of its alternative names, and
`search_hint` helps the `search_tools()` fuzzy-matching find it by keyword.

### MCP Integration

Connect to Model Context Protocol servers:

```yaml
# config/mcp_servers.yaml
servers:
  - name: filesystem
    type: stdio
    command: npx
    args: ["-y", "@anthropic/mcp-server-filesystem", "/data"]
    
  - name: database
    type: http
    url: http://localhost:3000/mcp
```

### Performance Tuning

```yaml
# config/settings.yaml
performance:
  # LLM caching
  llm_cache_enabled: true
  llm_cache_ttl: 3600
  
  # Database connection pool
  db_pool_size: 20
  db_max_overflow: 10
  
  # Redis connection pool
  redis_pool_size: 50
  
  # Concurrent tool execution
  max_parallel_tools: 5
```

### Security Hardening

```yaml
# config/settings.yaml
security:
  # JWT configuration
  jwt_algorithm: HS256
  access_token_expire_minutes: 30
  refresh_token_expire_days: 7
  
  # Rate limiting
  rate_limit_enabled: true
  rate_limit_requests: 100
  rate_limit_window: 60
  
  # Content security
  max_upload_size_mb: 50
  allowed_file_types:
    - pdf
    - docx
    - xlsx
    - png
    - jpg
```

---

## Troubleshooting

### Common Issues

**Issue: LLM not responding**
```bash
# Check provider status
leagent models test openai

# View logs
docker compose logs leagent | grep -i error
```

**Issue: Tool execution failed**
```bash
# Check tool availability
leagent tools list

# Test specific tool
leagent tools test pdf_reader --file test.pdf
```

**Issue: Workflow stuck**
```bash
# Check task status
curl http://localhost:8000/api/v1/tasks/task-uuid

# View workflow logs
docker compose logs leagent | grep workflow
```

### Getting Help

- GitHub Issues: Report bugs and feature requests
- Documentation: Full API reference
- Community: Join our discussion forum

---

## Next Steps

1. **Explore the Tool Catalog**: Browse all 60 available tools (including `code_execution`)
2. **Build a Workflow**: Create your first automated process
3. **Integrate Channels**: Connect to your team's messaging platform
4. **Define Rules**: Encode your business policies
5. **Use the Task System**: Create, monitor, and kill background tasks
6. **Read the Architecture Docs**: Understand tool concurrency, abort signals, and task lifecycle
7. **Monitor Performance**: Set up Grafana dashboards

Happy automating! 🚀
