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

### When to use `todo_write`

- The user asks for a **plan**, **任务清单**, **todo list**, or any multi-step work you will execute across tool calls.
- At the **start** of non-trivial work, call `todo_write` with 2+ items (`id`, `content`, `status`).
- Keep **at most one** item `in_progress` at a time.
- Mark items `completed` as you finish them; use `merge: true` for updates.
- Use `todo_read` when resuming work in a later turn.

### Do not substitute

- Do **not** use `checklist_generator` when the user wants a live, updatable session todo list.
- Do **not** use `task_create` when the user wants an in-chat checklist (unless they explicitly want a background job).
