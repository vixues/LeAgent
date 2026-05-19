"""Interactive agent REPL and one-shot mode.

Bootstraps :func:`leagent.cli.bootstrap.bootstrap_cli_services` (LLM, curated
``ToolRegistry`` from :func:`leagent.bootstrap.bootstrap_tools`, rules, skills)
then drives multi-turn work through :class:`~leagent.agent.controller.AgentController`,
which delegates the think/act loop to :class:`~leagent.agent.query_engine.QueryEngine`
when executing tools. Prompts are built with :class:`~leagent.prompts.builder.PromptBuilder`
and layered templates (persona, capabilities, policies, …).

This path **does not** persist chat history to ``SessionManager`` or attach the full
HTTP ``ServiceManager`` tool context — use the web UI or REST API for session-scoped
files, signed URLs, and ``AgentMemory`` integration.
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import click

from leagent.cli.utils import (
    console,
    create_table,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
)


# ── Slash-command registry ──────────────────────────────────────────

SLASH_COMMANDS: dict[str, str] = {
    "/help": "Show this help message",
    "/quit": "Exit the session (alias: /exit, /q)",
    "/clear": "Clear conversation history",
    "/mode": "Switch agent mode: /mode [react|plan_execute|hybrid]",
    "/tools": "List available tools",
    "/rules": "List loaded rule sets",
    "/skills": "List loaded skills",
    "/model": "Show or switch model: /model [name]",
    "/verbose": "Toggle verbose output",
    "/history": "Show conversation history",
    "/export": "Export session to JSON: /export [path]",
    "/status": "Show session status",
}

EXIT_COMMANDS = {"/quit", "/exit", "/q"}


# ── REPL session ────────────────────────────────────────────────────

class ChatSession:
    """Manages an interactive agent chat session."""

    def __init__(self, *, verbose: bool = False, debug: bool = False) -> None:
        self._verbose = verbose
        self._debug = debug
        self._session_id = uuid4()
        self._services = None
        self._agent = None
        self._history: list[dict[str, str]] = []

    async def start(self) -> None:
        """Bootstrap services and enter the REPL loop."""
        console.print()
        console.print("[bold cyan]LeAgent[/] — local agent (QueryEngine-backed, in-process tools)")

        from leagent.cli.bootstrap import bootstrap_cli_services

        with console.status("[dim]Initializing services...[/]"):
            self._services = await bootstrap_cli_services(debug=self._debug)

        if not self._services.is_ready:
            print_warning(
                "LLM provider not configured. Agent features are limited.\n"
                "Set API keys (e.g. DEEPSEEK_API_KEY, OPENAI_API_KEY) and/or edit ~/.leagent/providers.yaml "
                "(see ~/.leagent/.env.example after leagent init)."
            )
        else:
            self._agent = self._services.build_agent(verbose=self._verbose)
            model_info = ""
            try:
                providers = self._services.llm.list_providers()
                if providers:
                    model_info = f" ({providers[0]})"
            except Exception:
                pass
            print_success(f"Agent ready{model_info}")

        tool_count = len(self._services.tools.list_tools()) if self._services.tools else 0
        rule_count = len(self._services.rules.list_rule_sets()) if self._services.rules else 0
        print_dim(f"  {tool_count} tools | {rule_count} rule sets | session {str(self._session_id)[:8]}")
        console.print("[dim]Type /help for commands, /quit to exit[/]")
        console.print()

        await self._repl_loop()

    async def _repl_loop(self) -> None:
        """Main read-eval-print loop."""
        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: console.input("[bold green]> [/]")
                )
            except (EOFError, KeyboardInterrupt):
                console.print()
                print_dim("Goodbye.")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                should_exit = await self._handle_slash_command(user_input)
                if should_exit:
                    break
                continue

            await self._run_agent(user_input)

    async def _run_agent(self, message: str) -> None:
        """Send a message to the agent and stream the response."""
        self._history.append({"role": "user", "content": message})

        if self._agent is None:
            print_warning("No agent available (LLM not configured).")
            return

        from leagent.cli.stream_handler import CLIStreamHandler

        handler = CLIStreamHandler(verbose=self._verbose)

        # Allow Ctrl+C to abort the current run
        original_handler = signal.getsignal(signal.SIGINT)
        aborted = False

        def _abort_handler(sig: int, frame: Any) -> None:
            nonlocal aborted
            aborted = True
            self._agent.abort()
            console.print("\n[yellow]Aborting...[/]")

        try:
            signal.signal(signal.SIGINT, _abort_handler)

            console.print()
            response = await self._agent.run(
                user_input=message,
                session_id=self._session_id,
                stream_handler=handler,
            )

            if response.text:
                self._history.append({"role": "assistant", "content": response.text})
            if response.error:
                print_error(f"Agent error: {response.error}")

        except Exception as exc:
            print_error(f"Error: {exc}")
        finally:
            signal.signal(signal.SIGINT, original_handler)
            if aborted:
                print_dim("Run aborted.")
            console.print()

    async def _handle_slash_command(self, command: str) -> bool:
        """Handle a slash command. Returns True if session should exit."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in EXIT_COMMANDS:
            print_dim("Goodbye.")
            return True

        if cmd == "/help":
            self._show_help()
        elif cmd == "/clear":
            self._history.clear()
            print_success("Conversation history cleared.")
        elif cmd == "/verbose":
            self._verbose = not self._verbose
            print_info(f"Verbose mode: {'on' if self._verbose else 'off'}")
        elif cmd == "/tools":
            self._show_tools()
        elif cmd == "/rules":
            self._show_rules()
        elif cmd == "/skills":
            self._show_skills()
        elif cmd == "/history":
            self._show_history()
        elif cmd == "/status":
            self._show_status()
        elif cmd == "/mode":
            self._switch_mode(arg)
        elif cmd == "/model":
            self._show_model(arg)
        elif cmd == "/export":
            self._export_session(arg)
        else:
            print_warning(f"Unknown command: {cmd}. Type /help for available commands.")

        return False

    def _show_help(self) -> None:
        console.print()
        table = create_table(columns=[
            ("Command", {"style": "cyan", "min_width": 12}),
            ("Description", {}),
        ])
        for cmd, desc in SLASH_COMMANDS.items():
            table.add_row(cmd, desc)
        console.print(table)
        console.print()

    def _show_tools(self) -> None:
        if not self._services or not self._services.tools:
            print_info("No tools loaded.")
            return
        tools = self._services.tools.list_tools()
        if not tools:
            print_info("No tools registered.")
            return
        console.print()
        table = create_table(columns=[
            ("Tool", {"style": "cyan"}),
            ("Category", {}),
            ("Description", {}),
        ])
        for tool in sorted(tools, key=lambda t: t.name):
            desc = (tool.description or "")[:60]
            table.add_row(tool.name, tool.category.value if hasattr(tool.category, "value") else str(tool.category), desc)
        console.print(table)
        console.print()

    def _show_rules(self) -> None:
        if not self._services or not self._services.rules:
            print_info("No rule engine loaded.")
            return
        ids = self._services.rules.list_rule_sets()
        if not ids:
            print_info("No rule sets loaded.")
            return
        console.print()
        for rs_id in ids:
            rs = self._services.rules.get_rule_set(rs_id)
            if rs:
                console.print(f"  [cyan]{rs.id}[/] - {rs.name} ({len(rs.rules)} rules)")
        console.print()

    def _show_skills(self) -> None:
        if not self._services or not self._services.skills:
            print_info("No skills manager loaded.")
            return
        skills = self._services.skills.all_skills
        if not skills:
            print_info("No skills loaded.")
            return
        console.print()
        for skill in skills:
            status = "[green]active[/]" if skill.is_active else "[dim]inactive[/]"
            console.print(f"  [cyan]{skill.name}[/] ({skill.source.value}) {status}")
        console.print()

    def _show_history(self) -> None:
        if not self._history:
            print_info("No conversation history.")
            return
        console.print()
        for msg in self._history[-20:]:
            role = msg["role"]
            content = msg["content"][:200]
            if role == "user":
                console.print(f"  [green]you:[/] {content}")
            else:
                console.print(f"  [cyan]agent:[/] {content}")
        console.print()

    def _show_status(self) -> None:
        console.print()
        console.print(f"  [bold]Session:[/]  {self._session_id}")
        console.print(f"  [bold]Verbose:[/]  {self._verbose}")
        console.print(f"  [bold]LLM:[/]      {'ready' if self._services and self._services.llm else 'not configured'}")
        console.print(f"  [bold]Tools:[/]    {len(self._services.tools.list_tools()) if self._services and self._services.tools else 0}")
        console.print(f"  [bold]Rules:[/]    {len(self._services.rules.list_rule_sets()) if self._services and self._services.rules else 0}")
        console.print(f"  [bold]Turns:[/]    {len(self._history) // 2}")
        console.print()

    def _switch_mode(self, mode: str) -> None:
        from leagent.agent.base import AgentMode
        valid_modes = {m.value: m for m in AgentMode}

        if not mode:
            current = self._agent.config.mode.value if self._agent else "unknown"
            print_info(f"Current mode: {current}. Options: {', '.join(valid_modes)}")
            return

        if mode not in valid_modes:
            print_error(f"Invalid mode '{mode}'. Options: {', '.join(valid_modes)}")
            return

        if self._agent:
            self._agent.config.mode = valid_modes[mode]
            print_success(f"Mode switched to: {mode}")
        else:
            print_warning("No agent available.")

    def _show_model(self, model: str) -> None:
        if not model:
            if self._services and self._services.llm:
                providers = self._services.llm.list_providers()
                print_info(f"Providers: {', '.join(providers) if providers else 'none'}")
            else:
                print_info("LLM not configured.")
        else:
            print_info(f"Model switching not yet supported from CLI. Configure in providers.yaml.")

    def _export_session(self, path: str) -> None:
        if not self._history:
            print_warning("No history to export.")
            return

        target = Path(path) if path else Path(f"leagent_session_{str(self._session_id)[:8]}.json")
        data = {
            "session_id": str(self._session_id),
            "messages": self._history,
        }
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print_success(f"Session exported to {target}")


