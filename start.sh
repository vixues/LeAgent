#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# LeAgent — single-node start script (macOS / Ubuntu / Debian)
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Environment (.env) ──────────────────────────────────────────
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$SCRIPT_DIR/.env"
    set +a
fi

# ── Defaults ────────────────────────────────────────────────────
BACKEND_DIR="$SCRIPT_DIR/backend"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$BACKEND_DIR/.venv}"

BACKEND_PORT="${PORT:-7860}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
HOST="${HOST:-0.0.0.0}"
LOG_DIR="${LEAGENT_LOG_DIR:-$SCRIPT_DIR/logs}"
MODE="dev"
STREAM_LOGS=1
FORCE_UV_SYNC=0
UV_SYNC_EXTRAS="${UV_SYNC_EXTRAS:-dev browser}"
LOG_RETENTION="${LEAGENT_LOG_RETENTION:-5}"
SHUTDOWN_GRACE_SEC="${LEAGENT_SHUTDOWN_GRACE_SEC:-5}"

export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

CHILD_PIDS=()
SPAWNED_LOG_FILES=()
TAIL_PID=""

# Predictable file permissions in production.
umask 022

# ── Platform detection ──────────────────────────────────────────
PLATFORM="unknown"
case "$(uname -s)" in
    Linux*)  PLATFORM="linux"  ;;
    Darwin*) PLATFORM="macos"  ;;
    MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
esac

# ── Terminal colours (disabled when piped or dumb terminal) ─────
if [ -t 1 ] && [ "${TERM:-dumb}" != "dumb" ]; then
    RED='\033[0;31m'  GREEN='\033[0;32m'  YELLOW='\033[1;33m'
    BLUE='\033[0;34m' CYAN='\033[0;36m'   BOLD='\033[1m'
    DIM='\033[2m'     NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' DIM='' NC=''
fi

# ── Output helpers ──────────────────────────────────────────────
info()    { printf "  ${BLUE}▸${NC} %b\n" "$*"; }
success() { printf "  ${GREEN}✔${NC} %b\n" "$*"; }
warn()    { printf "  ${YELLOW}⚠${NC}  %b\n" "$*" >&2; }
fail()    { printf "  ${RED}✘${NC} %b\n" "$*" >&2; exit 1; }
step()    { printf "\n${BOLD}%s${NC}\n" "$*"; }

_elapsed() {
    local start="$1" now
    now="$(date +%s)"
    echo "$(( now - start ))s"
}

_leagent_version() {
    local ver=""
    if [ -f "$BACKEND_DIR/pyproject.toml" ]; then
        ver="$(grep -m1 '^version' "$BACKEND_DIR/pyproject.toml" \
            | sed 's/.*=\s*"\(.*\)".*/\1/' 2>/dev/null || true)"
    fi
    echo "${ver:-dev}"
}

# ── Banner ──────────────────────────────────────────────────────
print_banner() {
    printf "${CYAN}\n"
    if [ "$MODE" = "prod" ]; then
        cat <<'BANNER'
  ╭──────────────────────────────────────────────────────────╮
  │          LeAgent  ──  Production Environment             │
  │                                                          │
  │  Backend   FastAPI  HTTP/WS/SSE  QueryEngine             │
  │  Frontend  React 19  Vite  ReactFlow                     │
  ╰──────────────────────────────────────────────────────────╯
BANNER
    else
        cat <<'BANNER'
  ╭──────────────────────────────────────────────────────────╮
  │          LeAgent  ──  Development Environment            │
  │                                                          │
  │  Backend   FastAPI  HTTP/WS/SSE  QueryEngine             │
  │  Frontend  React 19  Vite  ReactFlow                     │
  ╰──────────────────────────────────────────────────────────╯
BANNER
    fi
    printf "${NC}"
    info "version  ${BOLD}$(_leagent_version)${NC}"
    info "platform ${BOLD}${PLATFORM}${NC}   mode ${BOLD}${MODE}${NC}"
    if [ "$MODE" = "prod" ]; then
        info "app      ${DIM}http://${HOST}:${BACKEND_PORT}${NC}  ${DIM}(API + static UI)${NC}"
    else
        info "backend  ${DIM}http://${HOST}:${BACKEND_PORT}${NC}"
        info "frontend ${DIM}http://localhost:${FRONTEND_PORT}${NC}"
    fi
    echo ""
}

