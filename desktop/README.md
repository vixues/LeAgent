# LeAgent Desktop

Cross-platform Electron shell that bundles the LeAgent FastAPI backend and React frontend into a standalone desktop application for **macOS**, **Windows**, and **Linux**.

## Architecture

```
desktop/
├── electron/                    Electron app source
│   ├── src/
│   │   ├── main.ts              Thin entry — single-instance lock
│   │   ├── app/                 LeAgentDesktopApp orchestrator
│   │   ├── config/              electron-store desktop settings
│   │   ├── install/             InstallationManager + validator
│   │   ├── server/              BackendServer (Python subprocess)
│   │   ├── window/              AppWindow + splash + window state
│   │   ├── ipc/                 IPC registration modules
│   │   └── preload.ts           contextBridge → window.leagent
│   ├── splash/                  Boot progress UI
│   ├── maintenance/             Validation / repair UI
│   └── build/                   NSIS hooks, entitlements, notarize
└── scripts/                     Runtime staging + platform builds
```

### Boot flow

1. Splash appears immediately.
2. `InstallationManager.ensureInstalled()` — first launch runs `uv venv` + `uv sync --frozen` + `alembic upgrade head`.
3. `InstallValidator` — blocks startup on critical errors; opens **maintenance** page when validation fails.
4. `BackendServer` starts `python -m leagent.server` on `127.0.0.1:7860`, polls `/health`, then loads the SPA.
5. Backend crash auto-restart is limited to **3 attempts** before maintenance mode.

### Desktop bridge (`window.leagent`)

| Namespace | Methods |
|-----------|---------|
| `app` | `getVersion`, `getPaths`, `getMachineFingerprint`, `getDiagnostics`, `copyDiagnostics`, `openLogsDir`, `openApp` |
| `runtime` | `onProgress`, `onStatus` |
| `install` | `validate`, `repair`, `reinstall`, `retryBoot` |
| `server` | `restart`, `getStatus`, `onLog`, `onStatus` |
| `updater` | `check`, `download`, `install` + event listeners |

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | >= 20 |
| npm | >= 10 |
| Python + uv | For dev backend (`cd backend && uv sync`) |

### Main-process module system (ESM)

The Electron **main process** is native ESM (`package.json` → `"type": "module"`, TypeScript `module: NodeNext`). Relative imports in `src/` use explicit `.js` extensions (compiled output). This is required for `electron-store` v11 (ESM-only) and aligns with current Electron guidance.

| Dependency | Version | Notes |
|------------|---------|-------|
| `electron` | ^42.4.1 | Desktop shell runtime |
| `electron-builder` | ^26.15.3 | Cross-platform packaging |
| `electron-log` | ^5.4.4 | Import `electron-log/main.js` in main process |
| `electron-updater` | ^6.8.9 | Latest stable v6 (v7 is alpha — not used) |
| `electron-store` | ^11.0.2 | ESM-only persistence |

## Quick start (development)

```bash
cd desktop/electron && npm install && npm run build
cd ../../frontend && npm run dev &
cd ../desktop/electron && npm start
```

Electron loads `http://127.0.0.1:5173` (Vite); API calls proxy to `:7860`.

## Building for distribution

Version defaults to `desktop/electron/package.json`.

```bash
# macOS
cd desktop/scripts && ./build-mac.sh

# Linux
cd desktop/scripts && ./build-linux.sh

# Windows
cd desktop/scripts && .\build-win.ps1
```

Outputs land in `desktop/electron/dist-pack/`.

## Releases (CI)

Push a tag `desktop-v*` (e.g. `desktop-v1.1.4`) to trigger [`.github/workflows/desktop-release.yml`](../.github/workflows/desktop-release.yml). Builds macOS (arm64+x64), Windows (NSIS), and Linux (AppImage + deb), uploading artifacts to GitHub Releases via `electron-updater`.

Set `GH_TOKEN` in CI; optional macOS notarization via `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`.

## User data

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/LeAgent/` |
| Windows | `%APPDATA%/LeAgent/` |
| Linux | `~/.config/LeAgent/` |

Subdirs: `leagent/` (LEAGENT_HOME), `runtime/venv/`, `logs/main.log` + `logs/backend.log`, `desktop-config.json`.

## Environment variables (set by Electron)

| Variable | Purpose |
|----------|---------|
| `LEAGENT_DESKTOP` | `1` — skip heavyweight warmup |
| `LEAGENT_DESKTOP_MODE` | `1` — desktop tool discovery mode |
| `LEAGENT_HOME` | User data directory |
| `LEAGENT_FRONTEND_DIST` | Bundled SPA path (packaged only) |

## Testing

```bash
cd desktop/electron && npm test
```
