#!/usr/bin/env bash
set -euo pipefail

#──────────────────────────────────────────────────────────────────────
# LeAgent Desktop — macOS build (arm64 + x64)
#
# Usage:
#   ./build-mac.sh                        # default 0.1.0, both arches
#   ./build-mac.sh --version 0.2.0        # custom version
#   ./build-mac.sh --arch arm64           # single arch
#   ./build-mac.sh --skip-runtime         # skip python/uv download
#
# Code signing env vars (optional — skipped if unset):
#   APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, APPLE_TEAM_ID
#──────────────────────────────────────────────────────────────────────

VERSION="0.1.0"
ARCH="arm64,x64"
SKIP_RUNTIME=false
SKIP_BACKEND=false
SKIP_FRONTEND=false
SKIP_COMPILEALL=false
CHANNEL="stable"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)       VERSION="$2"; shift 2 ;;
    --arch)          ARCH="$2"; shift 2 ;;
    --channel)       CHANNEL="$2"; shift 2 ;;
    --skip-runtime)  SKIP_RUNTIME=true; shift ;;
    --skip-backend)  SKIP_BACKEND=true; shift ;;
    --skip-frontend) SKIP_FRONTEND=true; shift ;;
    --skip-compileall) SKIP_COMPILEALL=true; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
DESKTOP_ELECTRON="$REPO/desktop/electron"
IFS=',' read -ra ARCHES <<< "$ARCH"

echo "============================================"
echo "  LeAgent Desktop — macOS Build"
echo "  Version : $VERSION"
echo "  Arch    : $ARCH"
echo "  Channel : $CHANNEL"
echo "============================================"

# ── 1. Icons ──
echo ""
echo "==> make-icons.mjs"
node "$SCRIPT_DIR/make-icons.mjs" || echo "  ⚠ Icon generation failed (non-fatal)"

# ── 2. Runtime (Python + uv) ──
if [ "$SKIP_RUNTIME" = false ]; then
  # Build platform list from arch
  PLATFORMS=""
  for a in "${ARCHES[@]}"; do
    PLATFORMS="${PLATFORMS:+$PLATFORMS,}mac-${a}"
  done
  echo ""
  echo "==> prepare-runtime.mjs --platform $PLATFORMS"
  node "$SCRIPT_DIR/prepare-runtime.mjs" --platform "$PLATFORMS"
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
  export VITE_DESKTOP=true
  export VITE_API_BASE_URL="http://127.0.0.1:7860/api/v1"
  npm ci
  npm run build
  unset VITE_DESKTOP VITE_API_BASE_URL
  popd > /dev/null
else
  echo "  ⚠ SkipFrontend: frontend/dist not rebuilt."
fi

# ── 5. Compile bytecode ──
if [ "$SKIP_COMPILEALL" = false ]; then
  PAYLOAD_DIR="$DESKTOP_ELECTRON/resources/backend-payload"
  # Use the first bundled Python that can execute on this host.
  RUNTIME_PY=""
  for a in "${ARCHES[@]}"; do
    candidate="$DESKTOP_ELECTRON/resources/runtime/mac-${a}/python/bin/python3"
    if [ -x "$candidate" ] && "$candidate" --version > /dev/null 2>&1; then
      RUNTIME_PY="$candidate"
      break
    fi
  done
  if [ -n "$RUNTIME_PY" ] && [ -d "$PAYLOAD_DIR/leagent" ]; then
    echo ""
    echo "==> compileall backend payload"
    "$RUNTIME_PY" -m compileall -q "$PAYLOAD_DIR/leagent" || echo "  ⚠ compileall failed (non-fatal)"
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

# Build electron-builder arch flags
ARCH_FLAGS=""
for a in "${ARCHES[@]}"; do
  ARCH_FLAGS="$ARCH_FLAGS --${a}"
done

export VERSION="$VERSION"
npx electron-builder --mac $ARCH_FLAGS --config electron-builder.yml --c.extraMetadata.version="$VERSION"

popd > /dev/null

# ── 7. Notarize (if signing env is set) ──
if [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ]; then
  echo ""
  echo "==> Notarization"
  NOTARIZE_SCRIPT="$DESKTOP_ELECTRON/build/notarize.mjs"
  if [ -f "$NOTARIZE_SCRIPT" ]; then
    node "$NOTARIZE_SCRIPT"
  else
    echo "  ⚠ notarize.mjs not found — skipping notarization."
  fi
else
  echo ""
  echo "  ℹ  Skipping notarization (APPLE_ID / APPLE_APP_SPECIFIC_PASSWORD / APPLE_TEAM_ID not set)"
fi

# ── 8. Report ──
echo ""
echo "==> Build complete"
DIST_PACK="$DESKTOP_ELECTRON/dist-pack"
if [ -d "$DIST_PACK" ]; then
  echo "Artifacts:"
  find "$DIST_PACK" -maxdepth 1 -type f \( -name "*.dmg" -o -name "*.zip" \) -exec sh -c '
    for f; do
      size=$(stat -f%z "$f" 2>/dev/null || stat --printf="%s" "$f" 2>/dev/null || echo "?")
      sha=$(shasum -a 256 "$f" | cut -d" " -f1)
      echo "  $(basename "$f")  ${size} bytes  SHA-256=${sha}"
    done
  ' _ {} +
fi
