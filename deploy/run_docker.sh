#!/bin/bash
# =============================================================================
# LeAgent — Docker Lifecycle Manager
# =============================================================================
#
# Usage:
#   ./run_docker.sh <command> [options]
#
# Commands:
#   init              First-time setup: generate .env from .env.example
#   build             Build the LeAgent Docker image
#   up                Start services (production by default)
#   down              Stop and remove containers
#   restart           Restart one or all services
#   logs              Tail service logs
#   status            Show container status and health summary
#   shell             Open an interactive shell inside the app container
#   migrate           Run database migrations (SQLite via run_migrations)
#   backup            Backup SQLite DB + data dirs to ./backups/
#   restore           Restore SQLite DB from a .db backup (stops container briefly)
#   health            Query /health endpoints for all running services
#   prune             Remove stopped containers and dangling images
#
# Mode flags (combine with up / build / down):
#   --dev             Use development compose overlay
#   --tools           Enable MailHog profile (dev overlay only)
#   --ocr             Build image with PaddleOCR target
#
# Other flags:
#   --no-build        Skip image rebuild on up
#   --version <tag>   Override image tag (default: latest)
#   --service <name>  Target a specific service (logs / restart / shell)
#   --file <path>     Path to a SQLite backup (.db) for restore
#   --help, -h        Show this help
#
# Environment (.env in this directory):
#   LEAGENT_SECRET_KEY   *** Required — openssl rand -hex 32 (also used for signed URLs)
#   LEAGENT_VERSION      Image tag (default: latest)
#   LEAGENT_HOST_PORT    Host port mapping (default: 8000)
#   DEEPSEEK_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY — at least one LLM key recommended
#
# Examples:
#   ./run_docker.sh init
#   ./run_docker.sh build
#   ./run_docker.sh up
#   ./run_docker.sh up --dev --tools
#   ./run_docker.sh logs --service leagent
#   ./run_docker.sh shell
#   ./run_docker.sh migrate
#   ./run_docker.sh backup
#   ./run_docker.sh restore --file ./backups/leagent-2026-04-14.db
#   ./run_docker.sh down
#   ./run_docker.sh down --volumes
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROJECT_NAME="leagent"
BACKUP_DIR="$SCRIPT_DIR/backups"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
APP_CONTAINER="leagent-backend"

# Compose file set (populated by parse_flags)
COMPOSE_FILES=(-f docker-compose.yml)
COMPOSE_PROFILES=()

# -----------------------------------------------------------------------------
# Colors
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()     { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()   { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()    { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()    { err "$*"; exit 1; }
header() { echo -e "\n${CYAN}${BOLD}▶ $*${NC}"; }

# -----------------------------------------------------------------------------
# Prerequisite check
# -----------------------------------------------------------------------------
require_cmd() {
    command -v "$1" &>/dev/null || die "'$1' is required but not installed."
}

check_docker() {
    require_cmd docker
    docker info &>/dev/null || die "Docker daemon is not running."
    # Prefer 'docker compose' (v2) over 'docker-compose' (v1)
    if docker compose version &>/dev/null 2>&1; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &>/dev/null; then
        DOCKER_COMPOSE="docker-compose"
        warn "Using legacy docker-compose v1. Consider upgrading to Docker Compose v2."
    else
        die "Neither 'docker compose' nor 'docker-compose' found."
    fi
}

# -----------------------------------------------------------------------------
# Compose wrapper — always runs from SCRIPT_DIR with selected files/profiles
# -----------------------------------------------------------------------------
dc() {
    local profile_args=()
    for p in "${COMPOSE_PROFILES[@]+"${COMPOSE_PROFILES[@]}"}"; do
        profile_args+=(--profile "$p")
    done
    $DOCKER_COMPOSE \
        --project-name "$PROJECT_NAME" \
        "${COMPOSE_FILES[@]}" \
        "${profile_args[@]}" \
        "$@"
}

# -----------------------------------------------------------------------------
# Parse global flags (modifies COMPOSE_FILES / COMPOSE_PROFILES / opts)
# -----------------------------------------------------------------------------
MODE_DEV=false
OPT_NO_BUILD=false
OPT_VOLUMES=false
OPT_VERSION="${LEAGENT_VERSION:-latest}"
OPT_SERVICE=""
OPT_BACKUP_FILE=""
BUILD_TARGET="production"
REMAINING_ARGS=()

parse_flags() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dev)
                MODE_DEV=true
                COMPOSE_FILES+=(-f docker-compose.dev.yml)
                shift ;;
            --tools)
                COMPOSE_PROFILES+=(tools)
                shift ;;
            --ocr)
                BUILD_TARGET="ocr"
                shift ;;
            --no-build)
                OPT_NO_BUILD=true
                shift ;;
            --volumes|-v)
                OPT_VOLUMES=true
                shift ;;
            --version)
                OPT_VERSION="$2"
                shift 2 ;;
            --service|-s)
                OPT_SERVICE="$2"
                shift 2 ;;
            --file)
                OPT_BACKUP_FILE="$2"
                shift 2 ;;
            --help|-h)
                sed -n '2,50p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
                exit 0 ;;
            *)
                REMAINING_ARGS+=("$1")
                shift ;;
        esac
    done
}