# ── Help ────────────────────────────────────────────────────────
print_help() {
    cat <<'EOF'
Usage: ./start.sh [command] [options]

Commands:
  all            Start backend + frontend (default)
  backend        Start backend only
  frontend       Start frontend only
  check          Run environment readiness check
  status         Show whether services are running on configured ports
  fix-deps       Install or upgrade missing local dependencies
  sync-python    Lock + sync Python dependencies
  build-frontend Build the frontend for production (npm run build)
  log [name]     Tail logs (all services, or single service)
  stop           Kill running LeAgent processes on configured ports

Options:
  --dev          Development mode (default)
  --prod         Production mode (builds frontend, multi-worker backend)
  --quiet        Do not stream logs to terminal
  --sync-python  Force uv sync before backend start
  --help, -h     Show this help

Requirements:
  git, uv, npm, Node.js 20.19+ or 22.12+ (required by Vite 7)

Environment:
  PORT                    Backend port          (default: 7860)
  FRONTEND_PORT           Frontend port         (default: 5173)
  HOST                    Backend bind address  (default: 0.0.0.0)
  LEAGENT_LOG_DIR         Log directory         (default: ./logs)
  LEAGENT_LOG_RETENTION   Rotated log copies    (default: 5)
  LEAGENT_SHUTDOWN_GRACE_SEC  SIGTERM grace period (default: 5)
  UV_SYNC_EXTRAS          uv extras             (default: dev browser)
  LEAGENT_SKIP_PLAYWRIGHT_INSTALL  set to 1 to skip `playwright install` after uv sync
  (markers: backend/.playwright_chromium_marker, backend/.playwright_system_deps_marker)
  LEAGENT_PLAYWRIGHT_MIRROR        set to 1 to use a common npm mirror for browser downloads (China-friendly)
  PLAYWRIGHT_DOWNLOAD_HOST         optional explicit Playwright download host URL (overrides mirror flag)
  UV_PROJECT_ENVIRONMENT  Python virtualenv dir (default: backend/.venv)
EOF
}

# ── Lock file (prevents concurrent starts) ──────────────────────
LOCK_FILE="$SCRIPT_DIR/.leagent.lock"

acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local lock_pid
        lock_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
        if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
            fail "Another LeAgent instance is running (PID $lock_pid). Use './start.sh stop' first, or remove $LOCK_FILE."
        fi
        warn "Stale lock file found (PID $lock_pid no longer running) — removing"
        rm -f "$LOCK_FILE"
    fi
    echo $$ > "$LOCK_FILE"
}

release_lock() {
    local lock_pid
    lock_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
    if [ "$lock_pid" = "$$" ]; then
        rm -f "$LOCK_FILE"
    fi
}

stop_leagent() {
    _kill_stray_log_tails
    _kill_port "$BACKEND_PORT"
    _kill_port "$FRONTEND_PORT"
    if [ -f "$LOCK_FILE" ]; then
        local lock_pid
        lock_pid="$(tr -d '\n\r ' < "$LOCK_FILE" 2>/dev/null || true)"
        if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
            info "Stopping start.sh supervisor (PID ${lock_pid})"
            kill -TERM "$lock_pid" 2>/dev/null || true
            local waited=0
            while [ "$waited" -lt "$SHUTDOWN_GRACE_SEC" ]; do
                kill -0 "$lock_pid" 2>/dev/null || break
                sleep 1
                waited=$((waited + 1))
            done
            if kill -0 "$lock_pid" 2>/dev/null; then
                kill -9 "$lock_pid" 2>/dev/null || true
            fi
        fi
        rm -f "$LOCK_FILE"
    fi
    success "Stopped LeAgent processes on ports ${BACKEND_PORT}, ${FRONTEND_PORT}"
}

