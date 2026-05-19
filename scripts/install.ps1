#Requires -Version 5.1
<#
.SYNOPSIS
  LeAgent installer for Windows — clone repo (or use local tree), ensure uv + Node, run ./start.sh via Git Bash.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
  powershell -ExecutionPolicy Bypass -c "iwr -useb https://vixues.com.cn/install.ps1 | iex"

.NOTES
  Environment variables still apply: LEAGENT_GIT_URL, LEAGENT_CLONE_DIR, LEAGENT_REF, LEAGENT_SKIP_START,
  LEAGENT_DRY_RUN, LEAGENT_RUN_CHECK, UV_SYNC_EXTRAS, UV_INDEX_URL, UV_VENV_CLEAR, LEAGENT_INSTALL_RETRIES
#>

param(
    [string]$GitUrl,
    [string]$Dir,
    [string]$Ref,
    [string]$Version,
    [string]$Extras,
    [string]$FromSource,
    [switch]$SkipStart,
    [switch]$SkipInit,
    [switch]$DryRun,
    [switch]$NoCheck,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

function Write-LeAgentInfo([string]$msg) { Write-Host "[leagent] $msg" -ForegroundColor Green }
function Write-LeAgentWarn([string]$msg) { Write-Host "[leagent] $msg" -ForegroundColor Yellow }

$GitUrl = if ($GitUrl) { $GitUrl } elseif ($env:LEAGENT_GIT_URL) { $env:LEAGENT_GIT_URL } else { 'https://github.com/vixues/LeAgent.git' }
$CloneDir = if ($Dir) { $Dir } elseif ($env:LEAGENT_CLONE_DIR) { $env:LEAGENT_CLONE_DIR } else { Join-Path $HOME 'leagent-desktop' }
$Ref = if ($Ref) { $Ref } elseif ($Version) { $Version } elseif ($env:LEAGENT_REF) { $env:LEAGENT_REF } else { 'main' }
$SkipStart = $SkipStart -or ($env:LEAGENT_SKIP_START -eq '1')
$SkipInit = $SkipInit -or ($env:LEAGENT_SKIP_INIT -eq '1')
$DryRun = $DryRun -or ($env:LEAGENT_DRY_RUN -eq '1')
$RunCheck = if ($NoCheck) { $false } elseif ($null -eq $env:LEAGENT_RUN_CHECK -or $env:LEAGENT_RUN_CHECK -eq '1') { $true } else { $false }
$MaxRetries = if ($env:LEAGENT_INSTALL_RETRIES) { [int]$env:LEAGENT_INSTALL_RETRIES } else { 3 }

if ($Extras) { $env:UV_SYNC_EXTRAS = $Extras }
elseif ($null -ne $env:UV_SYNC_EXTRAS) { }
else { $env:UV_SYNC_EXTRAS = 'dev browser' }

if ($null -eq $env:UV_VENV_CLEAR -or $env:UV_VENV_CLEAR -eq '') {
    $env:UV_VENV_CLEAR = '1'
}

function Choose-PypiMirror {
    try {
        $null = Invoke-WebRequest -Uri 'https://pypi.org/pypi/pip/json' -TimeoutSec 3 -UseBasicParsing -Method Get
        Write-LeAgentInfo 'Using official PyPI index (connectivity OK)'
        return 'https://pypi.org/simple/'
    }
    catch {
        Write-LeAgentInfo 'Using Aliyun PyPI mirror (official index unreachable)'
        return 'https://mirrors.aliyun.com/pypi/simple/'
    }
}

if (-not $env:UV_INDEX_URL) {
    $env:UV_INDEX_URL = Choose-PypiMirror
}
else {
    Write-LeAgentInfo "UV_INDEX_URL already set: $($env:UV_INDEX_URL)"
}

function Show-InstallHelp {
    @'
LeAgent installer — clones the repo (or uses a local tree), ensures uv + Node.js,
then runs ./start.sh via Git Bash.

Usage:
  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 [options]

Parameters:
  -GitUrl <url>        Git clone URL
  -Dir <path>         Install directory (default: ~/leagent-desktop)
  -Ref <ref>          Branch or tag (default: main)
  -Version <ref>      Same as -Ref
  -FromSource <path>  Use existing checkout (skips git clone)
  -Extras <names>     uv sync extras (default: dev browser)
  -SkipStart          Do not run start.sh
  -SkipInit           Skip sync-python + leagent init --defaults
  -DryRun             Print planned steps only
  -NoCheck            Skip start.sh check
  -Help               Show this help

Environment: LEAGENT_GIT_URL, LEAGENT_CLONE_DIR, LEAGENT_REF, LEAGENT_SKIP_START,
  LEAGENT_DRY_RUN, LEAGENT_RUN_CHECK, LEAGENT_SKIP_INIT, LEAGENT_INSTALL_RETRIES,
  UV_SYNC_EXTRAS, UV_INDEX_URL, UV_VENV_CLEAR

Examples:
  iwr -useb https://vixues.com.cn/install.ps1 | iex
  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -SkipStart
'@ | Write-Host
}

if ($Help) {
    Show-InstallHelp
    exit 0
}

function Find-GitBash {
    $pf86 = [Environment]::GetFolderPath('ProgramFilesX86')
    $candidates = [System.Collections.ArrayList]@()
    [void]$candidates.Add((Join-Path $env:ProgramFiles 'Git\bin\bash.exe'))
    if ($pf86) { [void]$candidates.Add((Join-Path $pf86 'Git\bin\bash.exe')) }
    [void]$candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\Git\bin\bash.exe'))
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if ($gitCmd) {
        $gitRoot = Split-Path (Split-Path $gitCmd.Source -Parent) -Parent
        $bash = Join-Path $gitRoot 'bin\bash.exe'
        if (Test-Path -LiteralPath $bash) { return $bash }
    }
    return $null
}

function ConvertTo-GitBashPath([string]$PathStr) {
    $full = [System.IO.Path]::GetFullPath($PathStr)
    if ($full -match '^([A-Za-z]):\\(.*)$') {
        $drive = $Matches[1].ToLowerInvariant()
        $rest = $Matches[2] -replace '\\', '/'
        return "/$drive/$rest"
    }
    return $PathStr -replace '\\', '/'
}

function Test-NodeSupportsVite {
    $ok = & node -p "const [M,m]=process.versions.node.split('.').map(Number); Number((M === 20 && m >= 19) || (M === 22 && m >= 12) || M > 22)" 2>$null
    return ($ok -eq '1')
}

function Ensure-Node {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) {
        throw 'Node.js 20.19+ or 22.12+ is required: https://nodejs.org/'
    }
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npm) {
        throw 'npm is required (install current Node.js LTS)'
    }
    if (-not (Test-NodeSupportsVite)) {
        throw "Node.js 20.19+ or 22.12+ required for Vite 7 (found $(node -v))"
    }
    Write-LeAgentInfo "Node $(node -p 'process.versions.node') OK"
}

