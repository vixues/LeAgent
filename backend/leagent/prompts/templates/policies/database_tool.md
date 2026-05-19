---
name: policies/database_tool
variant: default
description: Safe use of the real-database ``database`` tool (vs in-memory sql_query).
---

Database tool (`database`):

- **Not** the same as `sql_query`: `sql_query` runs **SELECT-only** SQL on **in-memory**
  tables / artifacts (pandasql). The `database` tool talks to a **real** SQLite file or,
  when explicitly enabled, PostgreSQL/MySQL over a URL.
- **Default**: use **SQLite** with `sqlite_path` under the session upload sandbox (same
  rules as other file tools). Prefer `create_sqlite` then `query` / `execute` for local
  analysis databases.
- **Remote URLs** (`database_url` with `kind` postgresql/mysql) are **disabled** unless
  the deployment sets **`LEAGENT_DATABASE_TOOL_REMOTE=1`**. Never point the tool at
  production servers unless the user and operators explicitly intend it.
- **`query`** accepts read-only SQL only (SELECT / WITH / EXPLAIN and a small allow-list
  of SQLite `PRAGMA` for introspection). Use **`execute`** for DML/DDL only when the user
  asked to modify schema or data.
- **`execute`** with `DROP`, `TRUNCATE`, or `ALTER … DROP` requires **`confirm_destructive: true`**
  and must reflect an explicit user request to delete or restructure data.
- Prefer **bound `params`** (named placeholders) instead of string-concatenating user text
  into SQL.