# ── Platform-safe port killing ──────────────────────────────────
_pids_on_port() {
    local port="$1"
    if command -v lsof >/dev/null 2>&1; then
        lsof -ti:"$port" 2>/dev/null || true
    elif command -v fuser >/dev/null 2>&1; then
        fuser "$port/tcp" 2>/dev/null | tr -s ' ' '\n' || true
    elif command -v ss >/dev/null 2>&1; then
        ss -tlnp "sport = :$port" 2>/dev/null \
            | grep -o 'pid=[0-9]*' | grep -o '[0-9]*' || true
    fi
}

_kill_port() {
    local port="$1" pids=""
    pids="$(_pids_on_port "$port")"
    [ -z "$pids" ] && return 0

    echo "$pids" | xargs kill -TERM 2>/dev/null || true
    local waited=0
    while [ "$waited" -lt "$SHUTDOWN_GRACE_SEC" ]; do
        sleep 1
        waited=$((waited + 1))
        local remaining=""
        remaining="$(_pids_on_port "$port")"
        [ -z "$remaining" ] && return 0
    done
    pids="$(_pids_on_port "$port")"
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
}

_ensure_log_dir() { mkdir -p "$LOG_DIR"; }

# Reap orphaned `tail -F` processes left following our logs by a previous run.
# These cause duplicated output and "file inaccessible/appeared" noise when the
# next run rotates the log files.
_kill_stray_log_tails() {
    command -v pgrep >/dev/null 2>&1 || return 0
    local pids
    pids="$(pgrep -f "tail .*${LOG_DIR}/" 2>/dev/null || true)"
    # Never kill the tail belonging to this process.
    [ -n "${TAIL_PID:-}" ] && pids="$(echo "$pids" | grep -v "^${TAIL_PID}\$" || true)"
    [ -n "$pids" ] && echo "$pids" | xargs kill 2>/dev/null || true
    return 0
}

# ── Log rotation ────────────────────────────────────────────────
_rotate_log() {
    local logfile="$1"
    [ -f "$logfile" ] || return 0
    [ -s "$logfile" ] || return 0
    local i="$LOG_RETENTION"
    while [ "$i" -gt 0 ]; do
        local prev=$((i - 1))
        if [ "$prev" -eq 0 ]; then
            [ -f "$logfile" ] && mv -f "$logfile" "${logfile}.1"
        else
            [ -f "${logfile}.${prev}" ] && mv -f "${logfile}.${prev}" "${logfile}.${i}"
        fi
        i=$((i - 1))
    done
}

node_supports_vite() {
    local node_bin="${1:-}"
    [ -n "$node_bin" ] || node_bin="$(command -v node || true)"
    [ -n "$node_bin" ] || return 1
    [ "$("$node_bin" -p "const [M,m]=process.versions.node.split('.').map(Number); Number((M === 20 && m >= 19) || (M === 22 && m >= 12) || M > 22)" 2>/dev/null || echo 0)" = "1" ]
}

node_version() {
    local node_bin="${1:-}"
    [ -n "$node_bin" ] || node_bin="$(command -v node || true)"
    if [ -n "$node_bin" ]; then
        "$node_bin" -p "process.versions.node" 2>/dev/null || echo "unknown"
    else
        echo "missing"
    fi
}

load_nvm() {
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [ -s "$NVM_DIR/nvm.sh" ]; then
        # shellcheck disable=SC1091
        . "$NVM_DIR/nvm.sh"
        return 0
    fi
    if command -v brew >/dev/null 2>&1 && [ -s "$(brew --prefix nvm 2>/dev/null)/nvm.sh" ]; then
        # shellcheck disable=SC1091
        . "$(brew --prefix nvm)/nvm.sh"
        return 0
    fi
    return 1
}

activate_compatible_node() {
    NODE_BIN="$(command -v node || true)"
    NPM_BIN="$(command -v npm || true)"
    if node_supports_vite "$NODE_BIN" && [ -n "$NPM_BIN" ]; then
        export NODE_BIN NPM_BIN
        return 0
    fi

    if load_nvm; then
        if nvm use 22 >/dev/null 2>&1 || nvm use default >/dev/null 2>&1; then
            hash -r
            NODE_BIN="$(command -v node || true)"
            NPM_BIN="$(command -v npm || true)"
            if node_supports_vite "$NODE_BIN" && [ -n "$NPM_BIN" ]; then
                export NODE_BIN NPM_BIN
                return 0
            fi
        fi
    fi

    return 1
}

