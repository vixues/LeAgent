#requires -Version 5.1
<#
.SYNOPSIS
  Build LeAgent Desktop for Windows (x64).

.DESCRIPTION
  Downloads portable Python + uv, stages the backend payload, builds the
  frontend (Vite), compiles the Electron main process, and runs
  electron-builder to produce an NSIS installer.

.PARAMETER Version
  Semantic version string baked into the installer. Default: "0.1.0".

.PARAMETER SkipRuntime
  Skip downloading python-build-standalone and uv.

.PARAMETER SkipBackendPayload
  Skip copying the backend source tree.

.PARAMETER SkipFrontend
  Skip the frontend npm ci / build step.

.PARAMETER SkipCompileall
  Skip pre-compiling .pyc bytecode for bundled Python packages.

.PARAMETER Channel
  Release channel embedded in the package name: "stable" or "beta".
#>
param(
  [string]$Version = "0.1.0",
  [switch]$SkipRuntime,
  [switch]$SkipBackendPayload,
  [switch]$SkipFrontend,
  [switch]$SkipCompileall,
  [ValidateSet("stable","beta")]
  [string]$Channel = "stable"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DesktopElectron = Join-Path $Repo "desktop\electron"

Write-Host "============================================"
Write-Host "  LeAgent Desktop — Windows Build"
Write-Host "  Version : $Version"
Write-Host "  Channel : $Channel"
Write-Host "============================================"

# ── 1. Icons ──
Write-Host "`n==> make-icons.mjs"
$iconScript = Join-Path $PSScriptRoot "make-icons.mjs"
try {
  node $iconScript
} catch {
  Write-Warning "Icon generation failed: $_  (non-fatal)"
}

# ── 2. Runtime (Python + uv) ──
if (-not $SkipRuntime) {
  Write-Host "`n==> prepare-runtime.mjs --platform win-x64"
  node (Join-Path $PSScriptRoot "prepare-runtime.mjs") --platform win-x64
  if ($LASTEXITCODE -ne 0) { throw "prepare-runtime.mjs failed (exit $LASTEXITCODE)" }
} else {
  Write-Warning "SkipRuntime: python-build-standalone + uv not refreshed."
}

# ── 3. Backend payload ──
if (-not $SkipBackendPayload) {
  Write-Host "`n==> prepare-backend-payload.mjs"
  node (Join-Path $PSScriptRoot "prepare-backend-payload.mjs")
  if ($LASTEXITCODE -ne 0) { throw "prepare-backend-payload.mjs failed (exit $LASTEXITCODE)" }
} else {
  Write-Warning "SkipBackendPayload: backend source tree not refreshed."
}

# ── 4. Frontend build ──
if (-not $SkipFrontend) {
  Write-Host "`n==> Frontend build (Vite)"
  $frontendDir = Join-Path $Repo "frontend"
  Push-Location $frontendDir
  try {
    $env:VITE_DESKTOP = "true"
    $env:VITE_API_BASE_URL = "http://127.0.0.1:7860/api/v1"
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed in frontend (exit $LASTEXITCODE)" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed in frontend (exit $LASTEXITCODE)" }
  } finally {
    Remove-Item Env:\VITE_DESKTOP -ErrorAction SilentlyContinue
    Remove-Item Env:\VITE_API_BASE_URL -ErrorAction SilentlyContinue
    Pop-Location
  }
} else {
  Write-Warning "SkipFrontend: frontend/dist not rebuilt."
}

# ── 5. Compile bytecode ──
if (-not $SkipCompileall) {
  $payloadDir = Join-Path $DesktopElectron "resources\backend-payload"
  $runtimePy = Join-Path $DesktopElectron "resources\runtime\win-x64\python\python.exe"
  $runtimeWorks = $false
  if (Test-Path $runtimePy) {
    try {
      & $runtimePy --version *> $null
      $runtimeWorks = ($LASTEXITCODE -eq 0)
    } catch {
      $runtimeWorks = $false
    }
  }

  if ($runtimeWorks) {
    Write-Host "`n==> compileall backend payload"
    $leagentPkg = Join-Path $payloadDir "leagent"
    if (Test-Path $leagentPkg) {
      & $runtimePy -m compileall -q $leagentPkg
      if ($LASTEXITCODE -ne 0) { Write-Warning "compileall exited $LASTEXITCODE (non-fatal)" }
    }
  } else {
    Write-Warning "Compatible bundled Python not found at $runtimePy — skipping compileall."
  }
} else {
  Write-Warning "SkipCompileall: .pyc cache not refreshed."
}

# ── 6. Electron build + pack ──
Write-Host "`n==> Electron npm ci + build + pack"
Push-Location $DesktopElectron
try {
  npm ci
  if ($LASTEXITCODE -ne 0) { throw "npm ci failed in desktop/electron (exit $LASTEXITCODE)" }

  npm run build
  if ($LASTEXITCODE -ne 0) { throw "npm run build (tsc) failed (exit $LASTEXITCODE)" }

  $env:VERSION = $Version
  npx electron-builder --win --x64 --config electron-builder.yml "--c.extraMetadata.version=$Version"
  if ($LASTEXITCODE -ne 0) { throw "electron-builder failed (exit $LASTEXITCODE)" }
} finally {
  Pop-Location
}

# ── 7. Report ──
Write-Host "`n==> Build complete"
$distPack = Join-Path $DesktopElectron "dist-pack"
$setup = Get-ChildItem -Path $distPack -Filter "LeAgent-Setup-*.exe" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
if ($setup) {
  $h = Get-FileHash -Path $setup.FullName -Algorithm SHA256
  Write-Host ("Installer : {0}" -f $setup.Name)
  Write-Host ("Size      : {0:N0} bytes ({1:N1} MB)" -f $setup.Length, ($setup.Length / 1MB))
  Write-Host ("SHA-256   : {0}" -f $h.Hash)
} else {
  Write-Host "Artifacts under: $distPack"
  Get-ChildItem $distPack -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ("  {0} ({1:N1} MB)" -f $_.Name, ($_.Length / 1MB)) }
}
