"""CLI command for first-time ``LEAGENT_HOME`` layout and templates.

Creates the on-disk home (default ``~/.leagent``), ``config.yaml``, ``providers.yaml``,
``.env.example``, optional sample rules/skills, and a generated JWT secret — the same
directories the FastAPI ``ServiceManager`` and layered prompts expect at runtime.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

import click

from leagent.cli.utils import (
    console,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    prompt_text,
)


@click.command(name="init")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing configuration files.",
)
@click.option(
    "--non-interactive",
    "-y",
    "non_interactive",
    is_flag=True,
    help="Run in non-interactive mode with defaults.",
)
@click.option(
    "--defaults",
    is_flag=True,
    help="Alias for --non-interactive / -y (accept defaults without prompts).",
)
@click.option(
    "--home",
    type=click.Path(),
    default=None,
    help="Custom LeAgent home directory.",
)
def init_cmd(force: bool, non_interactive: bool, defaults: bool, home: str | None) -> None:
    """Create ``LEAGENT_HOME`` trees, ``config.yaml``, ``providers.yaml``, and ``.env.example``.

    Use ``--non-interactive`` / ``--defaults`` / ``-y`` for CI or scripted installs.
    """
    if defaults:
        non_interactive = True
    from leagent.config.constants import (
        ALL_DIRS,
        CONFIG_PATH,
        PROVIDERS_PATH,
        SECRET_DIR,
        LEAGENT_HOME,
    )

    leagent_home = Path(home) if home else LEAGENT_HOME
    config_path = leagent_home / "config.yaml" if home else CONFIG_PATH
    providers_path = leagent_home / "providers.yaml" if home else PROVIDERS_PATH
    env_example_path = leagent_home / ".env.example"

    console.print()
    console.rule("[bold cyan]LeAgent Initialization[/]")
    console.print()
    console.print(f"  [dim]Home directory:[/] {leagent_home}")
    console.print()

    dirs_to_create = ALL_DIRS if not home else [
        leagent_home,
        leagent_home / "working",
        leagent_home / "secrets",
        leagent_home / "working" / "uploads",
        leagent_home / "working" / "outputs",
        leagent_home / "working" / "tmp",
        leagent_home / "logs",
        leagent_home / "templates",
        leagent_home / "rules",
        leagent_home / "skills",
        leagent_home / "workflows",
        leagent_home / "jobs",
        leagent_home / "sessions",
        leagent_home / "working" / "cache",
        leagent_home / "knowledge",
    ]

    console.print("[bold]Creating directories...[/]")
    for d in dirs_to_create:
        dir_path = Path(d)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            print_dim(f"  Created {dir_path}")
        except Exception as e:
            print_error(f"  Failed to create {dir_path}: {e}")
            raise click.Abort()

    print_success("Directories created successfully.")
    console.print()

    if config_path.exists() and not force:
        print_warning(f"Configuration file already exists at {config_path}")
        if not non_interactive and not prompt_confirm("Overwrite existing configuration?"):
            print_info("Skipping configuration file.")
        else:
            _create_config(config_path)
    else:
        _create_config(config_path)

    if providers_path.exists() and not force:
        print_warning(f"Providers file already exists at {providers_path}")
        if not non_interactive and not prompt_confirm("Overwrite existing providers config?"):
            print_info("Skipping providers file.")
        else:
            _create_providers_config(providers_path, non_interactive)
    else:
        _create_providers_config(providers_path, non_interactive)

    _create_env_example(env_example_path, force)

    secret_key_path = (Path(home) / "secrets" / ".secret_key" if home else SECRET_DIR / ".secret_key")
    if not secret_key_path.exists():
        _generate_secret_key(secret_key_path)

    # Scaffold sample rules
    rules_dir = leagent_home / "rules"
    sample_rule = rules_dir / "sample_rules.yaml"
    if not sample_rule.exists():
        _create_sample_rules(sample_rule)

    # Scaffold sample skill
    skills_dir = leagent_home / "skills"
    sample_skill_dir = skills_dir / "getting-started"
    sample_skill = sample_skill_dir / "SKILL.md"
    if not sample_skill.exists():
        _create_sample_skill(sample_skill_dir)

    console.print()
    console.rule("[bold green]Initialization Complete[/]")
    console.print()
    console.print("[bold]Next steps:[/]")
    console.print("  1. Edit configuration files in:", style="dim")
    console.print(f"     {leagent_home}")
    console.print("  2. Set up your environment variables (see .env.example)", style="dim")
    console.print("  3. Start the agent:", style="dim")
    console.print("     [cyan]leagent run[/]             (HTTP server on LEAGENT_PORT, default 7860)")
    console.print("     [cyan]leagent[/]                 (interactive agent mode)")
    console.print("     [cyan]leagent app start[/]       (start the HTTP server)")
    console.print("     [cyan]leagent config init[/]     (init project config in current dir)")
    console.print()


def _create_config(config_path: Path) -> None:
    """Create the main configuration file."""
    from leagent.config.config import Config, save_config

    console.print("[bold]Creating configuration file...[/]")

    try:
        config = Config()
        save_config(config, config_path)
        print_success(f"Configuration saved to {config_path}")
    except Exception as e:
        print_error(f"Failed to create configuration: {e}")
        raise click.Abort()


def _create_providers_config(providers_path: Path, non_interactive: bool) -> None:
    """Create the LLM providers configuration file."""
    import yaml

    console.print("[bold]Creating providers configuration...[/]")

    # DeepSeek V4 models. Legacy names are auto-migrated on startup.
    providers_config = {
        "default_provider": "deepseek",
        "default_model": "deepseek-v4-flash",
        "providers": [
            {
                "name": "deepseek",
                "type": "deepseek",
                "enabled": True,
                "api_key": "${DEEPSEEK_API_KEY}",
                "base_url": "https://api.deepseek.com",
                "models": [
                    {"name": "deepseek-v4-flash", "tier": "tier2", "context_window": 1000000},
                    {"name": "deepseek-v4-pro", "tier": "tier1", "context_window": 1000000},
                ],
            },
            {
                "name": "dashscope",
                "type": "qwen",
                "enabled": False,
                "api_key": "${DASHSCOPE_API_KEY}",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "models": [
                    {"name": "qwen-max", "tier": "tier1", "context_window": 32000},
                    {"name": "qwen-plus", "tier": "tier2", "context_window": 32000},
                    {"name": "qwen-turbo", "tier": "tier3", "context_window": 8000},
                    {"name": "qwen-long", "tier": "tier1", "context_window": 1000000},
                    {"name": "qwen2.5-72b-instruct", "tier": "tier1", "context_window": 128000},
                ],
            },
            {
                "name": "openai",
                "type": "openai",
                "enabled": False,
                "api_key": "${OPENAI_API_KEY}",
                "base_url": "https://api.openai.com/v1",
                "models": [
                    {"name": "gpt-4o", "tier": "tier1", "context_window": 128000},
                    {"name": "gpt-4o-mini", "tier": "tier2", "context_window": 128000},
                    {"name": "gpt-3.5-turbo", "tier": "tier3", "context_window": 16385},
                ],
            },
            {
                "name": "ollama",
                "type": "ollama",
                "enabled": False,
                "base_url": "http://localhost:11434",
                "models": [
                    {"name": "llama3.1:70b", "tier": "tier1", "context_window": 128000},
                    {"name": "llama3.1:8b", "tier": "tier2", "context_window": 128000},
                    {"name": "qwen2.5:7b", "tier": "tier3", "context_window": 32000},
                ],
            },
        ],
    }

    try:
        providers_path.parent.mkdir(parents=True, exist_ok=True)
        with open(providers_path, "w", encoding="utf-8") as f:
            yaml.dump(
                providers_config,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        print_success(f"Providers configuration saved to {providers_path}")
    except Exception as e:
        print_error(f"Failed to create providers configuration: {e}")


def _create_env_example(env_path: Path, force: bool) -> None:
    """Create a template .env.example file."""
    console.print("[bold]Creating .env.example template...[/]")

    if env_path.exists() and not force:
        print_info(f".env.example already exists at {env_path}")
        return

    env_content = """\
