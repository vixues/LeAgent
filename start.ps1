#Requires -Version 5.1
<#
.SYNOPSIS
  LeAgent single-node start script (Windows / PowerShell).

.DESCRIPTION
  Mirrors start.sh: backend (uv + FastAPI), frontend (Vite or serve in prod),
  migrations, optional Playwright Chromium install, logs under ./logs.

  Run from repo root:  .\start.ps1
  Or:  powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1

.EXAMPLE
  .\start.ps1
  .\start.ps1 backend -Quiet
  .\start.ps1 stop
  .\start.ps1 fix-deps
  .\start.ps1 log monolith
  .\start.ps1 status
  .\start.ps1 build-frontend
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('all', 'backend', 'frontend', 'check', 'fix-deps', 'sync-python', 'build-frontend', 'status', 'log', 'stop')]
    [string] $Command = 'all',

    [Parameter(Position = 1)]
    [string] $LogService = '',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $RemainingArguments = @(),

    [switch] $Dev,
    [switch] $Prod,
    [switch] $Quiet,
    [switch] $SyncPython,
    [switch] $Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# ── Load .env (simple KEY=VALUE; Process scope) ─────────────────
$EnvFile = Join-Path $ScriptDir '.env'
if (Test-Path $EnvFile) {
    Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { return }
        if ($line -match '^\s*export\s+') { $line = $line -replace '^\s*export\s+', '' }
        $eq = $line.IndexOf('=')
        if ($eq -lt 1) { return }
        $key = $line.Substring(0, $eq).Trim()
        $val = $line.Substring($eq + 1).Trim()
        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        Set-Item -Path "Env:$key" -Value $val
    }
}

# ── Defaults ────────────────────────────────────────────────────
$BackendDir = Join-Path $ScriptDir 'backend'
if (-not $env:UV_PROJECT_ENVIRONMENT) {
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $BackendDir '.venv'
}

$BackendPort = if ($env:PORT) { $env:PORT } else { '7860' }
$FrontendPort = if ($env:FRONTEND_PORT) { $env:FRONTEND_PORT } else { '5173' }
$HostBind = if ($env:HOST) { $env:HOST } else { '0.0.0.0' }
$LogDir = if ($env:LEAGENT_LOG_DIR) { $env:LEAGENT_LOG_DIR } else { Join-Path $ScriptDir 'logs' }
$Mode = 'dev'
$StreamLogs = $true
$ForceUvSync = $false
$UvSyncExtras = if ($env:UV_SYNC_EXTRAS) { $env:UV_SYNC_EXTRAS } else { 'dev browser' }
$LogRetention = if ($env:LEAGENT_LOG_RETENTION) { [int]$env:LEAGENT_LOG_RETENTION } else { 5 }
$ShutdownGraceSec = if ($env:LEAGENT_SHUTDOWN_GRACE_SEC) { [int]$env:LEAGENT_SHUTDOWN_GRACE_SEC } else { 5 }

if (-not $env:PYTHONUNBUFFERED) { $env:PYTHONUNBUFFERED = '1' }
if (-not $env:PYTHONIOENCODING) { $env:PYTHONIOENCODING = 'utf-8' }

$script:ChildProcesses = [System.Collections.ArrayList]::new()
$script:TailJobs = @()
$script:NODE_BIN = $null
$script:NPM_BIN = $null

$LockFile = Join-Path $ScriptDir '.leagent.lock'

