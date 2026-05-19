#!/usr/bin/env python3
"""Minimal stdio MCP server for integration tests.

Run: ``python -m tests.fixtures.mcp_mock_stdio`` (from ``leagent/backend``).

Speaks newline-delimited JSON-RPC compatible with :class:`leagent.mcp.client.MCPClient`.
"""

from __future__ import annotations

import sys

from tests.fixtures.mcp_mock_protocol import handle_mcp_line


def main() -> None:
    for line in sys.stdin:
        try:
            out = handle_mcp_line(line)
            if out is not None:
                sys.stdout.write(out + "\n")
                sys.stdout.flush()
        except Exception as exc:
            err = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(exc)},
            }
            import json

            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
