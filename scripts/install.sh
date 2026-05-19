#!/usr/bin/env bash
# LeAgent installer (Unix / Git Bash)
# Usage:
#   curl -fsSL https://example.com/install.sh | bash
#   bash scripts/install.sh --help
#
# Environment (flags override when passed):
#   LEAGENT_GIT_URL       Clone URL (default: https://github.com/vixues/LeAgent.git)
#   LEAGENT_CLONE_DIR     Install directory (default: $HOME/leagent-desktop)
#   LEAGENT_REF           Branch or tag (default: main)
#   LEAGENT_SKIP_START    1 = clone + sync only, do not run start.sh
#   LEAGENT_DRY_RUN       1 = print actions only
#   LEAGENT_RUN_CHECK     1 = run ./start.sh check before start (default: 1)
#   LEAGENT_SKIP_INIT     1 = skip ./start.sh sync-python + leagent init --defaults
#   UV_SYNC_EXTRAS        uv extras for backend (default: dev browser); see also --extras
#   UV_PROJECT_ENVIRONMENT  Passed through to start.sh (default backend/.venv)

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
if [ -t 1 ] && [ "${TERM:-dumb}" != "dumb" ]; then
    BOLD="\033[1m"
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    RED="\033[0;31m"
    CYAN="\033[0;36m"
    RESET="\033[0m"
else
    BOLD="" GREEN="" YELLOW="" RED="" CYAN="" RESET=""
fi

info()  { printf "${GREEN}[leagent]${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[leagent]${RESET} %s\n" "$*"; }
error() { printf "${RED}[leagent]${RESET} %s\n" "$*" >&2; }
die()   { error "$@"; exit 1; }

# ── Defaults ─────────────────────────────────────────────────────────────────
LEAGENT_GIT_URL="${LEAGENT_GIT_URL:-https://github.com/vixues/LeAgent.git}"
LEAGENT_CLONE_DIR="${LEAGENT_CLONE_DIR:-$HOME/leagent-desktop}"
LEAGENT_REF="${LEAGENT_REF:-main}"
LEAGENT_SKIP_START="${LEAGENT_SKIP_START:-0}"
LEAGENT_DRY_RUN="${LEAGENT_DRY_RUN:-0}"
LEAGENT_RUN_CHECK="${LEAGENT_RUN_CHECK:-1}"
LEAGENT_SKIP_INIT="${LEAGENT_SKIP_INIT:-0}"
MAX_RETRIES="${LEAGENT_INSTALL_RETRIES:-3}"

FROM_SOURCE=false
SOURCE_DIR=""

export UV_VENV_CLEAR="${UV_VENV_CLEAR:-1}"

# Only probe network when UV_INDEX_URL is not already set.
choose_pypi_mirror() {
    if curl -fsS --connect-timeout 3 "https://pypi.org/pypi/pip/json" -o /dev/null 2>/dev/null; then
        echo "https://pypi.org/simple/"
        info "Using official PyPI index (connectivity OK)" >&2
    else
        echo "https://mirrors.aliyun.com/pypi/simple/"
        info "Using Aliyun PyPI mirror (official index unreachable)" >&2
    fi
}

if [ -z "${UV_INDEX_URL:-}" ]; then
    PYPI_MIRROR="$(choose_pypi_mirror)"
    export UV_INDEX_URL="$PYPI_MIRROR"
else
    info "UV_INDEX_URL already set: $UV_INDEX_URL"
fi

# ── Parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --git-url)
            LEAGENT_GIT_URL="$2"
            shift 2 ;;
        --dir)
            LEAGENT_CLONE_DIR="$2"
            shift 2 ;;
        --ref|--version)
            LEAGENT_REF="$2"
            shift 2 ;;
        --extras)
            export UV_SYNC_EXTRAS="$2"
            shift 2 ;;
        --skip-start)
            LEAGENT_SKIP_START=1
            shift ;;
        --skip-init)
            LEAGENT_SKIP_INIT=1
            shift ;;
        --dry-run)
            LEAGENT_DRY_RUN=1
            shift ;;
        --no-check)
            LEAGENT_RUN_CHECK=0
            shift ;;
        --from-source)
            FROM_SOURCE=true
            if [[ $# -ge 2 && "$2" != --* ]]; then
                SOURCE_DIR="$(cd "$2" && pwd)" || die "Directory not found: $2"
                shift
            fi
            shift ;;
        -h|--help)
            cat <<EOF
LeAgent installer — clones the repo (or uses a local tree), ensures uv + Node.js,
then runs ./start.sh (local dev stack).

Usage: bash install.sh [OPTIONS]

Options:
  --git-url <URL>     Git clone URL
  --dir <PATH>        Clone / install directory (default: \$HOME/leagent-desktop)
  --ref <REF>         Branch or tag (default: main)
  --version <REF>     Same as --ref
  --from-source <DIR> Use an existing checkout at DIR (skips git clone/update)
  --extras <NAMES>    uv sync extras, e.g. "dev browser" (default: dev browser)
  --skip-start        Clone/deps only; do not run ./start.sh
  --skip-init         Skip ./start.sh sync-python + leagent init --defaults
  --dry-run           Print planned steps only
  --no-check          Skip ./start.sh check before start

Environment:
  LEAGENT_GIT_URL  LEAGENT_CLONE_DIR  LEAGENT_REF  LEAGENT_SKIP_START
  LEAGENT_DRY_RUN  LEAGENT_RUN_CHECK  LEAGENT_SKIP_INIT
  LEAGENT_INSTALL_RETRIES  UV_SYNC_EXTRAS  UV_INDEX_URL  UV_VENV_CLEAR

Examples:
  curl -fsSL https://example.com/install.sh | bash
  curl -fsSL https://example.com/install.sh | bash -s -- --skip-start
  bash install.sh --from-source "\$HOME/src/LeAgent" --skip-start
EOF
            exit 0 ;;
        *)
            die "Unknown option: $1 (try --help)" ;;
    esac
