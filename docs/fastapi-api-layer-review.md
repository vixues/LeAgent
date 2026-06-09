# LeAgent FastAPI Layer — Professional Review

> Scope: the HTTP/API layer of the LeAgent backend (`backend/leagent/api/`,
> `backend/leagent/main.py`, exception handlers, middleware, and the
> request/response contracts exposed to clients). Evaluated against the
> conventions of a production-grade FastAPI service.
>
> Status: assessment / recommendations. No code changes are implied by this
> document.

---

## 1. Executive Summary

The API layer already adopts several mature FastAPI practices: a lifespan-based
startup/shutdown flow, `Annotated` dependency injection, a global exception
handler set, a layered middleware chain (request ID, access log, API-version
headers, content-size limit, metrics, GZip), and Pydantic v2 request/response
models on a meaningful subset of routes.

However, the layer overall reads like a **fast-moving monolithic backend**
rather than a hardened public API. The most material gaps are in **contract
stability** (inconsistent error shapes and incomplete `response_model`
coverage), **architectural boundaries** (oversized router modules, deferred
route registration, business logic in controllers), and **security/operational
readiness** (CORS misconfiguration, no HTTP-level rate limiting, background
processing for heavy work).

The findings below are grouped by theme and tagged with a severity level:

- **[High]** — correctness, contract, or security impact; address first.
- **[Medium]** — maintainability or operational risk.
- **[Low]** — polish and consistency.

---

## 2. Architecture & Organization

### 2.1 [High] Oversized router modules

A handful of route files concentrate too many responsibilities:

| File | Approx. lines |
|------|--------------|
| `api/v1/chat.py` | ~3200 |
| `api/v1/models.py` | ~1245 |
| `api/v1/folders.py` | ~830 |
| `api/v1/files.py` | ~825 |

`chat.py` alone hosts request/response models, SSE streaming, the WebSocket
endpoint, session CRUD, attachments, agent-memory endpoints, and agent
orchestration. A production FastAPI codebase typically splits these by
resource/use case (e.g. `sessions.py`, `completions.py`, `ws.py`) and keeps the
router thin, delegating to services.

**Impact:** hard to navigate, review, and test; high merge-conflict surface;
unclear ownership boundaries.

### 2.2 [High] Deferred route registration adds complexity and a readiness race

Many routers (documents, files, workflow, coding-projects, activities, etc.) are
not registered in `create_app()`. Instead they are mounted later, during
post-startup warmup:

```python
# main.py (_post_startup_warmup)
if os.environ.get("LEAGENT_SKIP_LIFESPAN_DEFERRED_ROUTES") != "1":
    deferred_v1_router = APIRouter(prefix="/api/v1")
    deferred_v2_router = APIRouter(prefix="/api/v2")
    mount_v1_deferred_routes(deferred_v1_router)
    mount_v2_deferred_routes(deferred_v2_router)
    app.include_router(deferred_v1_router)
    app.include_router(deferred_v2_router)
```

Problems:

- **Readiness race:** the process can report `ready` while warmup is still in
  progress, so clients may receive `404` for routes that exist but are not yet
  mounted.
- **Test/production divergence:** tests set
  `LEAGENT_SKIP_LIFESPAN_DEFERRED_ROUTES=1` and re-mount the same routers in
  `conftest.py`. The code path exercised by tests differs from production.
- **Maintenance cost:** idempotency is tracked with per-router attribute flags
  to avoid double registration (405s).

**Recommendation:** keep lazy imports for cold-start performance, but register
all routers once in `create_app()`. Defer only the expensive *initialization*
(inside lifespan), not the `include_router` calls themselves.

### 2.3 [Medium] Schema governance is fragmented

A shared schema module exists (`leagent/schema/api.py` with `PaginatedResponse`,
`ErrorResponse`, etc.), but most request/response models are defined inline in
each `api/v1/*.py`. Some types are duplicated across modules (e.g. `MessageRole`
appears both in `schema/api.py` and inline in `chat.py`).

**Recommendation:** consolidate into `api/schemas/` (per-domain) and treat these
models as the canonical client contract, aligned with OpenAPI generation.

### 2.4 [Medium] `v2` versioning is nominal

`mount_v2_deferred_routes` imports `leagent.api.v2.chat` and
`leagent.api.v2.agents`, but `api/v2/` contains only an empty `__init__.py`.
Meanwhile `APIVersionMiddleware` emits `Deprecation`/`Sunset` headers for v1.
The versioning policy and the implementation are out of sync, which can mislead
clients.

**Recommendation:** either implement v2 or remove the deprecation/sunset
signaling until a real successor exists.

### 2.5 [Medium] Silent router-registration failures

Router mounting is wrapped in `try/except ImportError: pass` in many places. A
missing optional module is swallowed silently, so a route can simply fail to
exist with no operational signal.

**Recommendation:** log at `warning`/`error` level when an expected router fails
to import, or fail fast in non-optional cases.

