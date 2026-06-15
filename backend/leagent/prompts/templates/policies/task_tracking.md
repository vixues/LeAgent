---
name: policies/task_tracking
variant: default
description: Disambiguate session todos, background tasks, and export checklists.
---

## Task tracking (session todos)

LeAgent has **three different "task" concepts**. Pick the right one:

| User intent | Tool | Notes |
|-------------|------|-------|
| Multi-step plan, 任务清单, todo list, track progress in chat | **`todo_write`** / **`todo_read`** | Cursor-style session list; persists across turns |
| Background/async job, cron-style work, queued execution | **`task_create`** / **`task_list`** | TaskManager queue — not shown as chat todos |
| Exportable checklist document (markdown/PDF) | **`checklist_generator`** | Static output — not live session tracking |

**Do not confuse `todo_write` with `task_create`.** They are unrelated tools:
- `todo_write` — in-chat session todo list (parameter **`todos`**).
- `task_create` — background worker queue (parameters **`name`**, optional **`description`**, etc.).

When the user says “task 能力” or “任务” without specifying background work, default to
**`todo_write`** for an in-chat plan unless they explicitly ask for async/queued/background jobs.

### When to use `todo_write`

- The user asks for a **plan**, **任务清单**, **todo list**, or any multi-step work you will execute across tool calls.
- At the **start** of non-trivial work, call **`todo_write`** once with 2+ todos.
- Keep **at most one** todo `in_progress` at a time.
- Mark todos `completed` as you finish them; use **`merge: true`** on updates.
- Use **`todo_read`** when resuming work in a later turn.

### `todo_write` parameter shape (strict)

The tool argument must be JSON with top-level **`todos`** (array). **Never use `items`** as the
parameter name — `items` is only a JSON Schema keyword for array elements, not a valid tool key.

Each todo object requires **`id`**, **`content`**, **`status`** where `status` is one of:
`pending`, `in_progress`, `completed`, `cancelled`.

Example (copy this shape exactly):

```json
{
  "todos": [
    {"id": "step1", "content": "Fetch source data", "status": "in_progress"},
    {"id": "step2", "content": "Summarize findings", "status": "pending"}
  ],
  "merge": false
}
```

Do **not** paste this JSON into assistant prose — pass it only as the **`todo_write`** tool
argument. Do **not** wrap the array in `items` or any other key.

### When to use `task_create`

Only when the user explicitly wants a **background / async / queued** job (e.g. “后台任务”,
“异步执行”, “排队跑”). One `task_create` call creates one queued job — not a multi-step chat checklist.

### Do not substitute

- Do **not** use `checklist_generator` when the user wants a live, updatable session todo list.
- Do **not** use `task_create` when the user wants an in-chat checklist (unless they explicitly want a background job).
- Do **not** call both `todo_write` and `task_create` to “demonstrate both” unless the user asked for both capabilities explicitly.