# LeAgent Environment Configuration
# Copy this file to .env and fill in your values

# =============================================================================
# Server Settings
# =============================================================================

# Server host and port
LEAGENT_HOST=0.0.0.0
LEAGENT_PORT=7860

# Number of worker processes (default: auto-detect based on CPU cores)
# LEAGENT_WORKERS=4

# Log level (debug, info, warning, error, critical)
LEAGENT_LOG_LEVEL=info

# Secret key for session encryption (generate with: openssl rand -hex 32)
LEAGENT_SECRET_KEY=

# =============================================================================
# Database Settings
# =============================================================================

# Default is SQLite (no extra services). Path empty → ~/.leagent/leagent.db
DB_DRIVER=sqlite+aiosqlite
# DB_SQLITE_PATH=

# Optional PostgreSQL (install drivers: pip install "leagent[postgresql]")
# DB_DRIVER=postgresql+asyncpg
# DB_HOST=localhost
# DB_PORT=5432
# DB_USER=leagent
# DB_PASSWORD=password
# DB_NAME=leagent

# Redis connection URL
REDIS_URL=redis://localhost:6379/0

# =============================================================================
# LLM Provider API Keys
# =============================================================================
#
# Default LLM stack uses DeepSeek (see LLM_TIER* / DEEPSEEK_*). Add DEEPSEEK_API_KEY to run.
# For Qwen instead, set DASHSCOPE_API_KEY and enable the dashscope entry in providers.yaml.