# ── Helpers ─────────────────────────────────────────────────────
function Print-Help {
    @'
Usage: .\start.ps1 [command] [options]

Commands:
  all            Start backend + frontend (default)
  backend        Start backend only
  frontend       Start frontend only
  check          Run environment readiness check
  status         Show whether services are running on configured ports
  fix-deps       Print manual install steps (git, uv, Node 20.19+ / 22.12+)
  sync-python    Lock + sync Python dependencies
  build-frontend Build the frontend for production (npm run build)
  log [name]     Tail logs (all *.log in logs/, or logs\<name>.log)
  stop           Kill processes listening on configured ports

Options:
  -Dev           Development mode (default)
  -Prod          Production mode (builds frontend, multi-worker backend)
  -Quiet         Do not stream logs to terminal
  -SyncPython    Force uv sync before backend start
  -Help          Show this help

  Bash-style (remaining args):  --dev  --prod  --quiet  --sync-python  --help  -h

Requirements:
  git, uv, npm, Node.js 20.19+ or 22.12+ (Vite 7)

Environment:
  PORT, FRONTEND_PORT, HOST, LEAGENT_LOG_DIR, LEAGENT_LOG_RETENTION,
  LEAGENT_SHUTDOWN_GRACE_SEC, UV_SYNC_EXTRAS,
  LEAGENT_SKIP_PLAYWRIGHT_INSTALL, LEAGENT_PLAYWRIGHT_MIRROR, PLAYWRIGHT_DOWNLOAD_HOST,
  UV_PROJECT_ENVIRONMENT
'@ | Write-Host
}

function Info([string] $Msg) { Write-Host "  ▸ $Msg" -ForegroundColor Blue }
function Success([string] $Msg) { Write-Host "  ✔ $Msg" -ForegroundColor Green }
function Warn([string] $Msg) { Write-Warning $Msg }
function Fail([string] $Msg) { Write-Error $Msg; exit 1 }
function Step([string] $Msg) { Write-Host "`n$Msg" -ForegroundColor White }

function Get-ElapsedSeconds([DateTime] $Start) {
    return '{0:0}s' -f ((Get-Date) - $Start).TotalSeconds
}

function Get-LeAgentVersion {
    $pyproject = Join-Path $BackendDir 'pyproject.toml'
    if (Test-Path $pyproject) {
        $match = Select-String -Path $pyproject -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($match) { return $match.Matches[0].Groups[1].Value }
    }
    return 'dev'
}

function Print-Banner {
    if ($Mode -eq 'prod') {
        Write-Host @'

  ╭──────────────────────────────────────────────────────────╮
  │          LeAgent  ──  Production Environment             │
  │                                                          │
  │  Backend   FastAPI  HTTP/WS/SSE  QueryEngine             │
  │  Frontend  React 19  Vite  ReactFlow                     │
  ╰──────────────────────────────────────────────────────────╯
'@ -ForegroundColor Cyan
    }
    else {
        Write-Host @'

  ╭──────────────────────────────────────────────────────────╮
  │          LeAgent  ──  Development Environment            │
  │                                                          │
  │  Backend   FastAPI  HTTP/WS/SSE  QueryEngine             │
  │  Frontend  React 19  Vite  ReactFlow                     │
  ╰──────────────────────────────────────────────────────────╯
'@ -ForegroundColor Cyan
    }
    Info "version  $(Get-LeAgentVersion)"
    Info "platform windows   mode $Mode"
    Info "backend  http://${HostBind}:${BackendPort}"
    Info "frontend http://localhost:${FrontendPort}"
    Write-Host ''
}

# ── Lock file ──────────────────────────────────────────────────
function Acquire-Lock {
    if (Test-Path $LockFile) {
        $lockPid = (Get-Content $LockFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($lockPid) {
            $proc = Get-Process -Id ([int]$lockPid) -ErrorAction SilentlyContinue
            if ($proc) {
                Fail "Another LeAgent instance is running (PID $lockPid). Use '.\start.ps1 stop' first, or remove $LockFile."
            }
        }
        Warn "Stale lock file found (PID $lockPid no longer running) — removing"
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    }
    $PID | Set-Content -Path $LockFile -Encoding UTF8
}

function Release-Lock {
    if (Test-Path $LockFile) {
        $lockPid = (Get-Content $LockFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($lockPid -eq "$PID") {
            Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
        }
    }
}

# ── Port management ────────────────────────────────────────────
function Get-PidsOnPort([int] $Port) {
    $pids = @()
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            if ($c.OwningProcess -and $c.OwningProcess -gt 0) {
                $pids += $c.OwningProcess
            }
        }
    }
    catch { }
    return ($pids | Sort-Object -Unique)
}

