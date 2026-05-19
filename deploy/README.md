# LeAgent — Docker (minimal)

Single **FastAPI** container with **SQLite** as the only database. No PostgreSQL, Redis, Milvus, or MinIO — matching `backend/leagent/config/settings.py` and the local **`./start.sh`** workflow.

## Prerequisites

- Docker Engine 24+ with Compose v2
- ~2 GB RAM for the image (more if you enable optional OCR build target)

## Quick start

```bash
cd deploy
cp .env.example .env
# Set LEAGENT_SECRET_KEY and at least one LLM API key in .env

docker compose up -d --build
# API: http://localhost:8000/docs
```

Or use the helper:

```bash
./run_docker.sh init
./run_docker.sh up
```

Data layout inside the container:

| Path | Purpose |
|------|---------|
| `/app/data` | `LEAGENT_HOME` — SQLite `leagent.db`, working dirs, secrets |
| `/app/uploads` | Chat attachments (`FILES_UPLOAD_DIR`) |
| `/app/logs` / `/app/cache` | Logs and cache volumes |

## Development overlay

Same image with bind mounts and **uvicorn --reload** (from repo root or `deploy/`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Optional **MailHog** (SMTP capture UI on port 8025):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile tools up -d
```

## Image build (CI parity)

```bash
cd /path/to/LeAgent   # repository root
docker build -f deploy/Dockerfile -t leagent:local .
```

## Parity with `./start.sh`

For day-to-day development (backend + frontend, `uv`, no Docker DB), prefer the repo root script:

```bash
./start.sh check
./start.sh          # backend + frontend
```

Docker here is for **packaged demos**, **CI**, or hosts where you only want one long-running API process with persisted volumes.

## Migrations

The container entrypoint runs `python -m leagent.scripts.run_migrations` unless `LEAGENT_RUN_MIGRATIONS=false`.

## Backup / restore

```bash
./run_docker.sh backup
./run_docker.sh restore --file ./backups/leagent-YYYY-mm-dd_HHMMSS.db
```