install_or_update_git() {
    if command -v git >/dev/null 2>&1; then
        success "git $(git --version | head -1 | sed 's/git version //')"
        return
    fi

    step "Installing git"
    case "$PLATFORM" in
        linux)
            command -v sudo >/dev/null 2>&1 || fail "sudo is required to install git on Linux"
            sudo apt-get update
            sudo apt-get install -y git curl ca-certificates
            ;;
        macos)
            if command -v brew >/dev/null 2>&1; then
                brew install git
            else
                xcode-select --install 2>/dev/null || true
                fail "Install Xcode Command Line Tools, then rerun ./start.sh fix-deps"
            fi
            ;;
        *)
            fail "Unsupported platform for automatic git installation: $PLATFORM"
            ;;
    esac
    command -v git >/dev/null 2>&1 || fail "git installation did not complete"
    success "git $(git --version | head -1 | sed 's/git version //')"
}

install_or_update_uv() {
    if command -v uv >/dev/null 2>&1; then
        success "uv $(uv --version | awk '{print $2}')"
        return
    fi

    step "Installing uv"
    command -v curl >/dev/null 2>&1 || fail "curl is required to install uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    command -v uv >/dev/null 2>&1 || fail "uv installed but is not on PATH; restart your shell and rerun ./start.sh"
    success "uv $(uv --version | awk '{print $2}')"
}

install_or_update_node() {
    NODE_BIN="$(command -v node || true)"
    NPM_BIN="$(command -v npm || true)"
    if node_supports_vite "$NODE_BIN" && [ -n "$NPM_BIN" ]; then
        export NODE_BIN NPM_BIN
        success "node $("$NODE_BIN" -v)  npm $("$NPM_BIN" -v 2>/dev/null || echo '?')"
        return
    fi

    step "Installing Node.js 22 with nvm"
    if [ -n "$NODE_BIN" ]; then
        warn "current node v$(node_version "$NODE_BIN") is not compatible with Vite 7"
    fi
    command -v curl >/dev/null 2>&1 || fail "curl is required to install nvm/Node.js"

    if ! load_nvm; then
        curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash
        load_nvm || fail "nvm installed but could not be loaded; restart your shell and rerun ./start.sh fix-deps"
    fi

    nvm install 22
    nvm alias default 22 >/dev/null
    nvm use 22 >/dev/null
    hash -r

    NODE_BIN="$(command -v node || true)"
    NPM_BIN="$(command -v npm || true)"
    node_supports_vite "$NODE_BIN" || fail "Node.js upgrade did not provide a Vite-compatible version (found v$(node_version "$NODE_BIN"))"
    [ -n "$NPM_BIN" ] || fail "npm was not found after installing Node.js"
    export NODE_BIN NPM_BIN
    success "node $("$NODE_BIN" -v)  npm $("$NPM_BIN" -v 2>/dev/null || echo '?')"
}

fix_dependencies() {
    print_banner
    step "Fixing local dependencies"
    install_or_update_git
    install_or_update_uv
    install_or_update_node
    echo ""
    success "Dependencies are ready"
    info "Run ${BOLD}./start.sh${NC} to start LeAgent"
}

# ── Prerequisite checks ────────────────────────────────────────
check_prerequisites() {
    local want_frontend="${1:-1}"
    step "Checking prerequisites"

    command -v git >/dev/null 2>&1 \
        || fail "git is not installed  ──  https://git-scm.com"
    success "git $(git --version | head -1 | sed 's/git version //')"

    command -v uv >/dev/null 2>&1 \
        || fail "uv is not installed   ──  https://docs.astral.sh/uv/"
    success "uv $(uv --version | awk '{print $2}')"

    if [ "$want_frontend" = "1" ]; then
        activate_compatible_node || true
        NODE_BIN="$(command -v node || true)"
        NPM_BIN="$(command -v npm || true)"
        [ -n "$NODE_BIN" ] \
            || fail "node is not installed  ──  https://nodejs.org"
        [ -n "$NPM_BIN" ] \
            || fail "npm is not installed   ──  https://nodejs.org"
        node_supports_vite "$NODE_BIN" || fail "Node.js 20.19+ or 22.12+ required for Vite 7 (found v$(node_version "$NODE_BIN")). Run ./start.sh fix-deps, then rerun ./start.sh"
        export NODE_BIN NPM_BIN
        success "node $("$NODE_BIN" -v)  npm $("$NPM_BIN" -v 2>/dev/null || echo '?')"
    fi
}