function Kill-Port([int] $Port) {
    $pids = Get-PidsOnPort $Port
    if ($pids.Count -eq 0) { return }

    foreach ($p in $pids) {
        try { Stop-Process -Id $p -ErrorAction SilentlyContinue } catch { }
    }

    $waited = 0
    while ($waited -lt $ShutdownGraceSec) {
        Start-Sleep -Seconds 1
        $waited++
        $remaining = Get-PidsOnPort $Port
        if ($remaining.Count -eq 0) { return }
    }

    $remaining = Get-PidsOnPort $Port
    foreach ($p in $remaining) {
        try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch { }
    }
}

function Ensure-LogDir {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }
}

# ── Log rotation ──────────────────────────────────────────────
function Rotate-Log([string] $LogPath) {
    if (-not (Test-Path $LogPath)) { return }
    if ((Get-Item $LogPath).Length -eq 0) { return }
    for ($i = $LogRetention; $i -gt 0; $i--) {
        $prev = if ($i -eq 1) { $LogPath } else { "$LogPath.$($i - 1)" }
        $curr = "$LogPath.$i"
        if (Test-Path $prev) {
            Move-Item -Path $prev -Destination $curr -Force -ErrorAction SilentlyContinue
        }
    }
}

function Get-UvExe {
    $g = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $g) { return $null }
    return $g.Source
}

function Test-NodeSupportsVite([string] $NodePath) {
    if (-not $NodePath -or -not (Test-Path $NodePath)) { return $false }
    $expr = "const [M,m]=process.versions.node.split('.').map(Number); process.stdout.write(String(Number((M === 20 && m >= 19) || (M === 22 && m >= 12) || M > 22))))"
    try {
        $out = & $NodePath -e $expr 2>$null
        return ($out -eq 'true' -or $out -eq '1')
    }
    catch { return $false }
}

function Get-NodeVersion([string] $NodePath) {
    if (-not $NodePath) { return 'missing' }
    try { return (& $NodePath -p 'process.versions.node' 2>$null) } catch { return 'unknown' }
}

