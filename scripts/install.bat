@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM LeAgent Windows installer (self-contained CMD).
REM Usage:
REM   curl -fsSL https://vixues.com.cn/install.bat -o install.bat && install.bat
REM   scripts\install.bat
REM Optional environment (same as install.sh):
REM   LEAGENT_GIT_URL LEAGENT_CLONE_DIR LEAGENT_REF LEAGENT_SKIP_START
REM   LEAGENT_DRY_RUN LEAGENT_RUN_CHECK LEAGENT_SKIP_INIT LEAGENT_INSTALL_RETRIES
REM   UV_SYNC_EXTRAS UV_INDEX_URL UV_VENV_CLEAR
REM Clones or uses a local tree, checks git / Node / uv, then runs ./start.sh via Git Bash.

if not defined LEAGENT_GIT_URL set "LEAGENT_GIT_URL=https://github.com/vixues/LeAgent.git"
if not defined LEAGENT_CLONE_DIR set "LEAGENT_CLONE_DIR=%USERPROFILE%\leagent-desktop"
if not defined LEAGENT_REF set "LEAGENT_REF=main"
if not defined UV_SYNC_EXTRAS set "UV_SYNC_EXTRAS=dev browser"
if not defined UV_VENV_CLEAR set "UV_VENV_CLEAR=1"
if not defined LEAGENT_SKIP_START set "LEAGENT_SKIP_START=0"
if not defined LEAGENT_DRY_RUN set "LEAGENT_DRY_RUN=0"
if not defined LEAGENT_RUN_CHECK set "LEAGENT_RUN_CHECK=1"
if not defined LEAGENT_SKIP_INIT set "LEAGENT_SKIP_INIT=0"
if not defined LEAGENT_INSTALL_RETRIES set "LEAGENT_INSTALL_RETRIES=3"

set "FLAG_SKIPSTART=0"
set "FLAG_DRYRUN=0"
set "FLAG_NOCHECK=0"
set "FLAG_FROMSOURCE=0"
set "FLAG_SKIPINIT=0"

:argloop
if "%~1"=="" goto argdone
if /i "%~1"=="-Help" goto :help
if /i "%~1"=="/?" goto :help
if /i "%~1"=="--help" goto :help
if /i "%~1"=="-SkipStart" set "FLAG_SKIPSTART=1" & shift & goto :argloop
if /i "%~1"=="-SkipInit" set "FLAG_SKIPINIT=1" & shift & goto :argloop
if /i "%~1"=="-DryRun" set "FLAG_DRYRUN=1" & shift & goto :argloop
if /i "%~1"=="-NoCheck" set "FLAG_NOCHECK=1" & shift & goto :argloop
if /i "%~1"=="-FromSource" (
  set "FLAG_FROMSOURCE=1"
  if "%~2"=="" (
    echo [leagent] -FromSource requires a path 1>&2
    exit /b 1
  )
  set "LEAGENT_CLONE_DIR=%~2"
  shift & shift
  goto :argloop
)
if /i "%~1"=="-GitUrl" (
  if "%~2"=="" ( echo [leagent] -GitUrl requires a value 1>&2 & exit /b 1 )
  set "LEAGENT_GIT_URL=%~2"
  shift & shift
  goto :argloop
)
if /i "%~1"=="-Dir" (
  if "%~2"=="" ( echo [leagent] -Dir requires a path 1>&2 & exit /b 1 )
  set "LEAGENT_CLONE_DIR=%~2"
  shift & shift
  goto :argloop
)
if /i "%~1"=="-Ref" (
  if "%~2"=="" ( echo [leagent] -Ref requires a value 1>&2 & exit /b 1 )
  set "LEAGENT_REF=%~2"
  shift & shift
  goto :argloop
)
if /i "%~1"=="-Version" (
  if "%~2"=="" ( echo [leagent] -Version requires a value 1>&2 & exit /b 1 )
  set "LEAGENT_REF=%~2"
  shift & shift
  goto :argloop
)
if /i "%~1"=="-Extras" (
  if "%~2"=="" ( echo [leagent] -Extras requires a value 1>&2 & exit /b 1 )
  set "UV_SYNC_EXTRAS=%~2"
  shift & shift
  goto :argloop
)
echo [leagent] Unknown option: %~1  (try install.bat /?) 1>&2
exit /b 1