# -----------------------------------------------------------------------------
# .env helpers
# -----------------------------------------------------------------------------
load_env() {
    if [[ -f "$ENV_FILE" ]]; then
        # Export variables — skip comments and blank lines
        set -o allexport
        # shellcheck source=/dev/null
        source "$ENV_FILE"
        set +o allexport
    fi
}

assert_env_file() {
    if [[ ! -f "$ENV_FILE" ]]; then
        die ".env not found. Run './run_docker.sh init' first."
    fi
    if ! grep -q "^LEAGENT_SECRET_KEY=" "$ENV_FILE" || \
       grep -q "^LEAGENT_SECRET_KEY=$" "$ENV_FILE" || \
       grep -q "^LEAGENT_SECRET_KEY=CHANGE_ME" "$ENV_FILE" || \
       grep -q "^LEAGENT_SECRET_KEY=changeme" "$ENV_FILE"; then
        die "LEAGENT_SECRET_KEY is not set in .env. Run './run_docker.sh init' or edit .env manually."
    fi
}

# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------

# ── init ─────────────────────────────────────────────────────────────────────
cmd_init() {
    header "Initializing LeAgent deployment"

    # Create .env from example or scratch
    if [[ -f "$ENV_FILE" ]]; then
        warn ".env already exists — skipping creation (delete it to regenerate)"
    else
        if [[ -f "$ENV_EXAMPLE" ]]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            log "Copied .env.example → .env"
        else
            cat > "$ENV_FILE" <<'EOF'
# LeAgent — Docker .env (SQLite-only stack)
# ==========================================
# Secret: openssl rand -hex 32

LEAGENT_SECRET_KEY=CHANGE_ME
LEAGENT_VERSION=latest
LEAGENT_HOST_PORT=8000

DEEPSEEK_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
EOF
            log "Created default .env"
        fi

        # Auto-generate LEAGENT_SECRET_KEY
        if command -v openssl &>/dev/null; then
            SECRET=$(openssl rand -hex 32)
            sed -i "s/^LEAGENT_SECRET_KEY=.*/LEAGENT_SECRET_KEY=$SECRET/" "$ENV_FILE"
            ok "Generated LEAGENT_SECRET_KEY"
        else
            warn "openssl not found — set LEAGENT_SECRET_KEY manually in .env"
        fi
    fi

    # Create backup directory
    mkdir -p "$BACKUP_DIR"

    echo ""
    ok "Initialization complete."
    echo -e "  Next steps:"
    echo -e "    1. Review and edit ${CYAN}.env${NC} in this directory"
    echo -e "    2. ${CYAN}./run_docker.sh build${NC}"
    echo -e "    3. ${CYAN}./run_docker.sh up${NC}"
}

# ── build ─────────────────────────────────────────────────────────────────────
cmd_build() {
    header "Building LeAgent image  [target: $BUILD_TARGET, tag: $OPT_VERSION]"
    load_env
    export BUILD_TARGET

    dc build \
        --build-arg LEAGENT_VERSION="$OPT_VERSION" \
        --progress plain \
        "${OPT_SERVICE:-leagent}"

    ok "Image built successfully: leagent:$OPT_VERSION"
}

# ── up ────────────────────────────────────────────────────────────────────────
cmd_up() {
    header "Starting LeAgent services"
    assert_env_file
    load_env

    local up_flags=(--remove-orphans)
    $OPT_NO_BUILD || up_flags+=(--build)

    dc up -d "${up_flags[@]}"

    echo ""
    ok "Services started. Waiting for health checks..."
    sleep 4
    cmd_status_quiet
    echo ""

    local host_port="${LEAGENT_HOST_PORT:-8000}"
    echo -e "  ${CYAN}API:${NC}       http://localhost:${host_port}"
    echo -e "  ${CYAN}API docs:${NC}  http://localhost:${host_port}/docs"
    if $MODE_DEV; then
        echo -e "  ${CYAN}(dev overlay)${NC} source mounts + uvicorn --reload (see deploy/docker-compose.dev.yml)"
        echo -e "  ${CYAN}MailHog:${NC}   http://localhost:8025  (with --tools)"
    fi
    echo -e "  ${CYAN}SQLite:${NC}    persisted under Docker volume → /app/data/leagent.db"
    echo ""
    echo -e "  ${YELLOW}Tail logs:${NC}  ./run_docker.sh logs"
    echo -e "  ${YELLOW}Stop:${NC}       ./run_docker.sh down"
}

