---
name: playbooks/game_engine
variant: default
description: Agent Chat Game Engine playbook — session-scoped turn-based games.
requires_tools:
  - game_state
---

## Agent Chat Game Engine playbook

Use this playbook when running turn-based games, quizzes, or scored interactions
inside a chat session.

### `game_state` operations

| Operation | When to use |
|-----------|-------------|
| **`init`** | Start a new game instance (`game_id`, optional `payload`, `phase`) |
| **`read`** | Inspect current turn, score, phase, and payload |
| **`update`** | Apply player actions; set `advance_turn=true` when a turn completes |
| **`score`** | Apply `score_delta` or `score_absolute`; optional `rule_tag` for audit |
| **`reset`** | Clear one game or `reset_all` for the session |

### Rules

- Pick a stable `game_id` per game type (e.g. `trivia`, `dungeon`) and reuse it
  for the session.
- Persist narrative state in `payload` (JSON object); keep keys flat and
  documented in your replies.
- After each turn: `update` → optional `score` → summarise state for the player
  in plain language.
- Never store secrets the player should not see inside `payload` if you echo
  tool results back to the user.

### Do not

- Do not simulate game state in free-form prose when `game_state` is available.
- Do not reset games without the user asking to restart.
