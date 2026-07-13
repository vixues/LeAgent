# Security Control Plane

LeAgent’s security control plane stops unauthenticated LAN access, reduces
information disclosure, and adds light multi-user isolation/quotas.

## Compulsory authentication

| Piece | Location |
|-------|----------|
| Instance access password | `$LEAGENT_HOME/security.json` (PBKDF2 hash) |
| Session JWT | HMAC via `LEAGENT_SECRET_KEY` / `$LEAGENT_HOME/secrets/.secret_key` |
| HTTP API | `POST /api/v1/auth/setup`, `/login`, `/logout`, `GET /me`, `/status` |
| Named users | `users` table + `GET/POST /api/v1/admin/users` |

### Enforce-auth policy

`LEAGENT_SECURITY_ENFORCE_AUTH` is tri-state:

- unset / `null` → **auto**: enforce when bind host is not loopback (and not desktop)
- `true` → always enforce
- `false` → never enforce (local/dev/tests)

Desktop (`LEAGENT_DESKTOP=1` / `LEAGENT_DESKTOP_MODE=1`) stays password-free unless
`require_unlock_on_desktop` was set at setup; it may call
`POST /api/v1/auth/desktop-bootstrap` on loopback.

## Defense in depth

- Rate limiting auto-enables when auth is enforced (`LEAGENT_SECURITY_RATE_LIMIT_*`)
- Metrics are bearer-gated when auth + `gate_diagnostics` are on
- OpenAPI docs disabled when auth is enforced (`gate_openapi`)
- Workflow prompt/execution lifecycle and workflow WebSockets require ownership / auth
- Signed URL secret refuses the weak `"leagent-local-secret"` fallback when auth is enforced

## Multi-user performance

- Keep `LEAGENT_WORKERS=1` with SQLite; use PostgreSQL for concurrent writers
- Per-user sandbox concurrency: `LEAGENT_SECURITY_MAX_CONCURRENT_PER_USER` (default 5)
- Startup logs warn on open bind + weak secret, and on SQLite + workers > 1

## Operator checklist (LAN)

1. Set a strong `LEAGENT_SECRET_KEY` (`openssl rand -hex 32`)
2. Prefer `ports: ["127.0.0.1:8000:8000"]` or put a reverse proxy + TLS in front
3. Open the UI once and complete **setup** (access password)
4. Optionally create named users under Admin → Users (`/api/v1/admin/users`)
5. Set `LEAGENT_SECURITY_CORS_ALLOW_ORIGINS` to your UI origin(s)