# ── down ─────────────────────────────────────────────────────────────────────
cmd_down() {
    header "Stopping LeAgent services"
    load_env

    if $OPT_VOLUMES; then
        warn "This will destroy Docker volumes (SQLite DB, uploads, logs, cache)"
        read -r -p "  Type 'yes' to confirm: " confirm
        [[ "$confirm" == "yes" ]] || { log "Aborted."; exit 0; }
        dc down --volumes --remove-orphans
    else
        dc down --remove-orphans
    fi

    ok "Services stopped."
}

# ── restart ───────────────────────────────────────────────────────────────────
cmd_restart() {
    header "Restarting ${OPT_SERVICE:-all services}"
    load_env

    if [[ -n "$OPT_SERVICE" ]]; then
        dc restart "$OPT_SERVICE"
    else
        dc restart
    fi

    ok "Restart complete."
}

# ── logs ─────────────────────────────────────────────────────────────────────
cmd_logs() {
    load_env
    local lines="${REMAINING_ARGS[0]:-200}"
    if [[ -n "$OPT_SERVICE" ]]; then
        dc logs -f --tail="$lines" "$OPT_SERVICE"
    else
        dc logs -f --tail="$lines"
    fi
}

# ── status ────────────────────────────────────────────────────────────────────
cmd_status_quiet() {
    dc ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || dc ps
}

cmd_status() {
    header "Service Status"
    load_env
    cmd_status_quiet
}

# ── shell ─────────────────────────────────────────────────────────────────────
cmd_shell() {
    local target="${OPT_SERVICE:-$APP_CONTAINER}"
    header "Opening shell in $target"
    load_env
    dc exec "$target" /bin/bash || dc exec "$target" /bin/sh
}

# ── migrate ───────────────────────────────────────────────────────────────────
cmd_migrate() {
    header "Running Alembic database migrations"
    load_env
    dc exec "$APP_CONTAINER" python -m leagent.scripts.run_migrations
    ok "Migrations complete."
}

# ── backup ────────────────────────────────────────────────────────────────────
cmd_backup() {
    header "Backing up LeAgent (SQLite + data dirs)"
    load_env
    mkdir -p "$BACKUP_DIR"

    local ts
    ts=$(date +%Y-%m-%d_%H%M%S)
    local db_file="$BACKUP_DIR/leagent-$ts.db"
    local vol_archive="$BACKUP_DIR/leagent-data-$ts.tar.gz"

    log "Copying SQLite database from container..."
    docker cp "$APP_CONTAINER:/app/data/leagent.db" "$db_file" 2>/dev/null \
        || warn "Could not copy leagent.db (first run?). Skipping DB file."
    [[ -f "$db_file" ]] && ok "Database → $db_file  ($(du -sh "$db_file" | cut -f1))"

    log "Archiving /app/data /app/uploads /app/cache from container..."
    docker run --rm \
        --volumes-from "$APP_CONTAINER" \
        -v "$BACKUP_DIR":/backup \
        alpine \
        tar czf "/backup/leagent-data-$ts.tar.gz" \
            /app/data /app/uploads /app/cache 2>/dev/null \
        || warn "Volume archive skipped (container may not be running)."
    [[ -f "$vol_archive" ]] && ok "Data archive → $vol_archive  ($(du -sh "$vol_archive" | cut -f1))"

    echo ""
    ok "Backup complete → $BACKUP_DIR"
}

# ── restore ───────────────────────────────────────────────────────────────────
cmd_restore() {
    [[ -n "$OPT_BACKUP_FILE" ]] || \
        die "Specify a backup file with --file <path>.  e.g. --file ./backups/leagent-2026-04-14.db"
    [[ -f "$OPT_BACKUP_FILE" ]] || die "Backup file not found: $OPT_BACKUP_FILE"

    header "Restoring SQLite database from $OPT_BACKUP_FILE"
    load_env
    warn "This overwrites /app/data/leagent.db inside the container."
    read -r -p "  Type 'yes' to confirm: " confirm
    [[ "$confirm" == "yes" ]] || { log "Aborted."; exit 0; }

    dc stop leagent >/dev/null 2>&1 || true
    docker cp "$OPT_BACKUP_FILE" "$APP_CONTAINER:/app/data/leagent.db"
    dc start leagent

    ok "Restore complete. Verify with ./run_docker.sh health"
}