function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-LeAgentInfo "uv found: $(Get-Command uv | Select-Object -ExpandProperty Source)"
        return
    }
    $localUv = Join-Path $HOME '.local\bin\uv.exe'
    $cargoUv = Join-Path $HOME '.cargo\bin\uv.exe'
    foreach ($p in @($localUv, $cargoUv)) {
        if (Test-Path -LiteralPath $p) {
            $dir = Split-Path $p -Parent
            $env:PATH = "$dir;$env:PATH"
            Write-LeAgentInfo "uv found: $p"
            return
        }
    }
    if ($DryRun) {
        Write-LeAgentInfo '[dry-run] would install uv via https://astral.sh/uv/install.ps1'
        return
    }
    Write-LeAgentInfo 'Installing uv...'
    Invoke-Expression (Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1')
    $localBin = Join-Path $HOME '.local\bin'
    $cargoBin = Join-Path $HOME '.cargo\bin'
    if (Test-Path $localBin) { $env:PATH = "$localBin;$env:PATH" }
    if (Test-Path $cargoBin) { $env:PATH = "$cargoBin;$env:PATH" }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv installed but not on PATH; add $localBin or restart the terminal"
    }
    Write-LeAgentInfo 'uv installed successfully'
}

function Invoke-WithRetry {
    param(
        [ScriptBlock]$ScriptBlock,
        [int]$Retries = $MaxRetries,
        [string]$Label = 'command'
    )
    $attempt = 1
    $delay = 2
    while ($attempt -le $Retries) {
        try {
            & $ScriptBlock
            return
        }
        catch {
            if ($attempt -eq $Retries) { throw }
            Write-LeAgentWarn "Attempt $attempt/$Retries for $Label failed, retrying in ${delay}s..."
            Start-Sleep -Seconds $delay
            $delay *= 2
            $attempt++
        }
    }
}