# ── Dependency fingerprint helpers (avoid mtime false positives) ─
_file_sha256() {
    local f="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$f" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$f" | awk '{print $1}'
    else
        fail "sha256sum or shasum required for dependency fingerprinting"
    fi
}

_read_marker() {
    local marker="$1"
    [ -f "$marker" ] && tr -d '\n\r' < "$marker" || true
}

_write_marker() {
    printf '%s' "$2" > "$1"
}

# ── Python environment ──────────────────────────────────────────
run_backend_uv_sync() {
    local args=() e
    for e in $UV_SYNC_EXTRAS; do
        args+=(--extra "$e")
    done
    uv sync "${args[@]}" --directory "$BACKEND_DIR"
}

ensure_backend_sync() {
    [ -f "$BACKEND_DIR/uv.lock" ] \
        || fail "backend/uv.lock is missing ── run 'uv lock' in backend/"

    local marker="$BACKEND_DIR/.uv_sync_marker"
    local lockfile="$BACKEND_DIR/uv.lock"
    local lock_hash venv_python
    lock_hash="$(_file_sha256 "$lockfile")"
    venv_python="$UV_PROJECT_ENVIRONMENT/bin/python"

    if [ "${FORCE_UV_SYNC:-0}" = "1" ] \
        || [ ! -x "$venv_python" ] \
        || [ "$(_read_marker "$marker")" != "$lock_hash" ]; then
        step "Syncing Python environment"
        info "extras: ${UV_SYNC_EXTRAS}"
        local t; t="$(date +%s)"
        run_backend_uv_sync
        _write_marker "$marker" "$lock_hash"
        success "Python environment ready ($(_elapsed "$t"))"
    fi
}

# ── Playwright browser binaries (Chromium) ─────────────────────
ensure_playwright_browsers() {
    [ "${LEAGENT_SKIP_PLAYWRIGHT_INSTALL:-0}" = "1" ] && return 0
    echo " $UV_SYNC_EXTRAS " | grep -q ' browser ' || return 0
    if [ -z "${PLAYWRIGHT_DOWNLOAD_HOST:-}" ] && [ "${LEAGENT_PLAYWRIGHT_MIRROR:-0}" = "1" ]; then
        export PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright/"
    fi
    local pw_marker="$BACKEND_DIR/.playwright_chromium_marker"
    local deps_marker="$BACKEND_DIR/.playwright_system_deps_marker"
    local lockfile="$BACKEND_DIR/uv.lock"
    local lock_hash
    lock_hash="$(_file_sha256 "$lockfile")"
    # Fingerprint uv.lock (same idea as .uv_sync_marker), not file mtimes — uv sync
    # updates uv.lock and used to invalidate an empty touch marker every start.
    if [ "$(_read_marker "$pw_marker")" = "$lock_hash" ]; then
        return 0
    fi
    if ! uv run --directory "$BACKEND_DIR" python -c "import playwright" 2>/dev/null; then
        warn "Playwright Python package missing — run uv sync with 'browser' extra or ./start.sh --sync-python"
        return 0
    fi
    step "Ensuring Playwright Chromium is installed"
    local t; t="$(date +%s)"
    if uv run --directory "$BACKEND_DIR" playwright install chromium; then
        _write_marker "$pw_marker" "$lock_hash"
        success "Playwright Chromium ready ($(_elapsed "$t"))"
    else
        warn "playwright install chromium failed — set PLAYWRIGHT_DOWNLOAD_HOST or LEAGENT_PLAYWRIGHT_MIRROR=1 and retry"
        return 0
    fi
    # System libraries (apt) — one-time; do not re-run on every marker miss.
    if [ "$PLATFORM" = "linux" ] && [ "$(_read_marker "$deps_marker")" != "installed" ]; then
        step "Installing Playwright system dependencies (one-time; may ask for sudo)"
        if uv run --directory "$BACKEND_DIR" playwright install-deps chromium; then
            _write_marker "$deps_marker" "installed"
            success "Playwright system dependencies ready"
        else
            warn "playwright install-deps failed — rerun manually: cd backend && uv run playwright install-deps chromium"
        fi
    fi
}

