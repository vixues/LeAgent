# API reference

All endpoints live under `/api/v1/workflow`. Authentication follows the
rest of the backend (JWT / cookie session).

## Flow CRUD

| Method | Path                                   | Description                              |
| ------ | -------------------------------------- | ---------------------------------------- |
| `POST`   | `/workflow/flows`                      | Create a flow.                           |
| `GET`    | `/workflow/flows`                      | Paginated list.                          |
| `GET`    | `/workflow/flows/recent?limit=10`      | Recent flows (sidebar widget).           |
| `GET`    | `/workflow/flows/{flow_id}`            | Get a single flow.                       |
| `PUT`    | `/workflow/flows/{flow_id}`            | Update (writes are canonicalized).       |
| `DELETE` | `/workflow/flows/{flow_id}`            | Soft-delete.                             |
| `POST`   | `/workflow/flows/{flow_id}/duplicate`  | Copy the flow into a new draft.          |
| `POST`   | `/workflow/flows/import`               | Import a canonical document.             |
| `GET`    | `/workflow/flows/{flow_id}/export`     | Export the canonical document.           |

`POST` and `PUT` accept the `data` field in either canonical or
authoring shape; the server converts to canonical before persisting.

## Prompt lifecycle

| Method | Path                                          | Description                    |
| ------ | --------------------------------------------- | ------------------------------ |
| `POST`   | `/workflow/prompts?flow_id={uuid}`            | Queue a run.                   |
| `POST`   | `/workflow/flows/{flow_id}/run`               | Convenience wrapper.           |
| `GET`    | `/workflow/prompts/{prompt_id}`               | Current status & history.      |
| `POST`   | `/workflow/prompts/{prompt_id}/cancel`        | Cancel.                        |
| `POST`   | `/workflow/prompts/{prompt_id}/pause`         | Pause.                         |
| `POST`   | `/workflow/prompts/{prompt_id}/resume`        | Resume (optional resume data). |

Submission body:

```jsonc
{
  "input_data":    { "key": "value" },
  "priority":      5,          // 0=highest, 10=lowest
  "trigger_type":  "manual",
  "session_id":    null,
  "extra_data":    {}
}
```

Response:

```jsonc
{
  "execution_id": "uuid",
  "prompt_id":    "uuid-string",
  "flow_id":      "uuid",
  "status":       "queued",
  "queue_position": 2,
  "message":      "Workflow execution queued"
}
```

## Execution history

| Method | Path                                               | Description              |
| ------ | -------------------------------------------------- | ------------------------ |
| `GET`    | `/workflow/flows/{flow_id}/executions`             | Flow-scoped history.     |
| `GET`    | `/workflow/executions/{execution_id}`              | Detail + node timeline.  |
| `POST`   | `/workflow/executions/{execution_id}/cancel`       | Cancel execution.        |
| `POST`   | `/workflow/executions/{execution_id}/pause`        | Pause execution.         |
| `POST`   | `/workflow/executions/{execution_id}/resume?flow_id=...` | Resume execution. |

## Validation + build

| Method | Path                                   | Description                              |
| ------ | -------------------------------------- | ---------------------------------------- |
| `POST`   | `/workflow/flows/{flow_id}/validate`   | Run structural validation.               |
| `POST`   | `/workflow/flows/{flow_id}/build`      | Compile + graph-hash without running.    |

## Node registry / admin

| Method | Path                                   | Description                              |
| ------ | -------------------------------------- | ---------------------------------------- |
| `GET`    | `/workflow/object_info`                | Snapshot of every registered node.       |
| `POST`   | `/workflow/admin/reload-nodes`         | Hot-reload the custom-nodes directory.   |
| `GET`    | `/workflow/admin/replacements`         | List deprecation replacements.           |
| `POST`   | `/workflow/admin/replacements`         | Register a replacement.                  |
| `DELETE` | `/workflow/admin/replacements`         | Remove a replacement.                    |

## WebSockets

- `WS /api/v1/workflow/ws/executions/{prompt_id}` — events for one prompt.
- `WS /api/v1/workflow/ws/executions` — fan-in monitor for all prompts.

Frame schema:

```jsonc
{
  "type":       "node_started" | "node_completed" | "node_failed" |
                "execution_started" | "execution_completed" |
                "execution_failed" | "execution_cancelled" |
                "execution_paused" | "execution_resumed" |
                "queue_position",
  "prompt_id":  "uuid-string",
  "node_id":    "optional-node-id",
  "data":       { /* type-specific payload */ },
  "timestamp":  "2026-04-21T12:34:56Z"
}
```
