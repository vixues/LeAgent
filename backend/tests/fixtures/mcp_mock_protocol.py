"""Shared JSON-RPC dispatch for MCP mock servers (stdio + HTTP /rpc).

Mirrors the subset of MCP that :class:`leagent.mcp.client.MCPClient` uses.
"""

from __future__ import annotations

import json
from typing import Any

from leagent.mcp.constants import MCP_PROTOCOL_VERSION


def _json_rpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_mcp_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC object from the client.

    Returns:
        A response dict to send back, or ``None`` for notifications (no body required).
    """
    if msg.get("jsonrpc") != "2.0":
        return _json_rpc_error(msg.get("id"), -32600, "Invalid Request")

    method = msg.get("method")
    if not isinstance(method, str):
        return _json_rpc_error(msg.get("id"), -32600, "Missing method")

    req_id = msg.get("id")
    params = msg.get("params") or {}

    # Notifications: no response (stdio mock must not print a line).
    if req_id is None and method.startswith("notifications/"):
        return None

    if method == "initialize":
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},
                "prompts": {},
                "resources": {},
            },
            "serverInfo": {"name": "leagent-mcp-mock", "version": "0.0.1"},
            # MCPServerInfo.from_dict reads top-level name/version in this codebase.
            "name": "leagent-mcp-mock",
            "version": "0.0.1",
        }
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    if method == "tools/list":
        tools = [
            {
                "name": "echo",
                "description": "Echo arguments as JSON text",
                "inputSchema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                },
            },
            {
                "name": "fail",
                "description": "Always returns isError",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "echo":
            text = json.dumps(arguments, ensure_ascii=False)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                },
            }
        if name == "fail":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": "intentional failure"}],
                    "isError": True,
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": f"unknown tool: {name}"}],
                "isError": True,
            },
        }

    if method == "prompts/list":
        prompts = [
            {
                "name": "greet",
                "description": "A test prompt",
                "arguments": [{"name": "name", "required": True}],
            }
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": prompts}}

    if method == "prompts/get":
        pname = params.get("name")
        args = params.get("arguments") or {}
        if pname == "greet":
            n = args.get("name", "world")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "description": "greeting",
                    "messages": [
                        {
                            "role": "user",
                            "content": {"type": "text", "text": f"Hello, {n}."},
                        }
                    ],
                },
            }
        return _json_rpc_error(req_id, -32602, f"Unknown prompt: {pname}")

    if method == "resources/list":
        resources = [
            {
                "uri": "mock://config",
                "name": "config",
                "description": "Mock resource",
                "mimeType": "application/json",
            }
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": resources}}

    if method == "resources/read":
        uri = params.get("uri")
        if uri == "mock://config":
            body = json.dumps({"ok": True, "uri": uri})
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": body,
                        }
                    ]
                },
            }
        return _json_rpc_error(req_id, -32602, f"Unknown resource: {uri}")

    return _json_rpc_error(req_id, -32601, f"Method not found: {method}")


def handle_mcp_line(line: str) -> str | None:
    """Parse one NDJSON line and return one NDJSON response line, or None."""
    line = line.strip()
    if not line:
        return None
    msg = json.loads(line)
    out = handle_mcp_message(msg)
    if out is None:
        return None
    return json.dumps(out, ensure_ascii=False)