function Invoke-GitCloneOrUpdate {
    param([string]$Url, [string]$TargetDir, [string]$Branch)
    if ($DryRun) {
        Write-LeAgentInfo "[dry-run] git clone/update $Url -> $TargetDir @ $Branch"
        return
    }
    if (Test-Path (Join-Path $TargetDir '.git')) {
        Write-LeAgentInfo "Updating existing repo at $TargetDir ..."
        Invoke-WithRetry -Label 'git fetch' -ScriptBlock {
            git -C $TargetDir fetch --depth 1 origin $Branch 2>$null
            if ($LASTEXITCODE -ne 0) { git -C $TargetDir fetch origin }
            if ($LASTEXITCODE -ne 0) { throw 'git fetch failed' }
        }
        git -C $TargetDir checkout $Branch
        if ($LASTEXITCODE -ne 0) { throw "could not checkout $Branch" }
        git -C $TargetDir pull --ff-only 2>$null
    }
    elseif (Test-Path -LiteralPath $TargetDir) {
        throw "Path exists and is not a git repo: $TargetDir"
    }
    else {
        Write-LeAgentInfo "Cloning $Url -> $TargetDir (ref: $Branch) ..."
        $shallowCloned = $false
        try {
            Invoke-WithRetry -Label 'git clone' -ScriptBlock {
                if (Test-Path -LiteralPath $TargetDir) {
                    Remove-Item -LiteralPath $TargetDir -Recurse -Force -ErrorAction SilentlyContinue
                }
                git clone --depth 1 --branch $Branch $Url $TargetDir
                if ($LASTEXITCODE -ne 0) { throw 'shallow clone failed' }
            }
            $shallowCloned = $true
        }
        catch {
            Write-LeAgentWarn 'Shallow branch clone failed; full clone ...'
        }
        if (-not $shallowCloned) {
            if (Test-Path -LiteralPath $TargetDir) {
                Remove-Item -LiteralPath $TargetDir -Recurse -Force -ErrorAction SilentlyContinue
            }
            Invoke-WithRetry -Label 'git clone (full)' -ScriptBlock {
                git clone $Url $TargetDir
                if ($LASTEXITCODE -ne 0) { throw 'git clone failed' }
            }
            git -C $TargetDir checkout $Branch
            if ($LASTEXITCODE -ne 0) { throw "could not checkout $Branch" }
        }
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git is required: https://git-scm.com/download/win'
}

if ($PSBoundParameters.ContainsKey('FromSource')) {
    if ([string]::IsNullOrWhiteSpace($FromSource)) {
        throw '-FromSource requires a path (see -Help)'
    }
    $CloneDir = [System.IO.Path]::GetFullPath($FromSource)
    $startLocal = Join-Path $CloneDir 'start.sh'
    if (-not (Test-Path -LiteralPath $startLocal)) {
        throw "start.sh not found in $CloneDir (-FromSource)"
    }
}

Ensure-Node
Ensure-Uv

Write-Host ''
Write-LeAgentInfo "Target directory: $CloneDir"
Write-LeAgentInfo "repository: $GitUrl"
Write-LeAgentInfo "ref:        $Ref"
Write-LeAgentInfo "PyPI index: $($env:UV_INDEX_URL)"
Write-Host ''

if ($PSBoundParameters.ContainsKey('FromSource')) {
    Write-LeAgentInfo 'Using local source tree (-FromSource); skipping git clone.'
}
else {
    Invoke-GitCloneOrUpdate -Url $GitUrl -TargetDir $CloneDir -Branch $Ref
}

if ($DryRun) {
    Write-LeAgentInfo '[dry-run] done.'
    exit 0
}

$startSh = Join-Path $CloneDir 'start.sh'
if (-not (Test-Path -LiteralPath $startSh)) {
    throw "start.sh not found in $CloneDir"
}

$bash = Find-GitBash
if (-not $bash) {
    throw 'Git Bash not found. Install Git for Windows: https://git-scm.com/download/win'
}

$unixDir = ConvertTo-GitBashPath $CloneDir

$exportExtras = $env:UV_SYNC_EXTRAS.Replace("'", "'\''")
$exportIndex = $env:UV_INDEX_URL.Replace("'", "'\''")
$exportVenvClear = $env:UV_VENV_CLEAR
$bashPrefix = "export UV_SYNC_EXTRAS='$exportExtras' UV_INDEX_URL='$exportIndex' UV_VENV_CLEAR='$exportVenvClear'; "

if (-not $SkipInit) {
    Write-LeAgentInfo 'Running ./start.sh sync-python and leagent init --defaults ...'
    & $bash @('-lc', "${bashPrefix}cd '$unixDir' && { chmod +x start.sh 2>/dev/null || true; ./start.sh sync-python && uv run --directory backend leagent init --defaults; }")
    if ($LASTEXITCODE -ne 0) { throw './start.sh sync-python / leagent init failed' }
}

if ($RunCheck -and -not $SkipStart) {
    Write-LeAgentInfo 'Running ./start.sh check ...'
    & $bash @('-lc', "${bashPrefix}cd '$unixDir' && { chmod +x start.sh 2>/dev/null || true; ./start.sh check; }")
    if ($LASTEXITCODE -ne 0) { throw './start.sh check failed' }
}

if ($SkipStart) {
    Write-LeAgentInfo 'Skip start requested — not launching services.'
    Write-Host ''
    Write-Host 'LeAgent install finished.' -ForegroundColor Green
    Write-Host "  Directory: $CloneDir"
    Write-Host ''
    Write-LeAgentInfo "Next: cd '$CloneDir'; bash start.sh"
    exit 0
}

Write-LeAgentInfo 'Starting LeAgent (./start.sh all) ...'
& $bash @('-lc', "${bashPrefix}cd '$unixDir' && exec ./start.sh all")
exit $LASTEXITCODE