:argdone
if "%LEAGENT_SKIP_START%"=="1" set "FLAG_SKIPSTART=1"
if "%LEAGENT_DRY_RUN%"=="1" set "FLAG_DRYRUN=1"
if "%LEAGENT_RUN_CHECK%"=="0" set "FLAG_NOCHECK=1"
if "%LEAGENT_SKIP_INIT%"=="1" set "FLAG_SKIPINIT=1"

if "%FLAG_FROMSOURCE%"=="1" (
  for %%I in ("%LEAGENT_CLONE_DIR%") do set "LEAGENT_CLONE_DIR=%%~fI"
  if not exist "!LEAGENT_CLONE_DIR!\start.sh" (
    echo [leagent] start.sh not found in: !LEAGENT_CLONE_DIR! 1>&2
    exit /b 1
  )
) else (
  for %%I in ("%LEAGENT_CLONE_DIR%") do set "LEAGENT_CLONE_DIR=%%~fI"
)

where git >nul 2>nul || (
  echo [leagent] Git is required: https://git-scm.com/download/win 1>&2
  exit /b 1
)

where node >nul 2>nul || (
  echo [leagent] Node.js 20.19+ or 22.12+ is required: https://nodejs.org/ 1>&2
  exit /b 1
)
where npm >nul 2>nul || (
  echo [leagent] npm is required ^(install Node.js LTS^) 1>&2
  exit /b 1
)
for /f "delims=" %%V in ('node -p "const [M,m]=process.versions.node.split('.').map(Number); Number((M === 20 && m >= 19) || (M === 22 && m >= 12) || M > 22)" 2^>nul') do set "NODE_OK=%%V"
if not "!NODE_OK!"=="1" (
  for /f "delims=" %%N in ('node -v 2^>nul') do set "NODE_VER=%%N"
  echo [leagent] Node.js 20.19+ or 22.12+ required for Vite 7 ^(found !NODE_VER!^) 1>&2
  exit /b 1
)
echo [leagent] Node OK

