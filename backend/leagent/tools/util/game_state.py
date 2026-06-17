"""Session-scoped game state tool for the Agent Chat Game Engine playbook."""

from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from leagent.tools.base import BaseTool, NonRetryableToolError, ToolCategory, ToolContext


def _default_game(game_id: str) -> dict[str, Any]:
    return {
        "game_id": game_id,
        "turn": 0,
        "score": 0,
        "phase": "init",
        "payload": {},
    }


class GameStateTool(BaseTool):
    """Read/write session-scoped game state for turn-based chat games."""

    name = "game_state"
    description = (
        "Manage session-scoped game state: init, read, update JSON payload, "
        "score, and reset. Use for turn-based chat game playbooks."
    )
    category = ToolCategory.UTIL
    is_read_only = False
    is_concurrency_safe = False
    search_hint = "game state turn score session persist"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["init", "read", "update", "score", "reset"],
                    "description": "Game state operation",
                },
                "game_id": {
                    "type": "string",
                    "description": "Game instance identifier within the session",
                },
                "payload": {
                    "type": "object",
                    "description": "JSON patch for update operation",
                },
                "advance_turn": {
                    "type": "boolean",
                    "default": False,
                    "description": "Increment turn counter on update",
                },
                "phase": {
                    "type": "string",
                    "description": "Optional phase label (init, playing, ended)",
                },
                "score_delta": {
                    "type": "number",
                    "description": "Score delta for score operation",
                },
                "score_absolute": {
                    "type": "number",
                    "description": "Set absolute score",
                },
                "rule_tag": {
                    "type": "string",
                    "description": "Optional scoring rule tag",
                },
                "reset_all": {
                    "type": "boolean",
                    "default": False,
                    "description": "Reset all games in session (reset op)",
                },
            },
            "required": ["operation"],
        }

    async def _load_games(self, context: ToolContext) -> dict[str, Any]:
        sm = getattr(context, "service_manager", None)
        session_id = context.session_id
        if sm is None or not session_id:
            return {}
        session_manager = getattr(sm, "session_manager", None)
        if session_manager is None:
            return {}
        try:
            state = await session_manager.load(UUID(session_id))
        except (TypeError, ValueError):
            return {}
        if state is None:
            return {}
        raw = (state.metadata or {}).get("game_states")
        return dict(raw) if isinstance(raw, dict) else {}

    async def _save_games(self, context: ToolContext, games: dict[str, Any]) -> None:
        sm = getattr(context, "service_manager", None)
        session_id = context.session_id
        if sm is None or not session_id:
            return
        session_manager = getattr(sm, "session_manager", None)
        if session_manager is None:
            return
        try:
            sid = UUID(session_id)
        except (TypeError, ValueError):
            return
        async with session_manager.locked(sid) as state:
            meta = dict(state.metadata or {})
            meta["game_states"] = games
            state.metadata = meta

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        operation = str(params.get("operation") or "").strip().lower()
        game_id = str(params.get("game_id") or "default").strip() or "default"
        games = await self._load_games(context)

        if operation == "init":
            games[game_id] = _default_game(game_id)
            phase = params.get("phase")
            if isinstance(phase, str) and phase.strip():
                games[game_id]["phase"] = phase.strip()
            payload = params.get("payload")
            if isinstance(payload, dict):
                games[game_id]["payload"] = copy.deepcopy(payload)
            await self._save_games(context, games)
            return {"game": games[game_id]}

        if operation == "read":
            game = games.get(game_id)
            if game is None:
                raise NonRetryableToolError(f"Game {game_id!r} not found")
            return {"game": game}

        if operation == "update":
            game = games.get(game_id)
            if game is None:
                game = _default_game(game_id)
                games[game_id] = game
            payload = params.get("payload")
            if isinstance(payload, dict):
                base = game.get("payload")
                if not isinstance(base, dict):
                    base = {}
                base.update(payload)
                game["payload"] = base
            phase = params.get("phase")
            if isinstance(phase, str) and phase.strip():
                game["phase"] = phase.strip()
            if params.get("advance_turn"):
                game["turn"] = int(game.get("turn") or 0) + 1
            await self._save_games(context, games)
            return {"game": game}

        if operation == "score":
            game = games.get(game_id)
            if game is None:
                # Match ComfyUI-style affordance: scoring implicitly creates the
                # state when the caller didn't init it in this session context.
                game = _default_game(game_id)
                games[game_id] = game
            if params.get("score_absolute") is not None:
                game["score"] = float(params["score_absolute"])
            elif params.get("score_delta") is not None:
                game["score"] = float(game.get("score") or 0) + float(params["score_delta"])
            rule_tag = params.get("rule_tag")
            if isinstance(rule_tag, str) and rule_tag.strip():
                history = game.setdefault("score_history", [])
                if isinstance(history, list):
                    history.append({"tag": rule_tag.strip(), "score": game["score"]})
            await self._save_games(context, games)
            return {"game": game}

        if operation == "reset":
            if params.get("reset_all"):
                games = {}
            else:
                games.pop(game_id, None)
            await self._save_games(context, games)
            return {"reset": game_id, "remaining": list(games)}

        raise NonRetryableToolError(f"Unknown operation: {operation}")


__all__ = ["GameStateTool"]
