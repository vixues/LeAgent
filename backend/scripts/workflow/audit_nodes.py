"""Print the node-schema snapshot (``/object_info`` equivalent).

Useful for diffing registered nodes between environments (e.g. CI vs
production). Outputs JSON to stdout.
"""

from __future__ import annotations

import asyncio
import json


async def _run() -> None:
    from leagent.workflow.nodes import bootstrap, get_registry

    await bootstrap()
    print(json.dumps(get_registry().snapshot(), indent=2, ensure_ascii=False))


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