# ── Database migrations ─────────────────────────────────────────
run_database_migrations() {
    ensure_backend_sync
    step "Applying database migrations"
    local t; t="$(date +%s)"
    uv run --directory "$BACKEND_DIR" alembic upgrade head
    success "Migrations complete ($(_elapsed "$t"))"
}

# ── Frontend dependencies + build ──────────────────────────────
install_frontend_deps() {
    local frontend_dir="$SCRIPT_DIR/frontend"
    local lockfile="$frontend_dir/package-lock.json"
    local marker="$frontend_dir/.npm_install_marker"
    [ -f "$lockfile" ] \
        || fail "frontend/package-lock.json is missing ── run 'npm install' in frontend/"

    local lock_hash need_install=0
    lock_hash="$(_file_sha256 "$lockfile")"
    if [ ! -d "$frontend_dir/node_modules" ]; then
        need_install=1
    elif [ "$(_read_marker "$marker")" != "$lock_hash" ]; then
        need_install=1
    fi

    if [ "$need_install" = "1" ]; then
        step "Installing frontend dependencies"
        local t; t="$(date +%s)"
        if ! (cd "$frontend_dir" && PATH="$(dirname "$NODE_BIN"):$PATH" "$NPM_BIN" ci --silent 2>/dev/null); then
            (cd "$frontend_dir" && PATH="$(dirname "$NODE_BIN"):$PATH" "$NPM_BIN" install --silent)
        fi
        _write_marker "$marker" "$lock_hash"
        success "Frontend dependencies ready ($(_elapsed "$t"))"
    fi
}

build_frontend() {
    local frontend_dir="$SCRIPT_DIR/frontend"
    install_frontend_deps
    step "Building frontend for production"
    local t; t="$(date +%s)"
    (cd "$frontend_dir" && PATH="$(dirname "$NODE_BIN"):$PATH" "$NPM_BIN" run build)
    success "Frontend build complete ($(_elapsed "$t"))"
}

# ── Process spawning ────────────────────────────────────────────
_spawn() {
    local name="$1" logbase="$2"
    shift 2
    _ensure_log_dir
    local logfile="$LOG_DIR/${logbase}.log"
    _rotate_log "$logfile"
    : > "$logfile"
    info "Starting ${name}  ${DIM}-> ${logfile}${NC}"
    if command -v setsid >/dev/null 2>&1; then
        setsid bash -c 'exec "$@" >>"$0" 2>&1' "$logfile" "$@" &
    else
        bash -c 'exec "$@" >>"$0" 2>&1' "$logfile" "$@" &
    fi
    CHILD_PIDS+=("$!")
    SPAWNED_LOG_FILES+=("$logfile")
}

_stream_logs() {
    if [ "${#SPAWNED_LOG_FILES[@]}" -eq 0 ]; then
        wait
        return
    fi
    local backlog="${LEAGENT_LOG_BACKLOG:-200}"
    tail -n "$backlog" -F "${SPAWNED_LOG_FILES[@]}" &
    TAIL_PID=$!
    wait "$TAIL_PID"
}

_wait_or_stream() {
    if [ "$STREAM_LOGS" = "1" ]; then
        _stream_logs
    else
        echo ""
        success "Services started in background"
        info "Logs:  ${DIM}${LOG_DIR}${NC}"
        info "Tail:  ${BOLD}./start.sh log${NC}"
        info "Stop:  ${BOLD}./start.sh stop${NC}  or  Ctrl-C"
        wait
    fi
}