set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>nul
if errorlevel 1 (
  if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
)
where uv >nul 2>nul
if errorlevel 1 (
  if "!FLAG_DRYRUN!"=="1" (
    echo [leagent] [dry-run] would install uv via Astral install script
  ) else (
    echo [leagent] Installing uv...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Expression (Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1')"
    if errorlevel 1 (
      echo [leagent] uv install failed 1>&2
      exit /b 1
    )
    set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
  )
)
where uv >nul 2>nul
if errorlevel 1 (
  echo [leagent] uv not on PATH. Add %USERPROFILE%\.local\bin to PATH and retry. 1>&2
  exit /b 1
)
echo [leagent] uv OK

if not defined UV_INDEX_URL (
  set "UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/"
  curl -fsS --connect-timeout 3 "https://pypi.org/pypi/pip/json" -o nul 2>nul
  if not errorlevel 1 (
    set "UV_INDEX_URL=https://pypi.org/simple/"
    echo [leagent] Using official PyPI index ^(connectivity OK^)
  ) else (
    echo [leagent] Using Aliyun PyPI mirror ^(official index unreachable^)
  )
) else (
  echo [leagent] UV_INDEX_URL already set: !UV_INDEX_URL!
)

echo.
echo [leagent] Target directory: !LEAGENT_CLONE_DIR!
echo [leagent] repository: !LEAGENT_GIT_URL!
echo [leagent] ref:        !LEAGENT_REF!
echo [leagent] PyPI index: !UV_INDEX_URL!
echo.

if "!FLAG_FROMSOURCE!"=="1" (
  echo [leagent] Using local source tree; skipping git clone.
) else if "!FLAG_DRYRUN!"=="1" (
  echo [leagent] [dry-run] would clone/update: !LEAGENT_GIT_URL! -^> !LEAGENT_CLONE_DIR! @ !LEAGENT_REF!
) else (
  if exist "!LEAGENT_CLONE_DIR!\.git" (
    echo [leagent] Updating existing repo at !LEAGENT_CLONE_DIR! ...
    set "_RETRY_COUNT=0"
    :fetch_retry
    git -C "!LEAGENT_CLONE_DIR!" fetch --depth 1 origin "!LEAGENT_REF!" 2>nul
    if errorlevel 1 (
      set /a "_RETRY_COUNT+=1"
      if !_RETRY_COUNT! lss !LEAGENT_INSTALL_RETRIES! (
        echo [leagent] Fetch attempt !_RETRY_COUNT! failed, retrying...
        timeout /t 2 /nobreak >nul
        goto :fetch_retry
      )
      git -C "!LEAGENT_CLONE_DIR!" fetch origin
    )
    git -C "!LEAGENT_CLONE_DIR!" checkout "!LEAGENT_REF!"
    if errorlevel 1 (
      echo [leagent] git checkout failed for ref: !LEAGENT_REF! 1>&2
      exit /b 1
    )
    git -C "!LEAGENT_CLONE_DIR!" pull --ff-only 2>nul
  ) else if exist "!LEAGENT_CLONE_DIR!" (
    echo [leagent] Path exists and is not a git repo: !LEAGENT_CLONE_DIR! 1>&2
    exit /b 1
  ) else (
    echo [leagent] Cloning !LEAGENT_GIT_URL! -^> !LEAGENT_CLONE_DIR! ^(ref: !LEAGENT_REF!^) ...
    set "_RETRY_COUNT=0"
    :clone_retry
    git clone --depth 1 --branch "!LEAGENT_REF!" "!LEAGENT_GIT_URL!" "!LEAGENT_CLONE_DIR!"
    if errorlevel 1 (
      set /a "_RETRY_COUNT+=1"
      if !_RETRY_COUNT! lss !LEAGENT_INSTALL_RETRIES! (
        echo [leagent] Clone attempt !_RETRY_COUNT! failed, retrying...
        if exist "!LEAGENT_CLONE_DIR!" rmdir /s /q "!LEAGENT_CLONE_DIR!" 2>nul
        timeout /t 2 /nobreak >nul
        goto :clone_retry
      )
      echo [leagent] Shallow clone failed; trying full clone ...
      if exist "!LEAGENT_CLONE_DIR!" rmdir /s /q "!LEAGENT_CLONE_DIR!" 2>nul
      git clone "!LEAGENT_GIT_URL!" "!LEAGENT_CLONE_DIR!"
      if errorlevel 1 (
        echo [leagent] git clone failed 1>&2
        exit /b 1
      )
      git -C "!LEAGENT_CLONE_DIR!" checkout "!LEAGENT_REF!"
      if errorlevel 1 (
        echo [leagent] git checkout failed for ref: !LEAGENT_REF! 1>&2
        exit /b 1
      )
    )
  )
)

if "!FLAG_DRYRUN!"=="1" (
  echo [leagent] [dry-run] done.
  exit /b 0
)

if not exist "!LEAGENT_CLONE_DIR!\start.sh" (
  echo [leagent] start.sh not found in: !LEAGENT_CLONE_DIR! 1>&2
  exit /b 1
)

set "BASH_EXE="
if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles(x86)%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%LOCALAPPDATA%\Programs\Git\bin\bash.exe" set "BASH_EXE=%LOCALAPPDATA%\Programs\Git\bin\bash.exe"
if not defined BASH_EXE (
  for /f "delims=" %%G in ('where git 2^>nul') do (
    for %%H in ("%%~dpG..") do (
      if exist "%%~fH\bin\bash.exe" set "BASH_EXE=%%~fH\bin\bash.exe"
    )
    goto :bash_search_done
  )
)
:bash_search_done
if not defined BASH_EXE (
  echo [leagent] Git Bash not found. Install Git for Windows. 1>&2
  exit /b 1
)

REM Git Bash cd path: C:\Users\... -> /C/Users/...
set "FD=!LEAGENT_CLONE_DIR!"
for %%I in ("!FD!") do set "FD=%%~fI"
set "DRIVE=!FD:~0,1!"
set "REST=!FD:~3!"
set "REST=!REST:\=/!"
set "UNIX_DIR=/!DRIVE!/!REST!"

REM Properly quote UV_SYNC_EXTRAS in the bash export.
set "SAFE_EXTRAS=!UV_SYNC_EXTRAS:'='\''!"
set "SAFE_INDEX=!UV_INDEX_URL:'='\''!"
set "BASH_PREFIX=export UV_SYNC_EXTRAS='!SAFE_EXTRAS!' UV_INDEX_URL='!SAFE_INDEX!' UV_VENV_CLEAR='!UV_VENV_CLEAR!'; "

if not "!FLAG_SKIPINIT!"=="1" (
  if "!FLAG_DRYRUN!"=="0" (
    echo [leagent] Running ./start.sh sync-python and leagent init --defaults ...
    "!BASH_EXE!" -lc "!BASH_PREFIX!cd '!UNIX_DIR!' && chmod +x start.sh 2>/dev/null; ./start.sh sync-python && uv run --directory backend leagent init --defaults"
    if errorlevel 1 (
      echo [leagent] sync-python / leagent init failed 1>&2
      exit /b 1
    )
  )
)

if "!FLAG_NOCHECK!"=="0" if "!FLAG_SKIPSTART!"=="0" (
  echo [leagent] Running ./start.sh check ...
  "!BASH_EXE!" -lc "!BASH_PREFIX!cd '!UNIX_DIR!' && chmod +x start.sh 2>/dev/null; ./start.sh check"
  if errorlevel 1 (
    echo [leagent] ./start.sh check failed 1>&2
    exit /b 1
  )
)

if "!FLAG_SKIPSTART!"=="1" (
  echo [leagent] Skip start — not launching services.
  echo.
  echo LeAgent install finished.
  echo   Directory: !LEAGENT_CLONE_DIR!
  echo.
  echo [leagent] Next: cd /d "!LEAGENT_CLONE_DIR!" ^& start.sh   ^(via Git Bash: ./start.sh^)
  exit /b 0
)

echo [leagent] Starting LeAgent ^(./start.sh all^) ...
"!BASH_EXE!" -lc "!BASH_PREFIX!cd '!UNIX_DIR!' && exec ./start.sh all"
exit /b %ERRORLEVEL%

:help
echo LeAgent Windows installer ^(CMD^)
echo.
echo Usage: install.bat [options]
echo   -GitUrl ^<url^>        Git clone URL
echo   -Dir ^<path^>          Install directory ^(default: %%USERPROFILE%%\leagent-desktop^)
echo   -Ref ^<ref^>           Branch or tag ^(default: main^)
echo   -Version ^<ref^>       Same as -Ref
echo   -FromSource ^<path^>   Use existing checkout ^(skips git clone^)
echo   -Extras ^<names^>     uv sync extras ^(default: dev browser^)
echo   -SkipStart            Do not run start.sh
echo   -SkipInit             Skip sync-python + leagent init --defaults
echo   -DryRun               Print planned steps only
echo   -NoCheck              Skip start.sh check
echo   -Help /?
echo.
echo Environment: LEAGENT_GIT_URL LEAGENT_CLONE_DIR LEAGENT_REF LEAGENT_SKIP_START
echo   LEAGENT_DRY_RUN LEAGENT_RUN_CHECK LEAGENT_SKIP_INIT LEAGENT_INSTALL_RETRIES
echo   UV_SYNC_EXTRAS UV_INDEX_URL UV_VENV_CLEAR
echo.
echo Examples:
echo   curl -fsSL https://vixues.com.cn/install.bat -o install.bat ^&^& install.bat
echo   scripts\install.bat -SkipStart
exit /b 0
