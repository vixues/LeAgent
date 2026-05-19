# LeAgent Desktop

Cross-platform Electron shell that bundles the LeAgent FastAPI backend and React frontend into a standalone desktop application for **macOS**, **Windows**, and **Linux**.

## Architecture

```
desktop/
├── electron/               Electron app source
│   ├── src/                TypeScript main-process code
│   │   ├── main.ts         App lifecycle, single-instance lock
│   │   ├── preload.ts      contextBridge → window.leagent
│   │   ├── window/         Splash + main window factories
│   │   ├── backend/        Runtime installer, backend launcher, path resolver
│   │   └── ipc/            IPC handlers (runtime, app, updater)
│   ├── splash/             Splash screen (plain HTML/CSS/JS, no bundler)
│   ├── resources/          Icons + staged runtime + backend payload (gitignored)
│   └── build/              NSIS hooks, macOS entitlements, notarize script
└── scripts/                Build & staging scripts
```

### How it works

1. User launches the app. A **splash screen** appears immediately (~50 ms).
2. On first launch, the **runtime installer** creates a Python venv from bundled `python-build-standalone` + `uv`, then runs `uv sync --frozen` against the bundled backend source.
3. The Electron main process spawns `leagent app start` on `127.0.0.1:7860` and polls `/health` with exponential backoff.
4. Once healthy, the **main window** loads the bundled frontend (or the Vite dev server in development) and the splash fades out.

### Title bar

The Electron shell uses the system-native window frame and title bar on all supported platforms.

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Node.js | >= 20 | Electron + frontend build |
| npm | >= 10 | Package management |
| Python | >= 3.11 | Backend (bundled at build time) |
| uv | >= 0.5 | Python env management (bundled at build time) |
| sharp | (dev dep) | Icon generation (`make-icons.mjs`) |

Optional (for macOS code signing):

| Env var | Purpose |
|---------|---------|
| `APPLE_ID` | Apple ID email |
| `APPLE_APP_SPECIFIC_PASSWORD` | App-specific password |
| `APPLE_TEAM_ID` | Developer team ID |

## Quick start (development)

```bash
# 1. Install Electron deps
cd desktop/electron
npm install

# 2. Build the main process
npm run build        # or: npm run watch

# 3. Start with the Vite dev server running
cd ../../frontend
npm run dev &

# 4. Launch Electron (loads http://127.0.0.1:5173)
cd ../desktop/electron
npm start
```

## Building for distribution

### Windows

```powershell
cd desktop/scripts
.\build-win.ps1 -Version "0.1.0"
```

Produces `desktop/electron/dist-pack/LeAgent-Setup-0.1.0.exe`.

Flags: `-SkipRuntime`, `-SkipBackendPayload`, `-SkipFrontend`, `-SkipCompileall`.

### macOS

```bash
cd desktop/scripts
./build-mac.sh --version 0.1.0
```

Produces `desktop/electron/dist-pack/LeAgent-0.1.0.dmg` (+ `.zip`).

Flags: `--arch arm64`, `--skip-runtime`, `--skip-backend`, `--skip-frontend`.

### Linux (Ubuntu/Debian)

```bash
# Prerequisites
sudo apt-get install -y dpkg fakeroot libarchive-tools

cd desktop/scripts
./build-linux.sh --version 0.1.0
```

Produces `desktop/electron/dist-pack/LeAgent-0.1.0.AppImage` and `leagent-desktop_0.1.0_amd64.deb`.

Flags: `--target appimage`, `--target deb`, `--skip-runtime`, `--skip-backend`, `--skip-frontend`.

## First-launch behaviour

On the very first launch after installation, the app:

1. Creates a Python venv in `<userData>/runtime/venv/` using the bundled portable Python.
2. Runs `uv sync --frozen` to install backend dependencies from the bundled `uv.lock`.
3. Compiles `.pyc` bytecode for faster subsequent imports.
4. Runs `alembic upgrade head` to initialise the SQLite database.
5. Writes a version marker at `<userData>/runtime/.installed`.

Subsequent launches skip directly to step "start backend" (~2-3 s).

## User data locations

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/LeAgent/` |
| Windows | `%APPDATA%/LeAgent/` |
| Linux | `~/.config/LeAgent/` |

Sub-directories: `leagent/` (LEAGENT_HOME), `runtime/` (venv), `logs/` (main.log).

## Environment variables (desktop mode)

The Electron launcher sets these before spawning the backend:

| Variable | Value | Purpose |
|----------|-------|---------|
| `LEAGENT_DESKTOP` | `1` | Signals desktop mode to the backend |
| `LEAGENT_HOME` | `<userData>/leagent` | Data directory |
| `LEAGENT_FRONTEND_DIST` | `<resources>/frontend` | Enables SPA serving from backend |
| `VIRTUAL_ENV` | `<userData>/runtime/venv` | Python venv path |