# ── Service start ───────────────────────────────────────────────
start_backend() {
    _kill_stray_log_tails
    ensure_backend_sync
    ensure_playwright_browsers
    run_database_migrations
    _kill_port "$BACKEND_PORT"
    step "Starting backend"
    if [ "$MODE" = "prod" ]; then
        build_frontend
        export LEAGENT_FRONTEND_DIST="$SCRIPT_DIR/frontend/dist"
        _spawn "Backend (prod)" "monolith" \
            uv run --directory "$BACKEND_DIR" leagent app start \
                --host "$HOST" --port "$BACKEND_PORT" --workers 4 --production
    else
        _spawn "Backend (dev)" "monolith" \
            uv run --directory "$BACKEND_DIR" leagent app start \
                --host "$HOST" --port "$BACKEND_PORT" --reload
    fi
}

start_frontend() {
    _kill_stray_log_tails
    if [ "$MODE" = "prod" ]; then
        info "Production UI is served by the backend (LEAGENT_FRONTEND_DIST)"
        info "Open ${BOLD}http://${HOST}:${BACKEND_PORT}${NC}  — not :${FRONTEND_PORT}"
        return 0
    fi
    _kill_port "$FRONTEND_PORT"
    install_frontend_deps
    step "Starting frontend (vite dev)"
    _spawn "Frontend (vite)" "frontend" \
        bash -c 'cd "$1" && \
            export VITE_API_PROXY_TARGET="${VITE_API_PROXY_TARGET:-http://127.0.0.1:$4}" && \
            export VITE_WS_PROXY_TARGET="${VITE_WS_PROXY_TARGET:-ws://127.0.0.1:$4}" && \
            exec "$2" ./node_modules/vite/bin/vite.js --port "$3" --host' \
            _ "$SCRIPT_DIR/frontend" "$NODE_BIN" "$FRONTEND_PORT" "$BACKEND_PORT"
}

wait_for_backend_ready() {
    local url="http://127.0.0.1:${BACKEND_PORT}/health"
    local attempt=0 max=120
    printf "  ${DIM}…${NC} Waiting for backend "
    while [ "$attempt" -lt "$max" ]; do
        if curl -sf --connect-timeout 1 --max-time 3 "$url" >/dev/null 2>&1; then
            printf "\r  ${GREEN}✔${NC} Backend is ready                    \n"
            return 0
        fi
        attempt=$((attempt + 1))
        printf "."
        sleep 0.5
    done
    printf "\n"
    if [ "$MODE" = "prod" ]; then
        fail "Backend health-check timed out after 60s (production mode — aborting)"
    fi
    warn "Backend health-check timed out after 60s ── continuing anyway"
}

# ── Status ──────────────────────────────────────────────────────
show_status() {
    step "LeAgent service status"
    local backend_pids frontend_pids
    backend_pids="$(_pids_on_port "$BACKEND_PORT")"
    frontend_pids="$(_pids_on_port "$FRONTEND_PORT")"

    if [ -n "$backend_pids" ]; then
        success "Backend  listening on :${BACKEND_PORT}  (PIDs: $(echo "$backend_pids" | tr '\n' ' '))"
    else
        info "Backend  ${DIM}not running${NC} on :${BACKEND_PORT}"
    fi

    if [ -n "$frontend_pids" ]; then
        success "Frontend listening on :${FRONTEND_PORT}  (PIDs: $(echo "$frontend_pids" | tr '\n' ' '))"
    else
        info "Frontend ${DIM}not running${NC} on :${FRONTEND_PORT}"
    fi

    if [ -f "$LOCK_FILE" ]; then
        local lock_pid
        lock_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
        if [ -n "$lock_pid" ] && kill -0 "$lock_pid" 2>/dev/null; then
            info "Lock     ${DIM}held by PID ${lock_pid}${NC}"
        else
            info "Lock     ${DIM}stale (PID ${lock_pid} not running)${NC}"
        fi
    else
        info "Lock     ${DIM}no lock file${NC}"
    fi
}

