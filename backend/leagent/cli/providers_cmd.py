"""CLI commands for ``providers.yaml`` via :class:`~leagent.llm.provider_config.ProviderConfigService` (same file the FastAPI ``LLMService`` reads)."""

from __future__ import annotations

from typing import Any

import click

from leagent.cli.utils import (
    console,
    create_table,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    status_badge,
)
from leagent.llm.provider_config import (
    PROVIDER_PRESETS,
    ProviderConfigService,
)


def _svc() -> ProviderConfigService:
    return ProviderConfigService()


@click.group(name="models")
def models_group() -> None:
    """Inspect or edit ``providers.yaml`` (tier1/tier2 routing, DeepSeek/OpenAI/Qwen/…)."""


@models_group.command(name="list")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all providers including disabled.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_providers(show_all: bool, as_json: bool) -> None:
    """List configured LLM providers and models."""
    svc = _svc()
    providers = svc.list_providers()
    default = svc.get_default()

    if not providers:
        print_warning("No providers configured. Run 'leagent init' or add providers manually.")
        return

    if as_json:
        import json

        data = {
            "default_provider": default.provider,
            "default_model": default.model,
            "providers": [p.to_dict() for p in providers],
        }
        console.print_json(json.dumps(data))
        return

    console.print()
    console.print(f"[dim]Default provider:[/] {default.provider or 'not set'}")
    console.print(f"[dim]Default model:[/] {default.model or 'not set'}")
    console.print()

    for provider in providers:
        if not show_all and not provider.enabled:
            continue

        is_default = provider.name == default.provider
        title = f"{provider.name} ({provider.type})"
        if is_default:
            title += " [cyan][default][/]"

        table = create_table(
            title=title,
            columns=[
                ("Model", {"style": "cyan"}),
                ("Tier", {}),
                ("Context Window", {"justify": "right"}),
                ("Default", {}),
            ],
        )

        for model in provider.models:
            model_name = model.get("name", "unknown")
            tier = model.get("tier", "-")
            context = model.get("context_window", "-")
            is_default_model = model_name == default.model and is_default

            table.add_row(
                model_name,
                tier,
                f"{context:,}" if isinstance(context, int) else str(context),
                "✓" if is_default_model else "",
            )

        console.print(f"  Status: {status_badge('enabled' if provider.enabled else 'disabled')}")
        console.print(table)
        console.print()


@models_group.command(name="add")
@click.option("--name", "-n", required=True, help="Provider name (e.g., 'openai', 'my-qwen').")
@click.option("--type", "-t", "provider_type", required=True,
              type=click.Choice(list(PROVIDER_PRESETS.keys())),
              help="Provider type.")
@click.option("--api-key", "-k", default="", help="API key for the provider.")
@click.option("--base-url", "-u", default="", help="Base URL for the API.")
@click.option("--enabled/--disabled", default=True, help="Enable the provider.")
def add_provider(
    name: str,
    provider_type: str,
    api_key: str,
    base_url: str,
    enabled: bool,
) -> None:
    """Add a new LLM provider configuration."""
    svc = _svc()

    data: dict[str, Any] = {
        "name": name,
        "type": provider_type,
        "enabled": enabled,
    }

    if api_key:
        data["api_key"] = api_key
    else:
        env_var = f"${{{name.upper()}_API_KEY}}"
        data["api_key"] = env_var

    if base_url:
        data["base_url"] = base_url

    try:
        svc.create_provider(data)
    except ValueError as exc:
        print_error(str(exc))
        raise click.Abort()

    print_success(f"Added provider '{name}' ({provider_type})")
    if not api_key:
        print_info(f"Set the API key via environment variable: {name.upper()}_API_KEY")


@models_group.command(name="remove")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def remove_provider(name: str, yes: bool) -> None:
    """Remove an LLM provider configuration."""
    svc = _svc()

    if svc.get_provider(name) is None:
        print_error(f"Provider '{name}' not found.")
        raise click.Abort()

    if not yes and not prompt_confirm(f"Remove provider '{name}'?"):
        print_info("Cancelled.")
        return

    svc.delete_provider(name)
    print_success(f"Removed provider '{name}'")


@models_group.command(name="test")
@click.argument("name", required=False)
@click.option("--model", "-m", default=None, help="Specific model to test.")
def test_provider(name: str | None, model: str | None) -> None:
    """Test connectivity to an LLM provider."""
    import asyncio

    svc = _svc()

    if not name:
        default = svc.get_default()
        name = default.provider
        if not name:
            print_error("No provider specified and no default set.")
            raise click.Abort()

    pc = svc.get_provider(name)
    if not pc:
        print_error(f"Provider '{name}' not found.")
        raise click.Abort()

    test_model = model or (pc.models[0].get("name") if pc.models else None)
    if not test_model:
        print_error("No model available to test.")
        raise click.Abort()

    console.print(f"Testing provider [cyan]{name}[/] with model [cyan]{test_model}[/]...")

    result = asyncio.run(svc.test_provider(name, test_model))
    if result.is_healthy:
        print_success(f"Provider '{name}' is working correctly. Latency: {result.latency_ms:.0f}ms")
    else:
        print_error(f"Provider test failed: {result.error}")
        raise click.Abort()


@models_group.command(name="set-default")
@click.argument("provider")
@click.argument("model", required=False)
def set_default(provider: str, model: str | None) -> None:
    """Set the default LLM provider and model."""
    svc = _svc()

    pc = svc.get_provider(provider)
    if not pc:
        print_error(f"Provider '{provider}' not found.")
        raise click.Abort()

    if not pc.enabled:
        print_warning(f"Provider '{provider}' is disabled. Enable it first.")

    chosen_model = model
    if not chosen_model and pc.models:
        chosen_model = pc.models[0].get("name", "")

    svc.set_default(provider, chosen_model or "")
    print_success(f"Default set to {provider}/{chosen_model or '(none)'}")


@models_group.command(name="pull")
@click.argument("model")
@click.option("--provider", "-p", default="ollama", help="Provider to pull from (ollama only).")
def pull_model(model: str, provider: str) -> None:
    """Pull/download a model (Ollama only)."""
    svc = _svc()

    pc = None
    for p in svc.list_providers():
        if p.name == provider or p.type == "ollama":
            pc = p
            break

    if not pc or pc.type != "ollama":
        print_error("Ollama provider not configured. Add it with: leagent models add --name ollama --type ollama")
        raise click.Abort()

    base_url = pc.base_url or "http://localhost:11434"

    console.print(f"Pulling model [cyan]{model}[/] from Ollama...")
    print_dim("This may take a while depending on model size.")

    try:
        import httpx

        with httpx.stream(
            "POST",
            f"{base_url}/api/pull",
            json={"name": model},
            timeout=None,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    import json

                    data = json.loads(line)
                    status_msg = data.get("status", "")
                    if "pulling" in status_msg.lower():
                        completed = data.get("completed", 0)
                        total = data.get("total", 0)
                        if total > 0:
                            pct = (completed / total) * 100
                            console.print(f"\r  {status_msg}: {pct:.1f}%", end="")
                    elif status_msg:
                        console.print(f"  {status_msg}")

        console.print()
        print_success(f"Model '{model}' pulled successfully.")

        models = list(pc.models)
        if not any(m.get("name") == model for m in models):
            models.append({"name": model, "tier": "tier2", "context_window": 32000})
            svc.update_provider(pc.name, {"models": models})
            print_info(f"Added '{model}' to Ollama provider configuration.")

    except Exception as e:
        print_error(f"Failed to pull model: {e}")
        raise click.Abort()
