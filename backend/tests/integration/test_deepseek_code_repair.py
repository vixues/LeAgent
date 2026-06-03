"""Optional live DeepSeek test: sandbox script repair via ``code_workspace_edit``.

Skipped when ``DEEPSEEK_API_KEY`` is unset. Offline coverage lives in
``test_edit_repair_offline.py`` (no key required).

    uv run pytest tests/integration/test_deepseek_code_repair.py -m live -v
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.conftest import (
    drive_query_engine,
    requires_live_deepseek,
)
from tests.integration.test_edit_repair_offline import _assert_script_repair_trace

pytestmark = [pytest.mark.integration, pytest.mark.live, requires_live_deepseek]

SCRIPT_REPAIR_PROMPT = """\
You are testing the sandbox repair workflow. Follow these steps exactly:

1. Call ``code_execution`` once with this exact ``source`` (do not fix it first):

```python
def add_values():
    return 17 + 25

print(add_values()
```

2. When the run fails with a syntax error, patch ``__last_source__.py`` with
   ``code_workspace_edit`` (add the missing ``)`` on the ``print`` line).
   Do **not** resend the full program via ``source``.

3. Re-run with ``code_execution`` using ``workspace_file=__last_source__.py``.

4. Stop calling tools and answer with a single sentence that includes 42.
"""


@pytest.mark.asyncio
async def test_live_deepseek_script_repair_via_workspace_edit(
    deepseek_llm,
    full_tool_registry,
    tmp_path,
) -> None:
    from leagent.agent.script_agent import build_script_agent_engine

    engine = build_script_agent_engine(
        llm=deepseek_llm,
        tools=full_tool_registry,
        cwd=str(tmp_path),
        model_tier="tier2",
        max_turns=12,
        max_tool_calls_per_turn=4,
        temperature=0.1,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    trace = await drive_query_engine(engine, SCRIPT_REPAIR_PROMPT, timeout=300.0)
    _assert_script_repair_trace(trace)
