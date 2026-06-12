"""Rich terminal :class:`~leagent.agent.base.StreamHandler` for CLI agent streaming.

Consumes the same ``StreamEvent`` stream emitted by :class:`~leagent.agent.controller.AgentController`
(``QueryEngine`` path) — tool panels, deltas, and summaries without the web UI.
"""

from __future__ import annotations

import json
import time
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from leagent.agent.base import AgentResponse, StreamHandler, ToolCall, ToolResult
from leagent.cli.utils import console, format_duration


class CLIStreamHandler:
    """Renders ``StreamEvent`` / tool traces from the local agent for the interactive REPL."""

    def __init__(
        self,
        *,
        verbose: bool = False,
        show_thinking: bool = True,
        show_tools: bool = True,
    ) -> None:
        self._verbose = verbose
        self._show_thinking = show_thinking
        self._show_tools = show_tools
        self._token_buffer: list[str] = []
        self._live: Live | None = None
        self._tool_count = 0
        self._start_time = time.monotonic()

    async def on_thinking(self, thought: str) -> None:
        if not self._show_thinking:
            return
        if not thought.strip():
            return
        truncated = thought[:300] + ("..." if len(thought) > 300 else "")
        console.print(f"  [dim italic]thinking: {truncated}[/]")

    async def on_tool_call(self, tool_call: ToolCall) -> None:
        self._tool_count += 1
        if not self._show_tools:
            return

        args_display = ""
        if tool_call.arguments and self._verbose:
            try:
                args_display = json.dumps(tool_call.arguments, ensure_ascii=False, indent=2)
                if len(args_display) > 200:
                    args_display = args_display[:200] + "..."
                args_display = f"\n{args_display}"
            except Exception:
                args_display = f"\n{tool_call.arguments}"

        console.print(
            f"  [bold cyan]> tool:[/] [white]{tool_call.name}[/]{args_display}"
        )

    async def on_tool_call_delta(self, payload: dict[str, Any]) -> None:
        """Streaming tool JSON — suppressed unless verbose (too noisy)."""
        if not self._verbose or not self._show_tools:
            return
        raw = payload.get("arguments_raw") or ""
        if isinstance(raw, str) and len(raw) > 120:
            raw = raw[:120] + "..."
        name = payload.get("name") or "?"
        console.print(f"  [dim]tool Δ {name}:[/] [dim]{raw}[/]")

    async def on_nested_agent_preview(self, payload: dict[str, Any]) -> None:
        if not self._verbose or not self._show_tools:
            return
        name = payload.get("name") or "?"
        console.print(f"  [dim]nested {name}[/]")

    async def on_tool_result(self, result: ToolResult) -> None:
        if not self._show_tools:
            return

        if result.success:
            content_preview = str(result.data or "")[:120]
            if len(str(result.data or "")) > 120:
                content_preview += "..."
            console.print(f"  [green]  ok[/] [dim]({result.duration_ms}ms)[/] {content_preview}")
        else:
            console.print(f"  [red]  err[/] {result.error}")

    async def on_user_input_request(self, payload: dict[str, Any]) -> None:
        qs = payload.get("questions") or []
        console.print(f"  [yellow]awaiting user input[/] ({len(qs)} question(s))")

    async def on_token(self, token: str) -> None:
        self._token_buffer.append(token)
        # Flush periodically to avoid per-char overhead
        if len(self._token_buffer) >= 5 or token.endswith(("\n", ".", "!", "?")):
            text = "".join(self._token_buffer)
            self._token_buffer.clear()
            console.print(text, end="", highlight=False)

    async def on_complete(self, response: AgentResponse) -> None:
        # Flush remaining tokens
        if self._token_buffer:
            console.print("".join(self._token_buffer), end="", highlight=False)
            self._token_buffer.clear()
        console.print()  # newline after streamed content

        if response.error:
            console.print(Panel(
                f"[red]Error:[/] {response.error}",
                title=response.terminal_reason.replace("_", " ").title(),
                border_style="red",
            ))
        elif self._verbose:
            elapsed = time.monotonic() - self._start_time
            parts = []
            if self._tool_count:
                parts.append(f"{self._tool_count} tool call(s)")
            if response.token_usage:
                total = response.token_usage.get("total_tokens", 0)
                if total:
                    parts.append(f"{total} tokens")
            parts.append(format_duration(elapsed, short=True))
            console.print(f"\n  [dim]{' | '.join(parts)}[/]")

    async def on_error(self, error: Exception) -> None:
        # Flush any partial output
        if self._token_buffer:
            console.print("".join(self._token_buffer), end="", highlight=False)
            self._token_buffer.clear()
        console.print()
        console.print(Panel(
            f"[red]{type(error).__name__}:[/] {error}",
            title="Error",
            border_style="red",
        ))
