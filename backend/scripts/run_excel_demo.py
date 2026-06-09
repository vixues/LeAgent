#!/usr/bin/env python
"""End-to-end demo: run the QueryEngine against an ``.xlsx`` workbook.

Exercises the full tool-calling pipeline **including** the filesystem
path sandbox introduced in the security hardening pass.  The script:

1. Stages (copies) the workbook into the sandbox uploads directory
   (``settings.files.upload_dir``) so the ``excel_reader`` tool can
   open it.
2. Registers the staged path as a per-request **attachment** on the
   ``ToolUseContext`` so the sandbox allow-list covers it.
3. Sends the user question through a real DeepSeek LLM and streams
   every event (tool calls, tool results, assistant deltas) to the
   terminal.

This mirrors ``tests/integration/test_deepseek_excel.py`` but is a
hand-runnable CLI you can point at any workbook + question.

Examples
--------

Run against the canonical fixture the integration test uses::

    DEEPSEEK_API_KEY=sk-... python scripts/run_excel_demo.py \\
        --question "What was total 2024 revenue and the best region?"

Run against your own workbook::

    DEEPSEEK_API_KEY=sk-... python scripts/run_excel_demo.py \\
        --xlsx ~/Downloads/q4-report.xlsx \\
        --question "Summarise the top 3 line items by profit."

Deliberately trigger a sandbox denial (for testing)::

    DEEPSEEK_API_KEY=sk-... python scripts/run_excel_demo.py \\
        --xlsx ~/Downloads/q4-report.xlsx \\
        --no-sandbox-stage \\
        --question "Read the file."

Environment
-----------

- ``DEEPSEEK_API_KEY`` *(required)* — your DeepSeek API key.
- ``DEEPSEEK_MODEL``   *(optional)* — default ``deepseek-v4-flash``.
- ``DEEPSEEK_BASE_URL``*(optional)* — default ``https://api.deepseek.com``.
- ``LEAGENT_TOOL_FILE_ROOTS`` *(optional)* — override sandbox roots.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

REPO_BACKEND = Path(__file__).resolve().parent.parent
if str(REPO_BACKEND) not in sys.path:
    sys.path.insert(0, str(REPO_BACKEND))


def _sandbox_uploads() -> Path:
    """Resolve the sandbox uploads directory from application settings."""
    from leagent.config.settings import get_settings

    return Path(get_settings().files.upload_dir)


SANDBOX_UPLOADS = _sandbox_uploads()


# ---------------------------------------------------------------------------
# Prompt — includes the file-access policy the production controller uses.
# ---------------------------------------------------------------------------

EXCEL_ANALYSIS_SYSTEM_PROMPT = """\
You are a data-analysis agent. You have been given the absolute path
to an Excel workbook (``.xlsx``) and a user question about its
contents.

Operating rules:

1. Always read the file before answering. Use the ``excel_reader``
   tool first to list sheets, then read the relevant sheet(s).
2. If the question requires computation the tool doesn't give you
   directly (sums, averages, ratios, sorting), write and run a
   short Python snippet via the ``code_execution`` tool.
3. Cite the sheet name and the concrete cells / columns behind
   every numeric claim.
4. When you have enough data, stop calling tools and produce a
   concise, well-formatted final answer (plain prose; use bullet
   lists only when they genuinely help).

Never fabricate figures. If the workbook doesn't contain the
information needed, say so explicitly.

File access policy (strict):
- You MUST only read or write files the user attached to this
  conversation (listed under "Attached files") or files generated as
  task outputs under the uploads directory.
- Do NOT call file_manager with ".", "/", or any path outside those
  attachments.
- Do NOT read source code, configuration files, or logs of this
  server.
- If a file path is needed that was not attached by the user, ask the
  user to provide or attach it.