function Activate-CompatibleNode {
    $nodeBin = (Get-Command node -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    $npmBin = (Get-Command npm -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    if ((Test-NodeSupportsVite $nodeBin) -and $npmBin) {
        $script:NODE_BIN = $nodeBin
        $script:NPM_BIN = $npmBin
        return $true
    }
    $nvmSymlink = Join-Path $env:ProgramFiles 'nodejs\node.exe'
    if ((Test-Path $nvmSymlink) -and (Test-NodeSupportsVite $nvmSymlink)) {
        $npmGuess = Join-Path $env:ProgramFiles 'nodejs\npm.cmd'
        if (Test-Path $npmGuess) {
            $script:NODE_BIN = $nvmSymlink
            $script:NPM_BIN = $npmGuess
            return $true
        }
    }
    return $false
}

function Show-FixDepsHints {
    Print-Banner
    Step 'fix-deps (Windows)'
    Write-Host @'
  Install manually (then re-run .\start.ps1):

  1. Git:   https://git-scm.com/download/win
  2. uv:    https://docs.astral.sh/uv/getting-started/installation/
            (or: irm https://astral.sh/uv/install.ps1 | iex)
  3. Node:  https://nodejs.org/  (LTS 22.x recommended for Vite 7)
            or nvm-windows: https://github.com/coreybutler/nvm-windows

  After installing, open a new terminal and run:  .\start.ps1 check
'@
    Success 'Hints printed'
}

function Test-Prerequisites {
    param([bool] $WantFrontend = $true)
    Step 'Checking prerequisites'
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Fail "git is not installed — https://git-scm.com/download/win"
    }
    Success "git $(git --version)"

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Fail "uv is not installed — https://docs.astral.sh/uv/"
    }
    $uvVer = ((uv --version) | Select-Object -First 1).ToString().Trim()
    Success "uv $uvVer"

    if ($WantFrontend) {
        [void](Activate-CompatibleNode)
        if (-not $script:NODE_BIN) {
            Fail "node is not installed — https://nodejs.org/"
        }
        if (-not $script:NPM_BIN) {
            Fail "npm is not found on PATH"
        }
        if (-not (Test-NodeSupportsVite $script:NODE_BIN)) {
            Fail "Node.js 20.19+ or 22.12+ required for Vite 7 (found v$(Get-NodeVersion $script:NODE_BIN)). Install Node 22 LTS or run nvm use 22, then retry."
        }
        Success "node $(& $script:NODE_BIN -v)  npm $(try { & $script:NPM_BIN -v } catch { '?' })"
    }
}

function Invoke-BackendUvSync {
    $uv = Get-UvExe
    if (-not $uv) { Fail 'uv not found' }
    $extraArgs = @()
    foreach ($e in ($UvSyncExtras -split '\s+')) {
        $t = $e.Trim()
        if ($t) { $extraArgs += @('--extra', $t) }
    }
    & $uv sync @extraArgs --directory $BackendDir
    if ($LASTEXITCODE -ne 0) { Fail 'uv sync failed' }
}

function Ensure-BackendSync {
    $lock = Join-Path $BackendDir 'uv.lock'
    if (-not (Test-Path $lock)) {
        Fail "backend/uv.lock is missing — run 'uv lock' in backend/"
    }
    $marker = Join-Path $BackendDir '.uv_sync_marker'
    $pyproject = Join-Path $BackendDir 'pyproject.toml'
    $need = $ForceUvSync -or -not (Test-Path $marker)
    if (-not $need -and (Test-Path $marker)) {
        if ((Get-Item $pyproject).LastWriteTimeUtc -gt (Get-Item $marker).LastWriteTimeUtc) { $need = $true }
        if ((Get-Item $lock).LastWriteTimeUtc -gt (Get-Item $marker).LastWriteTimeUtc) { $need = $true }
    }
    if ($need) {
        Step 'Syncing Python environment'
        Info "extras: $UvSyncExtras"
        $t0 = Get-Date
        Invoke-BackendUvSync
        New-Item -ItemType File -Path $marker -Force | Out-Null
        Success "Python environment ready ($(Get-ElapsedSeconds $t0))"
    }
}

function Ensure-PlaywrightBrowsers {
    if ($env:LEAGENT_SKIP_PLAYWRIGHT_INSTALL -eq '1') { return }
    if (" $UvSyncExtras " -notmatch '\s+browser\s+') { return }
    if (-not $env:PLAYWRIGHT_DOWNLOAD_HOST -and $env:LEAGENT_PLAYWRIGHT_MIRROR -eq '1') {
        $env:PLAYWRIGHT_DOWNLOAD_HOST = 'https://npmmirror.com/mirrors/playwright/'
    }
    $pwMarker = Join-Path $BackendDir '.playwright_chromium_marker'
    $lock = Join-Path $BackendDir 'uv.lock'
    if ((Test-Path $pwMarker) -and (Test-Path $lock)) {
        if ((Get-Item $pwMarker).LastWriteTimeUtc -gt (Get-Item $lock).LastWriteTimeUtc) { return }
    }
    $uv = Get-UvExe
    & $uv run --directory $BackendDir python -c "import playwright" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Warn "Playwright Python package missing — run uv sync with 'browser' extra or .\start.ps1 -SyncPython"
        return
    }
    Step 'Ensuring Playwright Chromium is installed'
    $t0 = Get-Date
    & $uv run --directory $BackendDir playwright install chromium
    if ($LASTEXITCODE -eq 0) {
        New-Item -ItemType File -Path $pwMarker -Force | Out-Null
        Success "Playwright Chromium ready ($(Get-ElapsedSeconds $t0))"
    }
    else {
        Warn 'playwright install chromium failed — set PLAYWRIGHT_DOWNLOAD_HOST or LEAGENT_PLAYWRIGHT_MIRROR=1 and retry'
    }
}