# ── Click commands ──────────────────────────────────────────────────

@click.command(name="chat")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.pass_context
def chat_cmd(ctx: click.Context, verbose: bool) -> None:
    """Interactive local agent REPL (tools + layered prompts; no HTTP session store)."""
    debug = ctx.obj.get("debug", False) if ctx.obj else False
    session = ChatSession(verbose=verbose, debug=debug)
    asyncio.run(session.start())


def run_one_shot(message: str, *, verbose: bool = False, debug: bool = False) -> None:
    """Run a single local agent turn (same bootstrap stack as ``leagent chat``)."""

    async def _run() -> None:
        from leagent.cli.bootstrap import bootstrap_cli_services
        from leagent.cli.stream_handler import CLIStreamHandler

        services = await bootstrap_cli_services(debug=debug)
        if not services.is_ready:
            print_error(
                "LLM not configured. Set DEEPSEEK_API_KEY / OPENAI_API_KEY / … "
                "or edit ~/.leagent/providers.yaml (see leagent init)."
            )
            sys.exit(1)

        agent = services.build_agent(verbose=verbose)
        handler = CLIStreamHandler(verbose=verbose)
        session_id = uuid4()

        console.print()
        response = await agent.run(
            user_input=message,
            session_id=session_id,
            stream_handler=handler,
        )
        if response.error:
            print_error(f"Agent error: {response.error}")
            sys.exit(1)
        console.print()

    asyncio.run(_run())
