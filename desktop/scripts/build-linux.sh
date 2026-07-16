#!/usr/bin/env bash
set -euo pipefail

#──────────────────────────────────────────────────────────────────────
# LeAgent Desktop — Linux build (x64, AppImage + deb)
#
# Usage:
#   ./build-linux.sh                        # version from electron/package.json
#   ./build-linux.sh --version 1.2.0        # custom version
#   ./build-linux.sh --skip-runtime         # skip python/uv download
#   ./build-linux.sh --target appimage      # AppImage only (default: both)
#   ./build-linux.sh --target deb           # .deb only
#
# Prerequisites (Ubuntu/Debian):
#   sudo apt-get install -y dpkg fakeroot rpm libarchive-tools
#──────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_VERSION="$(node -p "require('$SCRIPT_DIR/../electron/package.json').version")"
VERSION="$DEFAULT_VERSION"
ARCH="x64"
SKIP_RUNTIME=false
SKIP_BACKEND=false
SKIP_FRONTEND=false
SKIP_COMPILEALL=false
CHANNEL="stable"
TARGET=""  # empty = all configured targets

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)        VERSION="$2"; shift 2 ;;
    --arch)           ARCH="$2"; shift 2 ;;
    --channel)        CHANNEL="$2"; shift 2 ;;
    --target)         TARGET="$2"; shift 2 ;;
    --skip-runtime)   SKIP_RUNTIME=true; shift ;;
    --skip-backend)   SKIP_BACKEND=true; shift ;;
    --skip-frontend)  SKIP_FRONTEND=true; shift ;;
    --skip-compileall) SKIP_COMPILEALL=true; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
DESKTOP_ELECTRON="$REPO/desktop/electron"
IFS=',' read -ra ARCHES <<< "$ARCH"

echo "============================================"
echo "  LeAgent Desktop — Linux Build"
echo "  Version : $VERSION"
echo "  Arch    : $ARCH"
echo "  Channel : $CHANNEL"
echo "  Target  : ${TARGET:-all}"
echo "============================================"

# ── 0. Check system deps ──
echo ""
echo "==> Checking build prerequisites"
MISSING=""
for cmd in node npm; do
  if ! command -v "$cmd" &>/dev/null; then
    MISSING="$MISSING $cmd"
  fi
done
if [ -n "$MISSING" ]; then
  echo "ERROR: Missing required commands:$MISSING"
  exit 1
fi

if ! command -v dpkg &>/dev/null; then
  echo "  ⚠ dpkg not found — .deb target may fail. Install: sudo apt-get install dpkg fakeroot"
fi

# ── 1. Icons ──
echo ""
echo "==> make-icons.mjs"
node "$SCRIPT_DIR/make-icons.mjs" || echo "  ⚠ Icon generation failed (non-fatal)"

# ── 2. Runtime (Python + uv) ──
if [ "$SKIP_RUNTIME" = false ]; then
  PLATFORM=""
  for a in "${ARCHES[@]}"; do
    PLATFORM="${PLATFORM:+$PLATFORM,}linux-${a}"
  done
  echo ""
  echo "==> prepare-runtime.mjs --platform $PLATFORM"
  node "$SCRIPT_DIR/prepare-runtime.mjs" --platform "$PLATFORM"
else
  echo "  ⚠ SkipRuntime: python-build-standalone + uv not refreshed."
fi

# ── 3. Backend payload ──
if [ "$SKIP_BACKEND" = false ]; then
  echo ""
  echo "==> prepare-backend-payload.mjs"
  node "$SCRIPT_DIR/prepare-backend-payload.mjs"
else
  echo "  ⚠ SkipBackend: backend source tree not refreshed."
fi

# ── 4. Frontend build ──
if [ "$SKIP_FRONTEND" = false ]; then
  echo ""
  echo "==> Frontend build (Vite)"
  pushd "$REPO/frontend" > /dev/null
  # Relative /api/v1 — same-origin with backend-served SPA (any serverPort).
  export VITE_DESKTOP=true
  unset VITE_API_BASE_URL
  npm ci
  npm run build
  unset VITE_DESKTOP
  popd > /dev/null
else
  echo "  ⚠ SkipFrontend: frontend/dist not rebuilt."
fi

# ── 5. Compile bytecode ──
if [ "$SKIP_COMPILEALL" = false ]; then
  PAYLOAD_DIR="$DESKTOP_ELECTRON/resources/backend-payload"
  RUNTIME_PY=""
  for a in "${ARCHES[@]}"; do
    candidate="$DESKTOP_ELECTRON/resources/runtime/linux-${a}/python/bin/python3"
    if [ -x "$candidate" ] && "$candidate" --version > /dev/null 2>&1; then
      RUNTIME_PY="$candidate"
      break
    fi
  done
  if [ -x "$RUNTIME_PY" ] && [ -d "$PAYLOAD_DIR/leagent" ]; then
    echo ""
    echo "==> compileall backend payload"
    "$RUNTIME_PY" -m compileall -q "$PAYLOAD_DIR/leagent" || echo "  ⚠ compileall failed (non-fatal)"
  else
    echo "  ⚠ Compatible bundled Python not found or no payload — skipping compileall."
  fi
else
  echo "  ⚠ SkipCompileall: .pyc cache not refreshed."
fi

# ── 6. Electron build + pack ──
echo ""
echo "==> Electron npm ci + build + pack"
pushd "$DESKTOP_ELECTRON" > /dev/null

npm ci
npm run build

export VERSION="$VERSION"
ARCH_FLAGS=""
for a in "${ARCHES[@]}"; do
  ARCH_FLAGS="$ARCH_FLAGS --${a}"
done

EB_VERSION_FLAG="--c.extraMetadata.version=$VERSION"

if [ -n "$TARGET" ]; then
  # Build specific target only by creating a temporary override
  case "$TARGET" in
    appimage|AppImage)
      npx electron-builder --linux AppImage $ARCH_FLAGS --config electron-builder.yml $EB_VERSION_FLAG
      ;;
    deb)
      npx electron-builder --linux deb $ARCH_FLAGS --config electron-builder.yml $EB_VERSION_FLAG
      ;;
    *)
      echo "Unknown target: $TARGET (use appimage or deb)"
      exit 1
      ;;
  esac
else
  npx electron-builder --linux $ARCH_FLAGS --config electron-builder.yml $EB_VERSION_FLAG
fi

popd > /dev/null

# ── 7. Report ──
echo ""
echo "==> Build complete"
DIST_PACK="$DESKTOP_ELECTRON/dist-pack"
if [ -d "$DIST_PACK" ]; then
  echo "Artifacts:"
  find "$DIST_PACK" -maxdepth 1 -type f \( -name "*.AppImage" -o -name "*.deb" -o -name "*.rpm" -o -name "*.snap" \) | sort | while read -r f; do
    if [ -n "$TARGET" ]; then
      case "$TARGET" in
        appimage|AppImage)
          [[ "$f" == *.AppImage ]] || continue
          ;;
        deb)
          [[ "$f" == *.deb ]] || continue
          ;;
      esac
    fi
    size=$(stat --printf="%s" "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo "?")
    sha=$(sha256sum "$f" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$f" | cut -d' ' -f1)
    mb=$(echo "scale=1; $size / 1048576" | bc 2>/dev/null || echo "?")
    echo "  $(basename "$f")  ${mb} MB  SHA-256=${sha}"
  done
fi