done

if [[ "$FROM_SOURCE" == true && -z "$SOURCE_DIR" ]]; then
    die "--from-source requires a directory (see --help)"
fi

if [[ "$FROM_SOURCE" == true ]]; then
    LEAGENT_CLONE_DIR="$SOURCE_DIR"
fi

need_cmd() {
    command -v "$1" >/dev/null 2>&1
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

ensure_git() {
    need_cmd git || die "git is required — https://git-scm.com/downloads"
}

ensure_node() {
    need_cmd node || die "Node.js 20.19+ or 22.12+ is required — https://nodejs.org/"
    need_cmd npm || die "npm is required (install current Node.js LTS)"
    local nb
    nb="$(command -v node)"
    node_supports_vite "$nb" || die "Node.js 20.19+ or 22.12+ required for Vite 7 (found v$(node_version "$nb"))"
    info "Node $(node_version "$nb") OK"
}

ensure_uv() {
    if need_cmd uv; then
        info "uv found: $(command -v uv)"
        return 0
    fi

    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [ -x "$candidate" ]; then
            export PATH="$(dirname "$candidate"):$PATH"
            info "uv found: $candidate"
            return 0
        fi
    done

    if [ "$LEAGENT_DRY_RUN" = "1" ]; then
        info "[dry-run] would install uv via https://astral.sh/uv/install.sh"
        return 0
    fi

    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    if [ -f "$HOME/.local/bin/env" ]; then
        # shellcheck disable=SC1091
        . "$HOME/.local/bin/env"
    fi
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    need_cmd uv || die "Failed to install uv — https://docs.astral.sh/uv/"
    info "uv installed successfully"
}

# Retry wrapper for flaky network operations.
retry() {
    local max_attempts="$MAX_RETRIES" attempt=1
    local delay=2
    while [ "$attempt" -le "$max_attempts" ]; do
        if "$@"; then
            return 0
        fi
        if [ "$attempt" -eq "$max_attempts" ]; then
            error "Command failed after $max_attempts attempts: $*"
            return 1
        fi
        warn "Attempt $attempt/$max_attempts failed, retrying in ${delay}s..."
        sleep "$delay"
        delay=$((delay * 2))
        attempt=$((attempt + 1))
    done
}

clone_or_update() {
    local url="$1" dir="$2" ref="$3"
    if [ "$LEAGENT_DRY_RUN" = "1" ]; then
        info "[dry-run] clone/update $url -> $dir @ $ref"
        return 0
    fi
    if [ -d "$dir/.git" ]; then
        info "Updating existing repo at $dir ..."
        retry git -C "$dir" fetch --depth 1 origin "$ref" || retry git -C "$dir" fetch origin || die "git fetch failed"
        git -C "$dir" checkout "$ref" || die "could not checkout $ref"
        git -C "$dir" pull --ff-only 2>/dev/null || true
    elif [ -e "$dir" ]; then
        die "path exists and is not a git repository: $dir"
    else
        info "Cloning $url -> $dir (ref: $ref) ..."
        if ! retry git clone --depth 1 --branch "$ref" "$url" "$dir" 2>/dev/null; then
            warn "Shallow clone with branch failed; cloning full repo ..."
            retry git clone "$url" "$dir" || die "git clone failed after $MAX_RETRIES attempts"
            git -C "$dir" checkout "$ref" || die "could not checkout $ref"
        fi
    fi
}

main() {
    ensure_git
    ensure_node
    ensure_uv

    printf "\n${GREEN}[leagent]${RESET} Installing into ${BOLD}%s${RESET}\n" "$LEAGENT_CLONE_DIR"
    info "repository: $LEAGENT_GIT_URL"
    info "ref:        $LEAGENT_REF"
    info "PyPI index: $UV_INDEX_URL"
    echo ""

    if [ "$FROM_SOURCE" = true ]; then
        info "Using local source tree (--from-source)"
        [ -f "$LEAGENT_CLONE_DIR/start.sh" ] || die "start.sh not found in $LEAGENT_CLONE_DIR"
    else
        clone_or_update "$LEAGENT_GIT_URL" "$LEAGENT_CLONE_DIR" "$LEAGENT_REF"
    fi

    if [ "$LEAGENT_DRY_RUN" = "1" ]; then
        info "[dry-run] done."
        exit 0
    fi

    cd "$LEAGENT_CLONE_DIR"
    [ -f ./start.sh ] || die "start.sh not found in $LEAGENT_CLONE_DIR"
    chmod +x start.sh

    if [ "$LEAGENT_SKIP_INIT" != "1" ]; then
        info "Running ./start.sh sync-python and leagent init --defaults ..."
        ./start.sh sync-python
        uv run --directory backend leagent init --defaults
    fi

    if [ "$LEAGENT_RUN_CHECK" = "1" ]; then
        info "Running ./start.sh check ..."
        ./start.sh check
    fi

    if [ "$LEAGENT_SKIP_START" = "1" ]; then
        info "Skip start requested — not launching services."
        echo ""
        printf "${GREEN}${BOLD}LeAgent install finished.${RESET}\n"
        printf "  Directory: ${BOLD}%s${RESET}\n" "$LEAGENT_CLONE_DIR"
        echo ""
        echo "Next: cd \"$LEAGENT_CLONE_DIR\" && ./start.sh"
        exit 0
    fi

    info "Starting LeAgent (./start.sh all) ..."
    exec ./start.sh all
}

main "$@"
