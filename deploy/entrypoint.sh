#!/bin/bash
# =============================================================================
# LeAgent Entrypoint — SQLite-only container (no external DB / Redis / Milvus)
# =============================================================================

set -e

export LEAGENT_WORKERS=${LEAGENT_WORKERS:-1}
export LEAGENT_HOST=${LEAGENT_HOST:-0.0.0.0}
export LEAGENT_PORT=${LEAGENT_PORT:-8000}
export LEAGENT_LOG_LEVEL=${LEAGENT_LOG_LEVEL:-INFO}

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

init_directories() {
    log_info "Initializing directories..."
    mkdir -p /app/data /app/logs /app/uploads /app/cache /app/tmp
    mkdir -p /app/data/working/uploads /app/data/working/tmp /app/data/secrets 2>/dev/null || true
    log_success "Directories initialized"
}

run_migrations() {
    log_info "Running database migrations..."
    if [ "${LEAGENT_RUN_MIGRATIONS:-true}" = "false" ]; then
        log_warning "Database migrations disabled by LEAGENT_RUN_MIGRATIONS=false"
        return 0
    fi
    if [ -f "/app/alembic.ini" ]; then
        cd /app
        if python -m leagent.scripts.run_migrations; then
            log_success "Database migrations completed"
        elif [ "${LEAGENT_MIGRATIONS_REQUIRED:-true}" = "false" ]; then
            log_warning "Database migrations failed (non-fatal)"
        else
            log_error "Database migrations failed"
            return 1
        fi
    else
        log_warning "alembic.ini not found, skipping migrations"
    fi
}

health_check() {
    local max_attempts=60 attempt=1
    log_info "Performing health check..."
    while [ $attempt -le $max_attempts ]; do
        if curl -sf "http://localhost:${LEAGENT_PORT}/health" > /dev/null 2>&1; then
            log_success "Health check passed"
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
    done
    log_error "Health check failed after $max_attempts attempts"
    return 1
}

start_server() {
    log_info "Starting LeAgent (gunicorn + uvicorn workers)..."
    log_info "Workers: $LEAGENT_WORKERS | Host: $LEAGENT_HOST | Port: $LEAGENT_PORT"
    exec gunicorn leagent.main:app \
        --bind "${LEAGENT_HOST}:${LEAGENT_PORT}" \
        --workers "$LEAGENT_WORKERS" \
        --worker-class uvicorn.workers.UvicornWorker \
        --timeout 300 \
        --graceful-timeout 30 \
        --keep-alive 5 \
        --max-requests 10000 \
        --max-requests-jitter 1000 \
        --access-logfile - \
        --error-logfile - \
        --capture-output \
        --enable-stdio-inheritance
}

start_server_dev() {
    log_info "Starting LeAgent (uvicorn --reload)..."
    exec uvicorn leagent.main:app \
        --host "$LEAGENT_HOST" \
        --port "$LEAGENT_PORT" \
        --reload \
        --reload-dir /app/leagent \
        --log-level debug
}

start_supervisor() {
    log_info "Starting LeAgent with Supervisor..."
    exec supervisord -c /etc/supervisor/conf.d/leagent.conf
}

main() {
    local command="${1:-server}"
    echo "=============================================="
    echo "  LeAgent"
    echo "  Command: $command"
    echo "=============================================="

    init_directories

    case "$command" in
        server)
            run_migrations
            start_server
            ;;
        server-dev|dev)
            run_migrations
            start_server_dev
            ;;
        supervisor)
            run_migrations
            start_supervisor
            ;;
        migrate)
            run_migrations
            ;;
        shell)
            exec /bin/bash
            ;;
        worker)
            log_info "Starting background worker..."
            exec python -m leagent.cli.main worker
            ;;
        scheduler)
            log_info "Starting scheduler..."
            exec python -m leagent.cli.main scheduler
            ;;
        health)
            health_check
            ;;
        *)
            log_info "Executing custom command: $*"
            exec "$@"
            ;;
    esac
}

main "$@"