"""


# ---------------------------------------------------------------------------
# Terminal rendering helpers (ANSI colours; disable on non-tty)
# ---------------------------------------------------------------------------


class _Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def magenta(self, text: str) -> str:
        return self._wrap("35", text)


# ---------------------------------------------------------------------------
# Sandbox staging
# ---------------------------------------------------------------------------


def _stage_in_sandbox(src: Path) -> Path:
    """Copy *src* into the sandbox uploads dir and return the new path."""
    SANDBOX_UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = SANDBOX_UPLOADS / src.name
    if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
        return dest
    shutil.copy2(src, dest)
    return dest


# ---------------------------------------------------------------------------
# LLM + registry wiring
# ---------------------------------------------------------------------------


def _build_llm_service():
    from leagent.llm.model_registry import ModelRegistry
    from leagent.llm.providers.deepseek import DeepSeekProvider
    from leagent.llm.registry import ProviderRegistry
    from leagent.llm.service import LLMService
    from leagent.llm.task_resolver import TaskResolver

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit(
            "DEEPSEEK_API_KEY is not set — export it before running the demo, e.g.\n"
            "    export DEEPSEEK_API_KEY=sk-..."
        )
    base_url = os.getenv("DEEPSEEK_BASE_URL", DeepSeekProvider.DEFAULT_BASE_URL)
    model = os.getenv("DEEPSEEK_MODEL", DeepSeekProvider.DEFAULT_MODEL)

    registry = ProviderRegistry()
    for name in ("deepseek",):
        registry.register(
            name,
            DeepSeekProvider(api_key=api_key, base_url=base_url, default_model=model),
            metadata={"vendor": "deepseek", "model": model},
        )

    model_registry = ModelRegistry()
    model_registry.load_from_config({
        "providers": [{
            "name": "deepseek",
            "type": "deepseek",
            "models": [{"name": model, "kind": "chat"}],
        }],
        "routing": {
            "tasks": {
                "chat": {"provider": "deepseek", "model": model},
                "fast": {"provider": "deepseek", "model": model},
            },
        },
    })
    resolver = TaskResolver(registry=registry, model_registry=model_registry)
    return LLMService(registry=registry, model_registry=model_registry, resolver=resolver), model


def _build_tool_registry():
    from leagent.bootstrap.tools import register_default_tools
    from leagent.tools.registry import ToolRegistry

    registry = ToolRegistry()
    register_default_tools(registry=registry)
    return registry


# ---------------------------------------------------------------------------
# Main coroutine
# ---------------------------------------------------------------------------


def _truncate(value: Any, limit: int = 280) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > limit:
        return text[:limit] + f" …(+{len(text) - limit} chars)"
    return text


async def _run(
    xlsx_path: Path,
    question: str,
    *,
    max_turns: int,
    max_tool_calls: int,
    stage_in_sandbox: bool,
    style: _Style,
) -> int:
    from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
    from leagent.file.sandbox import PathSandbox, _get_allowed_roots
    from leagent.tools.executor import ToolExecutor

    llm, model = _build_llm_service()
    registry = _build_tool_registry()
    executor = ToolExecutor(registry=registry, service_manager=None)

    # --- sandbox info ---
    sandbox_roots = _get_allowed_roots()
    print(style.dim(f"[sandbox] roots={[str(r) for r in sandbox_roots]}"))

    # Stage the xlsx inside the sandbox so the tool can access it.
    if stage_in_sandbox:
        staged = _stage_in_sandbox(xlsx_path)
        print(style.dim(f"[sandbox] staged {xlsx_path.name} → {staged}"))
    else:
        staged = xlsx_path
        safe = PathSandbox.is_safe(str(staged))
        label = style.green("inside sandbox") if safe else style.red("OUTSIDE sandbox")
        print(style.yellow(f"[sandbox] --no-sandbox-stage: {staged} ({label})"))

    tool_count = len(registry.list_tools())
    print(style.dim(f"[setup] model={model}  tools={tool_count}  workbook={staged}"))

    engine = QueryEngine(
        QueryEngineConfig(
            cwd=str(staged.parent),
            llm=llm,
            tools=registry,
            executor=executor,
            system_prompt=EXCEL_ANALYSIS_SYSTEM_PROMPT,
            model_tier="tier1",
            temperature=0.1,
            max_turns=max_turns,
            max_tool_calls_per_turn=max_tool_calls,
            agent_id="scripts/run_excel_demo",
            tool_extra={"attachments": [str(staged)]},
        )
    )

    user_prompt = (
        f"The Excel workbook is located at {staged}. "
        f"{question.strip()}"
    )

    print(style.bold("\n>>> USER"))
    print(user_prompt)
    print()

    turn_index = 0
    in_stream = False
    wall_start = time.monotonic()

    async for msg in engine.submit_message(user_prompt):
        mtype = msg.type
        data = msg.data or {}

        if mtype == "stream_delta":
            if not in_stream:
                print(style.bold("\n<<< ASSISTANT"))
                in_stream = True
            sys.stdout.write(str(data.get("content", "")))
            sys.stdout.flush()

        elif mtype == "assistant":
            if in_stream:
                print()
                in_stream = False

        elif mtype == "tool_use":
            if in_stream:
                print()
                in_stream = False
            turn_index += 1
            print(style.cyan(f"\n[tool #{turn_index}] {data.get('name')}  call_id={data.get('id')}"))
            print(style.dim("  input: " + _truncate(data.get("input"))))

        elif mtype == "tool_result":
            success = data.get("success", True)
            label = style.green("success") if success else style.red("DENIED" if "sandbox" in str(data.get("content", "")).lower() else "error")
            print(style.cyan(f"[tool result] {label}  call_id={data.get('tool_use_id')}"))
            content = data.get("content", "")
            print(style.dim("  output: " + _truncate(content, limit=400)))

        elif mtype == "system":
            level = data.get("level", "info")
            colour = style.yellow if level == "warning" else style.dim
            print(colour(f"[system:{level}] {data.get('message', '')}"))

        elif mtype == "result":
            if in_stream:
                print()
                in_stream = False
            reason = data.get("reason", "?")
            usage = data.get("usage", {})
            colour = style.green if reason == "completed" else style.red
            wall_sec = time.monotonic() - wall_start
            print(colour(f"\n--- finished ({reason}) in {wall_sec:.1f}s ---"))
            if usage:
                print(
                    style.dim(
                        "tokens: "
                        f"prompt={usage.get('prompt_tokens', 0)}  "
                        f"completion={usage.get('completion_tokens', 0)}  "
                        f"total={usage.get('total_tokens', 0)}"
                    )
                )
            print(style.dim(f"tool calls: {turn_index}"))
            if err := data.get("error"):
                print(style.red(f"error: {_truncate(err, 800)}"))
            return 0 if reason == "completed" else 1

    return 1


# ---------------------------------------------------------------------------
# Argparse entrypoint
# ---------------------------------------------------------------------------


def _default_xlsx_path() -> Path:
    """Fall back to the committed demo fixture used by the pytest suite."""
    from tests.fixtures.excel_analysis import ensure_excel_sample

    return ensure_excel_sample().path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the QueryEngine against an Excel workbook using DeepSeek.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--xlsx",
        type=Path,
        default=None,
        help="Path to an .xlsx file. Defaults to the bundled demo fixture.",
    )
    parser.add_argument(
        "--question",
        default=(
            "What was the total 2024 revenue, which region performed best, "
            "and which single product has the highest unit price?"
        ),
        help="Free-form analysis question to send to the agent.",
    )
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--max-tool-calls", type=int, default=4)
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colour codes (handy when piping to a file).",
    )
    parser.add_argument(
        "--no-sandbox-stage",
        action="store_true",
        help=(
            "Do NOT copy the xlsx into the sandbox uploads directory. "
            "Use this to test that the sandbox correctly denies access "
            "to files outside the allow-list."
        ),
    )
    args = parser.parse_args(argv)

    xlsx = args.xlsx or _default_xlsx_path()
    if not xlsx.exists():
        print(f"error: workbook not found: {xlsx}", file=sys.stderr)
        return 2

    style = _Style(enabled=sys.stdout.isatty() and not args.no_color)

    try:
        return asyncio.run(
            _run(
                xlsx.resolve(),
                args.question,
                max_turns=args.max_turns,
                max_tool_calls=args.max_tool_calls,
                stage_in_sandbox=not args.no_sandbox_stage,
                style=style,
            )
        )
    except KeyboardInterrupt:
        print("\n[aborted]", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