function Invoke-DatabaseMigrations {
    Ensure-BackendSync
    Step 'Applying database migrations'
    $t0 = Get-Date
    $uv = Get-UvExe
    & $uv run --directory $BackendDir alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Fail 'alembic upgrade failed' }
    Success "Migrations complete ($(Get-ElapsedSeconds $t0))"
}

function Install-FrontendDeps {
    $frontendDir = Join-Path $ScriptDir 'frontend'
    $nm = Join-Path $frontendDir 'node_modules'
    $pj = Join-Path $frontendDir 'package.json'
    $run = $false
    if (-not (Test-Path $nm)) { $run = $true }
    elseif ((Get-Item $pj).LastWriteTimeUtc -gt (Get-Item $nm).LastWriteTimeUtc) { $run = $true }
    if ($run) {
        Step 'Installing frontend dependencies'
        $t0 = Get-Date
        Push-Location $frontendDir
        try {
            $env:PATH = "$(Split-Path $script:NODE_BIN -Parent);$env:PATH"
            & $script:NPM_BIN install --silent
            if ($LASTEXITCODE -ne 0) { Fail 'npm install failed' }
        }
        finally { Pop-Location }
        Success "Frontend dependencies ready ($(Get-ElapsedSeconds $t0))"
    }
}

function Build-Frontend {
    Install-FrontendDeps
    $frontendDir = Join-Path $ScriptDir 'frontend'
    Step 'Building frontend for production'
    $t0 = Get-Date
    Push-Location $frontendDir
    try {
        $env:PATH = "$(Split-Path $script:NODE_BIN -Parent);$env:PATH"
        & $script:NPM_BIN run build
        if ($LASTEXITCODE -ne 0) { Fail 'npm run build failed' }
    }
    finally { Pop-Location }
    Success "Frontend build complete ($(Get-ElapsedSeconds $t0))"
}

