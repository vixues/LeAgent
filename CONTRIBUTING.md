# Contributing to LeAgent

Thank you for your interest in contributing to LeAgent! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Submitting Changes](#submitting-changes)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)

## Code of Conduct

We are committed to providing a welcoming and inclusive experience for everyone. Please be respectful and considerate in all interactions.

## Getting Started

### Finding Issues

- Look for issues labeled `good first issue` for beginner-friendly tasks
- Issues labeled `help wanted` are open for community contribution
- Check the project roadmap for planned features

### Before You Start

1. Check if there's an existing issue for your proposed change
2. If not, create an issue to discuss the change before investing significant effort
3. Wait for maintainer feedback before starting work

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- Git

### Backend Setup

```bash
cd backend

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --extra dev

# Initialize configuration
uv run leagent init

# Run development server
uv run leagent app --reload
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Running Tests

```bash
# Backend tests
cd backend
uv run pytest tests/ -v

# Frontend tests
cd frontend
npm run test -- --run
```

## Submitting Changes

### Pull Request Process

1. **Fork** the repository and create your branch from `main`
2. **Make changes** following our coding standards
3. **Write tests** for new functionality
4. **Update documentation** as needed
5. **Run the test suite** to ensure nothing is broken
6. **Submit a pull request** with a clear description

### Branch Naming

Use descriptive branch names:
- `feature/add-new-tool` - New features
- `fix/login-redirect` - Bug fixes
- `docs/api-reference` - Documentation updates
- `refactor/tool-registry` - Code refactoring

### Commit Messages

Follow conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting (no code change)
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance

Example:
```
feat(tools): add Excel formula evaluation tool

- Implement formula parser
- Add support for common functions
- Include unit tests

Closes #123
```

## Coding Standards

### Python (Backend)

- Follow PEP 8 style guide
- Use type hints for function signatures
- Maximum line length: 100 characters
- Use `black` for formatting
- Use `ruff` for linting

```bash
# Format code
uv run ruff format leagent/

# Lint code
uv run ruff check leagent/
```

### TypeScript (Frontend)

- Follow ESLint configuration
- Use TypeScript strict mode
- Use functional components with hooks
- Prefer named exports

```bash
# Lint code
npm run lint

# Type check
npm run typecheck
```

### Documentation

- All public APIs must have docstrings
- Use Google-style docstrings for Python
- Include examples for complex functionality

```python
def process_document(file_path: str, options: dict | None = None) -> DocumentResult:
    """Process a document and extract structured data.
    
    Args:
        file_path: Path to the document file.
        options: Optional processing options.
            - extract_tables: Whether to extract tables (default: True)
            - ocr_enabled: Enable OCR for images (default: False)
    
    Returns:
        DocumentResult containing extracted text and metadata.
    
    Raises:
        FileNotFoundError: If the file does not exist.
        UnsupportedFormatError: If the file format is not supported.
    
    Example:
        >>> result = process_document("invoice.pdf", {"ocr_enabled": True})
        >>> print(result.text)
    """
```

## Testing

### Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── test_agent/          # Agent tests
├── test_tools/          # Tool tests
├── test_api/            # API endpoint tests
└── test_workflow/       # Workflow engine tests
```

### Writing Tests

- Use pytest for all tests
- Use fixtures for common setup
- Mock external services
- Aim for >80% code coverage

```python
import pytest
from leagent.tools.doc import PDFReaderTool

@pytest.fixture
def pdf_tool():
    return PDFReaderTool()

async def test_pdf_extraction(pdf_tool, sample_pdf_path):
    result = await pdf_tool.execute(
        context=None,
        file_path=sample_pdf_path
    )
    assert result.success
    assert "expected text" in result.data["text"]
```

### Running Specific Tests

```bash
# Run specific test file
uv run pytest tests/test_tools/test_pdf_reader.py -v

# Run tests matching pattern
uv run pytest -k "test_pdf" -v

# Run with coverage
uv run pytest --cov=leagent --cov-report=html
```

## Documentation

### Types of Documentation

1. **API Documentation**: Auto-generated from docstrings
2. **User Guide**: How to use features
3. **Developer Guide**: Architecture and internals
4. **Tutorials**: Step-by-step guides

### Building Documentation

```bash
cd docs
pip install -r requirements.txt
make html
```

### Adding Documentation

- Place user documentation in `docs/`
- Use Markdown format
- Include code examples
- Add screenshots for UI features

## Adding New Tools

To add a new tool:

1. Create tool file in appropriate category:
   ```
   backend/leagent/tools/<category>/new_tool.py
   ```

2. Implement the `BaseTool` interface:
   ```python
   from leagent.tools.base import BaseTool, ToolResult, ToolContext
   
   class NewTool(BaseTool):
       name = "new_tool"
       description = "Description of what this tool does"
       parameters = {
           "type": "object",
           "properties": {
               "param1": {"type": "string", "description": "..."}
           },
           "required": ["param1"]
       }
       
       async def execute(
           self,
           context: ToolContext,
           param1: str,
           **kwargs
       ) -> ToolResult:
           # Implementation
           return ToolResult(success=True, data={"result": "..."})
   ```

3. Register in category `__init__.py`

4. Add tests in `tests/test_tools/`

5. Update tool documentation

## Questions?

- Open an issue for questions
- Join our community discussions
- Check existing issues for similar questions

Thank you for contributing to LeAgent!