# DeepSeek (default)
DEEPSEEK_API_KEY=
# DEEPSEEK_MODEL=deepseek-v4-flash
# DEEPSEEK_BASE_URL=https://api.deepseek.com
# DEEPSEEK_THINKING_TYPE=enabled
# DEEPSEEK_REASONING_EFFORT=high

# OpenAI
OPENAI_API_KEY=

# Alibaba DashScope (Qwen)
DASHSCOPE_API_KEY=

# Anthropic (Claude)
ANTHROPIC_API_KEY=

# Azure OpenAI
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# =============================================================================
# Storage Settings
# =============================================================================

# MinIO / S3 compatible storage
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=leagent
MINIO_SECURE=false

# =============================================================================
# Channel Integrations
# =============================================================================

# DingTalk
DINGTALK_APP_KEY=
DINGTALK_APP_SECRET=
DINGTALK_AGENT_ID=

# Feishu (Lark)
FEISHU_APP_ID=
FEISHU_APP_SECRET=

# WeChat Work
WECHAT_WORK_CORP_ID=
WECHAT_WORK_AGENT_ID=
WECHAT_WORK_SECRET=

# =============================================================================
# Optional Features
# =============================================================================

# Enable debug mode (never enable in production)
DEBUG=false

# Enable OpenTelemetry tracing
OTEL_ENABLED=false
OTEL_ENDPOINT=http://localhost:4317

# Sentry error tracking
SENTRY_DSN=
"""

    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
        print_success(f"Environment template saved to {env_path}")
    except Exception as e:
        print_error(f"Failed to create .env.example: {e}")


def _generate_secret_key(secret_key_path: Path) -> None:
    """Generate a secure secret key."""
    console.print("[bold]Generating secret key...[/]")

    try:
        secret_key = secrets.token_hex(32)
        secret_key_path.parent.mkdir(parents=True, exist_ok=True)
        with open(secret_key_path, "w", encoding="utf-8") as f:
            f.write(secret_key)
        os.chmod(secret_key_path, 0o600)
        print_success("Secret key generated and saved.")
        print_dim(f"  Location: {secret_key_path}")
    except Exception as e:
        print_error(f"Failed to generate secret key: {e}")


def _create_sample_rules(sample_rule: Path) -> None:
    """Create a sample rule set YAML file."""
    console.print("[bold]Creating sample rule set...[/]")
    sample_rule.parent.mkdir(parents=True, exist_ok=True)
    sample_rule.write_text(
        "id: sample-rules\n"
        "name: Sample Rules\n"
        "description: Example rule set — customize or replace with your own\n"
        "version: '1.0.0'\n"
        "enabled: true\n"
        "tags: [example]\n"
        "rules:\n"
        "  - id: amount-threshold\n"
        '    name: "Amount Limit Check"\n'
        "    condition:\n"
        "      type: threshold\n"
        "      params:\n"
        '        value: "{{amount}}"\n'
        "        max: 10000\n"
        "    severity: warning\n"
        '    message: "Amount {{amount}} exceeds threshold of 10000"\n'
        "    enabled: true\n",
        encoding="utf-8",
    )
    print_dim(f"  Created {sample_rule}")


def _create_sample_skill(skill_dir: Path) -> None:
    """Create a sample skill with SKILL.md."""
    console.print("[bold]Creating sample skill...[/]")
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "description: Getting started guide for LeAgent skills\n"
        "when_to_use: When the user asks about LeAgent features or how to create skills\n"
        "category: general\n"
        "tags: [help, guide]\n"
        "---\n\n"
        "# Getting Started with LeAgent Skills\n\n"
        "LeAgent skills are markdown-based knowledge modules that provide the agent\n"
        "with specialized instructions for different task types.\n\n"
        "## Creating a Skill\n\n"
        "1. Run `leagent skills init my-skill` to scaffold a new skill\n"
        "2. Edit the generated SKILL.md file with your instructions\n"
        "3. The agent will automatically discover and use your skill\n\n"
        "## Skill Structure\n\n"
        "Each skill is a directory containing a `SKILL.md` file with:\n"
        "- **YAML frontmatter**: metadata (description, tags, when_to_use)\n"
        "- **Markdown body**: the actual instructions for the agent\n\n"
        "## Skill Locations\n\n"
        "- **Bundled**: Ship with LeAgent (skills/builtin/)\n"
        "- **User**: ~/.leagent/skills/ (personal skills)\n"
        "- **Project**: .leagent/skills/ (project-specific)\n",
        encoding="utf-8",
    )
    print_dim(f"  Created {skill_md}")