function Start-LeAgentBackgroundCmd {
    param(
        [string] $Name,
        [string] $LogBase,
        [string] $CmdLine
    )
    Ensure-LogDir
    $logFile = Join-Path $LogDir "$LogBase.log"
    Rotate-Log $logFile
    '' | Set-Content -Path $logFile -Encoding UTF8
    Info "Starting $Name  -> $logFile"
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'cmd.exe'
    $psi.Arguments = "/c `"$CmdLine`""
    $psi.WorkingDirectory = $ScriptDir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    [void]$script:ChildProcesses.Add($p)
}

function Stop-TailJobs {
    foreach ($j in $script:TailJobs) {
        try {
            Stop-Job $j -Force -ErrorAction SilentlyContinue
            Remove-Job $j -Force -ErrorAction SilentlyContinue
        }
        catch { }
    }
    $script:TailJobs = @()
}

function Wait-StreamLogs {
    if ($script:ChildProcesses.Count -eq 0) {
        return
    }
    $backlog = if ($env:LEAGENT_LOG_BACKLOG) { [int]$env:LEAGENT_LOG_BACKLOG } else { 200 }
    $paths = @(
        (Join-Path $LogDir 'monolith.log'),
        (Join-Path $LogDir 'frontend.log')
    ) | Where-Object { Test-Path $_ }

    if ($paths.Count -eq 0) {
        foreach ($p in $script:ChildProcesses) {
            if ($p -and -not $p.HasExited) { $p.WaitForExit() }
        }
        return
    }

    Stop-TailJobs
    foreach ($lp in $paths) {
        $j = Start-Job -ScriptBlock {
            param($LiteralPath, $Tail)
            Get-Content -LiteralPath $LiteralPath -Tail $Tail -Wait -Encoding UTF8
        } -ArgumentList $lp, $backlog
        $script:TailJobs += $j
    }

    try {
        while ($true) {
            $any = $false
            foreach ($j in $script:TailJobs) {
                $chunk = @(Receive-Job -Job $j -ErrorAction SilentlyContinue)
                if ($chunk.Count -gt 0) {
                    $any = $true
                    $chunk | ForEach-Object { Write-Host $_ }
                }
            }
            $allDone = $true
            foreach ($p in $script:ChildProcesses) {
                if ($p -and -not $p.HasExited) { $allDone = $false; break }
            }
            if ($allDone) { break }
            if (-not $any) { Start-Sleep -Milliseconds 300 }
        }
    }
    finally {
        Stop-TailJobs
    }
}

function Wait-OrBackgroundMessage {
    if ($StreamLogs) {
        Wait-StreamLogs
    }
    else {
        Write-Host ''
        Success 'Services started in background'
        Info "Logs:  $LogDir"
        Info 'Tail:  Get-Content .\logs\monolith.log -Wait -Tail 200'
        Info 'Stop:  .\start.ps1 stop'
        foreach ($p in $script:ChildProcesses) {
            if ($p -and -not $p.HasExited) { $null = $p.WaitForExit() }
        }
    }
}

function Start-BackendService {
    Ensure-BackendSync
    Ensure-PlaywrightBrowsers
    Invoke-DatabaseMigrations
    Kill-Port ([int]$BackendPort)
    Step 'Starting backend'
    $uv = Get-UvExe
    $uvQ = $uv -replace '/', '\\'
    $bdQ = $BackendDir -replace '/', '\\'
    if ($Mode -eq 'prod') {
        $inner = "`"$uvQ`" run --directory `"$bdQ`" leagent app start --host $HostBind --port $BackendPort --workers 4 --production"
    }
    else {
        $inner = "`"$uvQ`" run --directory `"$bdQ`" leagent app start --host $HostBind --port $BackendPort --reload"
    }
    $logPath = (Join-Path $LogDir 'monolith.log') -replace '\\', '/'
    Start-LeAgentBackgroundCmd 'Backend' 'monolith' "$inner >> `"$logPath`" 2>&1"
}

function Start-FrontendService {
    Kill-Port ([int]$FrontendPort)
    $fe = (Join-Path $ScriptDir 'frontend') -replace '/', '\\'
    $nodeDir = (Split-Path $script:NODE_BIN -Parent) -replace '/', '\\'
    $logPath = (Join-Path $LogDir 'frontend.log') -replace '\\', '/'
    if ($Mode -eq 'prod') {
        Build-Frontend
        Step 'Starting frontend (static serve)'
        $inner = "cd /d `"$fe`" && set PATH=$nodeDir;%PATH% && npx --yes serve -s dist -l $FrontendPort"
    }
    else {
        Install-FrontendDeps
        Step 'Starting frontend (vite dev)'
        $viteApi = if ($env:VITE_API_PROXY_TARGET) { $env:VITE_API_PROXY_TARGET } else { "http://127.0.0.1:$BackendPort" }
        $viteWs = if ($env:VITE_WS_PROXY_TARGET) { $env:VITE_WS_PROXY_TARGET } else { "ws://127.0.0.1:$BackendPort" }
        $nodeExe = $script:NODE_BIN -replace '/', '\\'
        $inner = "cd /d `"$fe`" && set VITE_API_PROXY_TARGET=$viteApi&& set VITE_WS_PROXY_TARGET=$viteWs&& set PATH=$nodeDir;%PATH% && `"$nodeExe`" .\node_modules\vite\bin\vite.js --port $FrontendPort --host"
    }
    Start-LeAgentBackgroundCmd 'Frontend' 'frontend' "$inner >> `"$logPath`" 2>&1"
}

function Wait-BackendReady {
    $url = "http://127.0.0.1:$BackendPort/health"
    $max = 120
    Write-Host "  … Waiting for backend " -NoNewline
    for ($i = 0; $i -lt $max; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($r.StatusCode -eq 200) {
                Write-Host "`r  ✔ Backend is ready                    " -ForegroundColor Green
                return
            }
        }
        catch {
            Write-Host '.' -NoNewline
            Start-Sleep -Milliseconds 500
        }
    }
    Write-Host ''
    if ($Mode -eq 'prod') {
        Fail 'Backend health-check timed out after ~60s (production mode — aborting)'
    }
    Warn 'Backend health-check timed out after ~60s — continuing anyway'
}