# ── System check ────────────────────────────────────────────────
check_system() {
    print_banner
    check_prerequisites 1
    [ -f "$BACKEND_DIR/uv.lock" ]              || fail "backend/uv.lock missing"
    [ -f "$SCRIPT_DIR/frontend/package.json" ]  || fail "frontend/package.json missing"
    step "Verifying backend import"
    uv run --directory "$BACKEND_DIR" python -c \
        "import leagent.main; print('  ✔ leagent.main importable')"
    echo ""
    success "All checks passed"
}

# ── Cleanup / signal handling ───────────────────────────────────
cleanup() {
    printf "\n"
    info "Shutting down (grace period: ${SHUTDOWN_GRACE_SEC}s)..."
    if [ -n "${TAIL_PID:-}" ]; then
        kill "$TAIL_PID" 2>/dev/null || true
        TAIL_PID=""
    fi
    for pid in "${CHILD_PIDS[@]}"; do
        [ -z "$pid" ] && continue
        kill -TERM -- -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    done

    local waited=0
    while [ "$waited" -lt "$SHUTDOWN_GRACE_SEC" ]; do
        local all_exited=true
        for pid in "${CHILD_PIDS[@]}"; do
            [ -z "$pid" ] && continue
            if kill -0 "$pid" 2>/dev/null; then
                all_exited=false
                break
            fi
        done
        if $all_exited; then break; fi
        sleep 1
        waited=$((waited + 1))
    done

    for pid in "${CHILD_PIDS[@]}"; do
        [ -z "$pid" ] && continue
        kill -9 -- -"$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    done
    _kill_port "$BACKEND_PORT"
    _kill_port "$FRONTEND_PORT"
    release_lock
    success "Shutdown complete"
    exit 0
}
trap cleanup INT TERM HUP QUIT

# ── Argument parsing ────────────────────────────────────────────
COMMAND="all"
LOG_SERVICE=""
_prev_was_log=0

for arg in "$@"; do
    if [ "$_prev_was_log" = "1" ]; then
        case $arg in
            --*) ;;
            *)   LOG_SERVICE="$arg"; _prev_was_log=0; continue ;;
        esac
        _prev_was_log=0
    fi
    case $arg in
        --dev)         MODE="dev" ;;
        --prod)        MODE="prod" ;;
        --quiet)       STREAM_LOGS=0 ;;
        --sync-python) FORCE_UV_SYNC=1 ;;
        --help|-h)     print_help; exit 0 ;;
        log)           COMMAND="log"; _prev_was_log=1 ;;
        stop)          COMMAND="stop" ;;
        all|backend|frontend|check|fix-deps|sync-python|build-frontend|status) COMMAND="$arg" ;;
        *)             fail "Unknown argument: $arg  (try --help)" ;;
    esac
done

# ── Dispatch ────────────────────────────────────────────────────
case "$COMMAND" in
    sync-python)
        check_prerequisites 0
        step "Locking and syncing Python environment"
        uv lock --directory "$BACKEND_DIR"
        run_backend_uv_sync
        _write_marker "$BACKEND_DIR/.uv_sync_marker" "$(_file_sha256 "$BACKEND_DIR/uv.lock")"
        ensure_playwright_browsers
        success "Python environment ready"
        ;;
    check)
        check_system
        ;;
    fix-deps)
        fix_dependencies
        ;;
    build-frontend)
        check_prerequisites 1
        build_frontend
        ;;
    status)
        show_status
        ;;
    log)
        _ensure_log_dir
        if [ -n "$LOG_SERVICE" ]; then
            tail -n "${LEAGENT_LOG_BACKLOG:-200}" -F "$LOG_DIR/${LOG_SERVICE}.log"
        else
            tail -n "${LEAGENT_LOG_BACKLOG:-200}" -F "$LOG_DIR"/*.log
        fi
        ;;
    stop)
        stop_leagent
        ;;
    backend)
        acquire_lock
        print_banner
        check_prerequisites 0
        start_backend
        _wait_or_stream
        ;;
    frontend)
        print_banner
        check_prerequisites 1
        start_frontend
        _wait_or_stream
        ;;
    all|*)
        acquire_lock
        print_banner
        check_prerequisites 1
        start_backend
        wait_for_backend_ready
        start_frontend
        _wait_or_stream
        ;;
esac