# ── health ────────────────────────────────────────────────────────────────────
cmd_health() {
    header "Service Health Check"
    load_env

    local port="${LEAGENT_HOST_PORT:-8000}"
    local all_ok=true

    _hcheck() {
        local name="$1" url="$2"
        if curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
            ok "$name  →  $url"
        else
            warn "$name  →  $url  (no response)"
            all_ok=false
        fi
    }

    _hcheck "LeAgent API" "http://localhost:$port/health"

    if docker exec "$APP_CONTAINER" test -f /app/data/leagent.db 2>/dev/null; then
        ok "SQLite  →  /app/data/leagent.db (inside $APP_CONTAINER)"
    else
        warn "SQLite  →  /app/data/leagent.db not found yet (first boot may still be migrating)"
        all_ok=false
    fi

    echo ""
    if $all_ok; then
        ok "All services are healthy."
    else
        warn "One or more services did not respond. Check logs: ./run_docker.sh logs"
    fi
}

# ── prune ─────────────────────────────────────────────────────────────────────
cmd_prune() {
    header "Pruning Docker resources"
    warn "This removes stopped containers and dangling images for this project."
    read -r -p "  Continue? [y/N] " confirm
    [[ "${confirm,,}" == "y" ]] || { log "Aborted."; exit 0; }

    docker container prune -f --filter "label=com.docker.compose.project=$PROJECT_NAME"
    docker image prune -f
    ok "Prune complete."
}

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
print_usage() {
    echo -e "${BOLD}LeAgent Docker Lifecycle Manager${NC}"
    echo ""
    echo "Usage: ./run_docker.sh <command> [options]"
    echo ""
    echo -e "${CYAN}Commands:${NC}"
    printf "  %-12s %s\n" "init"    "First-time setup: copy .env.example → .env + secrets"
    printf "  %-12s %s\n" "build"   "Build the Docker image"
    printf "  %-12s %s\n" "up"      "Start all services"
    printf "  %-12s %s\n" "down"    "Stop and remove containers  [--volumes to wipe data]"
    printf "  %-12s %s\n" "restart" "Restart services  [--service <name>]"
    printf "  %-12s %s\n" "logs"    "Tail logs  [--service <name>] [<lines>]"
    printf "  %-12s %s\n" "status"  "Show container status and ports"
    printf "  %-12s %s\n" "shell"   "Interactive shell in app container"
    printf "  %-12s %s\n" "migrate" "Run DB migrations (python -m leagent.scripts.run_migrations)"
    printf "  %-12s %s\n" "backup"  "Backup SQLite DB + data dirs → ./backups/"
    printf "  %-12s %s\n" "restore" "Restore SQLite  --file <backup.db>"
    printf "  %-12s %s\n" "health"  "Query health endpoints for all services"
    printf "  %-12s %s\n" "prune"   "Remove stopped containers and dangling images"
    echo ""
    echo -e "${CYAN}Mode flags:${NC}"
    printf "  %-14s %s\n" "--dev"       "Development overlay (hot reload, exposed ports)"
    printf "  %-14s %s\n" "--tools"     "MailHog profile (use with --dev)"
    printf "  %-14s %s\n" "--ocr"       "Build with PaddleOCR target"
    printf "  %-14s %s\n" "--no-build"  "Skip image rebuild when running up"
    echo ""
    echo -e "Run ${CYAN}./run_docker.sh --help${NC} for full documentation."
}

main() {
    check_docker

    local command="${1:-}"
    shift || true

    # Parse all remaining flags (including positional remainders)
    parse_flags "$@"
    # Remaining positional args are in REMAINING_ARGS

    case "$command" in
        init)      cmd_init ;;
        build)     cmd_build ;;
        up|start)  cmd_up ;;
        down|stop) cmd_down ;;
        restart)   cmd_restart ;;
        logs|log)  cmd_logs ;;
        status|ps) cmd_status ;;
        shell|exec) cmd_shell ;;
        migrate)   cmd_migrate ;;
        backup)    cmd_backup ;;
        restore)   cmd_restore ;;
        health)    cmd_health ;;
        prune)     cmd_prune ;;
        --help|-h) print_usage ;;
        "")        print_usage ;;
        *)
            err "Unknown command: $command"
            echo ""
            print_usage
            exit 1
            ;;
    esac
}

main "$@"