# ── Status ─────────────────────────────────────────────────────
function Show-Status {
    Step 'LeAgent service status'
    $bPids = Get-PidsOnPort ([int]$BackendPort)
    $fPids = Get-PidsOnPort ([int]$FrontendPort)

    if ($bPids.Count -gt 0) {
        Success "Backend  listening on :$BackendPort  (PIDs: $($bPids -join ', '))"
    }
    else {
        Info "Backend  not running on :$BackendPort"
    }

    if ($fPids.Count -gt 0) {
        Success "Frontend listening on :$FrontendPort  (PIDs: $($fPids -join ', '))"
    }
    else {
        Info "Frontend not running on :$FrontendPort"
    }

    if (Test-Path $LockFile) {
        $lockPid = (Get-Content $LockFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        $proc = if ($lockPid) { Get-Process -Id ([int]$lockPid) -ErrorAction SilentlyContinue } else { $null }
        if ($proc) {
            Info "Lock     held by PID $lockPid"
        }
        else {
            Info "Lock     stale (PID $lockPid not running)"
        }
    }
    else {
        Info "Lock     no lock file"
    }
}

function Invoke-SystemCheck {
    Print-Banner
    Test-Prerequisites $true
    if (-not (Test-Path (Join-Path $BackendDir 'uv.lock'))) { Fail 'backend/uv.lock missing' }
    if (-not (Test-Path (Join-Path $ScriptDir 'frontend/package.json'))) { Fail 'frontend/package.json missing' }
    Step 'Verifying backend import'
    $uv = Get-UvExe
    & $uv run --directory $BackendDir python -c "import leagent.main; print('  ✔ leagent.main importable')"
    if ($LASTEXITCODE -ne 0) { Fail 'backend import check failed' }
    Write-Host ''
    Success 'All checks passed'
}

function Stop-LeAgentChildren {
    Write-Host ''
    Info "Shutting down (grace period: ${ShutdownGraceSec}s)..."
    Stop-TailJobs
    foreach ($p in $script:ChildProcesses) {
        try {
            if ($p -and -not $p.HasExited) {
                Stop-Process -Id $p.Id -ErrorAction SilentlyContinue
            }
        }
        catch { }
    }

    $waited = 0
    while ($waited -lt $ShutdownGraceSec) {
        $allDone = $true
        foreach ($p in $script:ChildProcesses) {
            if ($p -and -not $p.HasExited) { $allDone = $false; break }
        }
        if ($allDone) { break }
        Start-Sleep -Seconds 1
        $waited++
    }

    foreach ($p in $script:ChildProcesses) {
        try {
            if ($p -and -not $p.HasExited) {
                Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            }
        }
        catch { }
    }
    Kill-Port ([int]$BackendPort)
    Kill-Port ([int]$FrontendPort)
    Release-Lock
    Success 'Shutdown complete'
}

function Register-InterruptHandler {
    # Set-StrictMode Latest treats [Console]::CancelKeyPress as a missing property
    # (it is a .NET event). Register via reflection so Ctrl+C shutdown works on Windows.
    $handler = [ConsoleCancelEventHandler] {
        param($sender, $e)
        $e.Cancel = $true
        Stop-LeAgentChildren
        [Environment]::Exit(0)
    }
    try {
        [void][Console]::TreatControlCAsInput = $false
    }
    catch { }

    try {
        $ev = [type]::GetType('System.Console').GetEvent('CancelKeyPress')
        if ($null -ne $ev) {
            [void]$ev.AddEventHandler($null, $handler)
            $script:ConsoleCancelHandler = $handler
        }
    }
    catch {
        # Non-interactive host (ISE, redirected stdin, automation) — no console events
    }
}

# ── Remaining args (bash-style flags) ───────────────────────────
foreach ($a in $RemainingArguments) {
    switch ($a) {
        '--dev' { $Mode = 'dev' }
        '--prod' { $Mode = 'prod' }
        '--quiet' { $StreamLogs = $false }
        '--sync-python' { $ForceUvSync = $true }
        '--help' { Print-Help; exit 0 }
        '-h' { Print-Help; exit 0 }
        default { Fail "Unknown argument: $a (use -Help)" }
    }
}

if ($Help) { Print-Help; exit 0 }
if ($Dev) { $Mode = 'dev' }
if ($Prod) { $Mode = 'prod' }
if ($Quiet) { $StreamLogs = $false }
if ($SyncPython) { $ForceUvSync = $true }

Register-InterruptHandler

switch ($Command) {
    'sync-python' {
        Test-Prerequisites $false
        Step 'Locking and syncing Python environment'
        $uv = Get-UvExe
        & $uv lock --directory $BackendDir
        if ($LASTEXITCODE -ne 0) { Fail 'uv lock failed' }
        Invoke-BackendUvSync
        New-Item -ItemType File -Path (Join-Path $BackendDir '.uv_sync_marker') -Force | Out-Null
        Ensure-PlaywrightBrowsers
        Success 'Python environment ready'
    }
    'check' { Invoke-SystemCheck }
    'fix-deps' { Show-FixDepsHints }
    'build-frontend' {
        Test-Prerequisites $true
        Build-Frontend
    }
    'status' { Show-Status }
    'log' {
        Ensure-LogDir
        $backlog = if ($env:LEAGENT_LOG_BACKLOG) { [int]$env:LEAGENT_LOG_BACKLOG } else { 200 }
        if ($LogService) {
            $one = Join-Path $LogDir "$LogService.log"
            Get-Content $one -Tail $backlog -Wait -Encoding UTF8
        }
        else {
            $logs = @(Get-ChildItem -Path (Join-Path $LogDir '*.log') -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
            if ($logs.Count -eq 1) {
                Get-Content -LiteralPath $logs[0] -Tail $backlog -Wait -Encoding UTF8
            }
            elseif ($logs.Count -gt 1) {
                Info 'Multiple log files: following monolith.log (use: .\start.ps1 log <name>)'
                $m = Join-Path $LogDir 'monolith.log'
                if (Test-Path $m) {
                    Get-Content -LiteralPath $m -Tail $backlog -Wait -Encoding UTF8
                }
                else {
                    Get-Content -LiteralPath $logs[0] -Tail $backlog -Wait -Encoding UTF8
                }
            }
            else {
                Warn "No log files under $LogDir"
            }
        }
    }
    'stop' {
        Kill-Port ([int]$BackendPort)
        Kill-Port ([int]$FrontendPort)
        Release-Lock
        Success "Stopped LeAgent processes on ports $BackendPort, $FrontendPort"
    }
    'backend' {
        Acquire-Lock
        Print-Banner
        Test-Prerequisites $false
        Start-BackendService
        Wait-OrBackgroundMessage
    }
    'frontend' {
        Print-Banner
        Test-Prerequisites $true
        Start-FrontendService
        Wait-OrBackgroundMessage
    }
    default {
        Acquire-Lock
        Print-Banner
        Test-Prerequisites $true
        Start-BackendService
        Wait-BackendReady
        Start-FrontendService
        Wait-OrBackgroundMessage
    }
}