---

## 3. API Contract & Type Safety

### 3.1 [High] Incomplete `response_model` coverage

Roughly half of the route handlers declare an explicit `response_model`. Many
endpoints return `dict[str, Any]` directly, for example:

```python
# api/v1/extensions.py
@router.get("")
async def list_extensions(...) -> dict[str, Any]:
    return {"packs": mgr.list_packs()}
```

**Impact:**

- Incomplete OpenAPI schema; clients/frontends cannot reliably generate types.
- No compile-time or test-time guard against response-shape drift.
- Risk of accidentally leaking internal fields.

### 3.2 [High] Inconsistent error-response shapes

The global handlers define a rich, uniform error structure
(`error`, `error_code`, `message`, `details`, `recovery`), but route code almost
never raises the domain `LeAgentError`. Instead it raises `HTTPException`, which
the Starlette handler maps to a different shape:

- `LeAgentError` → `{ error, error_code, message, details, recovery }`
- `HTTPException` → `{ error, error_code: "HTTP_<code>", message: str(detail), details: {} }`
- Some endpoints return ad-hoc bodies (e.g. `{"status": "not_initialized"}`).

Clients therefore have to handle multiple error formats, and none of them is
guaranteed to match the `ErrorResponse` model in `schema/api.py`.

**Recommendation:** standardize on one error envelope, register it as the
documented `responses` model, and prefer raising domain errors that map to it.

### 3.3 [Medium] Inconsistent pagination

- Default `page_size` varies across endpoints (20 / 50 / 200).
- Some endpoints use `page` + `page_size`; others use `limit` + `offset`.
- `has_next` is computed inconsistently — some use the `len(items) == page_size`
  heuristic, which can be off-by-one at exact-boundary pages.

**Recommendation:** adopt a single pagination convention and a shared dependency
that produces `PaginatedResponse[T]`.

---

## 4. Dependency Injection & Service Boundaries

### 4.1 [Medium] Global ServiceManager anti-pattern

```python
# api/deps.py
def get_service_manager(request: Request) -> "ServiceManager":
    from leagent.main import get_service_manager as _gsm
    return _gsm()
```

The `request` argument is unused; the function reads a module-level global.
Idiomatic FastAPI stores shared services on `app.state` (set in lifespan) and
reads them from `request.app.state` in a dependency. The current approach
complicates unit testing, multiple app instances, and hot-reload scenarios.

### 4.2 [Medium] Weakly typed dependencies

```python
def get_db_service(...) -> Any:
    return sm.db
```

`Any` return types defeat FastAPI's type inference and IDE support. Dependencies
should return concrete types (e.g. `DatabaseService`).

### 4.3 [Medium] Business logic in controllers

`chat.py`, `models.py`, and `coding_projects.py` contain DB queries, retries,
file handling, and agent construction directly in the route handlers. A service
layer exists (e.g. `ChatService`), but it is not applied consistently. The
"thin controller" principle (`Router → Service → Repository/Domain`) is only
partially realized.

### 4.4 [Medium] `build_agent_controller` is not a dependency

```python
# api/v1/chat_deps.py
def build_agent_controller():  # type: ignore[return]
    ...
```

It is invoked as a plain function rather than a FastAPI dependency, so it cannot
be overridden/mocked in tests or cached per request, and its return type is
suppressed.

---

## 5. Security

For a local-first single-user deployment some of these are acceptable today, but
they become **High** severity the moment a multi-user or network-exposed
deployment is supported.

### 5.1 [High] Authentication/authorization is a no-op

```python
# services/auth/deps.py
class PermissionChecker:
    def __init__(self, *keys: str, mode: str = "all") -> None:
        pass
    async def __call__(self, request: Request) -> UUID:
        return LOCAL_USER_ID
```

`PermissionChecker`, `require_permissions`, and role checks always allow. The
admin-gated endpoints (e.g. `/health/detailed`, `/health/metrics`) are not
actually protected. Acceptable for single-user local mode, but the API surface
implies access control that does not exist.

### 5.2 [High] CORS misconfiguration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_origins=["*"]` combined with `allow_credentials=True` is invalid per the
CORS spec; browsers will not honor credentialed wildcard origins. Use an
explicit origin allow-list, or disable credentials.

### 5.3 [Medium] No HTTP-level rate limiting

Tool execution has its own rate limit, but the REST API has no global throttling
(e.g. SlowAPI or a reverse-proxy policy). Chat, upload, and workflow endpoints
are susceptible to abuse.

### 5.4 [Medium] No security response headers / trusted hosts

No `TrustedHostMiddleware`, HSTS, `X-Content-Type-Options`, etc. This is a gap
for any internet-exposed deployment.

### 5.5 [Medium] WebSocket auth via query token

```python
# api/v1/chat.py
token_str = websocket.query_params.get("token")
```

Tokens passed as query parameters can leak into access logs, Referer headers,
and proxy logs. Prefer a first-message auth handshake or the
`Sec-WebSocket-Protocol` header.

### 5.6 [Medium] Upload size limit can be bypassed

`ContentSizeLimitMiddleware` only inspects the `Content-Length` header. Chunked
or header-less requests can bypass it. Enforce a streaming body limit and/or set
`client_max_body_size` at the reverse proxy.

### 5.7 [Low] Inconsistent protection on diagnostic endpoints

`/api/v1/health/memory` has no admin dependency and exposes internal subsystem
state, unlike `/detailed` and `/metrics`. Protection policy should be uniform.

---

## 6. Reliability & Operations

### 6.1 [Medium] `BackgroundTasks` used for heavy work

`files.py`, `documents.py`, and `pet_space.py` use `BackgroundTasks` for
non-trivial processing (document parsing, bundling). These tasks are lost on
restart, have no retry, and no persistence. Heavy/long work belongs in a durable
queue (Celery/ARQ or a persisted task table + worker).

### 6.2 [Medium] Migration failures are swallowed

```python
try:
    await _run_db_migrations()
except Exception:
    logger.warning("Database migration skipped (non-fatal)", exc_info=True)
```

The API can begin serving traffic with an inconsistent schema, surfacing as
runtime 500s rather than a clean startup failure.

### 6.3 [Low] Duplicated health surface

There are two health surfaces: the root `/health` (in `main.py`) and
`/api/v1/health/*` (live/ready/startup/detailed/metrics). Probe and monitoring
configuration should pick one to avoid semantic overlap.

### 6.4 [Medium] Error responses omit the request ID

The middleware injects `X-Request-ID`, but the JSON error bodies produced by
`register_exception_handlers` do not include `request_id`, which hampers
cross-service troubleshooting.

---

## 7. Testing & Documentation

### 7.1 [Medium] Narrow API test coverage

There are ~30 v1 route modules but only ~16 API-focused test files. Several
modules (`extensions`, `streams`, large parts of `folders`, `cron`) are
under-covered.

### 7.2 [Low] TestClient hides server-side exceptions

```python
with TestClient(app, raise_server_exceptions=False) as c:
    ...
```

This can mask unhandled exceptions — tests pass while production returns 500.
Consider enabling exception propagation for at least a subset of tests.

### 7.3 [Medium] OpenAPI is not treated as a first-class artifact

Disabling `/docs` in production is reasonable, but there is no schema export,
versioned OpenAPI document, or CI check aligning the schema with frontend
codegen. `ErrorResponse` is not registered as a global `responses` model.

---

## 8. Code-Quality Details

- **[Low]** Frequent `datetime.utcnow()` usage (deprecated in Python 3.12+);
  standardize on `datetime.now(UTC)`.
- **[Low]** `health.py` references `audit_router_auth.py`, which does not appear
  to exist — documentation drift from implementation.
- **[Low]** Mixed `HTTPException(detail=str(exc))` and bare `except Exception`
  handling can leak internal implementation details in error messages.

---

## 9. What the Codebase Does Well

These patterns are sound and worth preserving:

1. **Lifespan + ServiceManager** gives a clear startup/shutdown lifecycle.
2. **Middleware stack** is comprehensive (request ID, access log, API-version
   policy, content-size limit, metrics, GZip).
3. **Global exception handling** with a recovery-strategy concept is the right
   direction.
4. **Several modules** (`tools.py`, much of `health.py`) demonstrate good
   `response_model` + `Depends` usage.
5. **`PaginatedResponse[T]`** is a clean generic pagination abstraction.
6. **Chat layer** already attempts separation of concerns via `ChatService` and
   `chat_deps` (though not carried through end to end).

---

## 10. Prioritized Roadmap

| Priority | Action |
|----------|--------|
| **P0 — Contract & Security** | Register all routers at app-construction time (remove the deferred-route race); standardize on a single `ErrorResponse` envelope; fix CORS; add `response_model` to key endpoints. |
| **P1 — Maintainability** | Split `chat.py` and other oversized routers; centralize schemas under `api/schemas/`; inject `ServiceManager` via `app.state`; introduce real authorization if multi-user is on the roadmap. |
| **P2 — Production Readiness** | Move heavy work to a durable task queue; add HTTP rate limiting and security headers; include `request_id` in error bodies; broaden route-level integration tests; either deliver v2 or remove deprecation headers; enforce an OpenAPI CI check. |

---

## 11. Suggested Next Steps

Any single thread below can be taken on independently as a focused refactor:

1. **Unify the error response** — define one envelope, register it as the
   documented `responses` model, and convert ad-hoc `HTTPException` usage.
2. **Eliminate the deferred-routing race** — move `include_router` calls into
   `create_app()` while keeping lazy imports.
3. **Decompose `chat.py`** — extract schemas, WebSocket, and session CRUD into
   dedicated modules behind `ChatService`.
