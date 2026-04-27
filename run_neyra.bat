@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul
title Neyra Launcher

set "PY="
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Install Python 3.10+ and rerun this launcher.
    pause
    goto end
  )
  set "PY=python"
)
set "PIP=%PY% -m pip"

:print_header
echo.
echo ==========================================
echo   Neyra 2.0 Launcher (Windows)
echo ==========================================
set "PY_EXE=%PY%"
echo Python: !PY_EXE!
if exist ".venv\Scripts\python.exe" (
  echo Virtualenv: detected ^(.venv^)
) else (
  echo Virtualenv: not found ^(using global interpreter^)
)
echo.

echo [1/3] Checking system dependencies...
set "SYS_MISSING="
where git >nul 2>&1 || set "SYS_MISSING=!SYS_MISSING! git"
where ffmpeg >nul 2>&1 || set "SYS_MISSING=!SYS_MISSING! ffmpeg"
if defined SYS_MISSING (
  echo [WARN] Missing system tools:!SYS_MISSING!
  echo        git is recommended for updates, ffmpeg is recommended for media workflows.
) else (
  echo [OK] System dependencies are installed.
)
echo.

echo [2/3] Checking Python dependencies in the active interpreter...
set "MISSING_MODULES="
for %%m in (yaml dotenv requests fastapi uvicorn discord wavelink PIL langchain langchain_openai chromadb sentence_transformers apscheduler ddgs) do (
  "%PY%" -c "import %%m" >nul 2>&1
  if errorlevel 1 set "MISSING_MODULES=!MISSING_MODULES! %%m"
)
if defined MISSING_MODULES (
  echo [WARN] Missing Python modules:!MISSING_MODULES!
  echo.
  set /p INSTALL_MISSING=Install missing dependencies from requirements.txt now? [y/N]: 
  if /I "!INSTALL_MISSING!"=="y" (
    %PIP% install -r requirements.txt
    if errorlevel 1 (
      echo [ERROR] Dependency installation failed.
      pause
      goto end
    )
    set "MISSING_MODULES="
    for %%m in (yaml dotenv requests fastapi uvicorn discord wavelink PIL langchain langchain_openai chromadb sentence_transformers apscheduler ddgs) do (
      "%PY%" -c "import %%m" >nul 2>&1
      if errorlevel 1 set "MISSING_MODULES=!MISSING_MODULES! %%m"
    )
    if defined MISSING_MODULES (
      echo [ERROR] Still missing modules after install:!MISSING_MODULES!
      pause
      goto end
    ) else (
      echo [OK] All Python dependencies are installed.
    )
  ) else (
    echo [ERROR] Cannot continue with missing dependencies.
    pause
    goto end
  )
) else (
  echo [OK] All Python dependencies are installed.
)
echo.

echo [3/3] Running healthcheck...
"%PY%" scripts\healthcheck.py --mode console --skip-http
if errorlevel 1 (
  echo [WARN] Healthcheck reported issues.
  set /p CONT=Continue anyway? [y/N]: 
  if /I not "!CONT!"=="y" goto end
)

:menu
echo.
echo ==========================================
echo    Neyra 2.0 Launcher
echo ==========================================
echo 1) Console (model) - terminal chat only, no HTTP
echo 2) Core - API + dashboard + resident plugins
echo 3) Re-run dependency checks
echo 4) Exit
echo.
set /p CHOICE=Select mode [1-4]: 

if "%CHOICE%"=="1" goto run_console
if "%CHOICE%"=="2" goto run_core
if "%CHOICE%"=="3" goto print_header
if "%CHOICE%"=="4" goto end

echo Invalid choice.
pause
goto menu

:run_console
"%PY%" main.py --mode console
echo.
echo Console mode exited.
pause
goto menu

:run_core
"%PY%" scripts\healthcheck.py --mode core --skip-http
if errorlevel 1 (
  echo [WARN] Core healthcheck failed.
  set /p CONT_CORE=Continue anyway? [y/N]: 
  if /I not "!CONT_CORE!"=="y" goto menu
)
if exist "interfaces\discord_music\lavalink\Lavalink.jar" (
  tasklist /FI "WINDOWTITLE eq Lavalink" | find /I "java.exe" >nul 2>&1
  if errorlevel 1 (
    echo Starting Lavalink in background...
    start "Lavalink" /MIN cmd /c "cd /d interfaces\discord_music\lavalink && java -Dfile.encoding=UTF-8 -jar Lavalink.jar"
    timeout /t 2 /nobreak >nul
  ) else (
    echo Lavalink window already running.
  )
) else (
  echo [WARN] Lavalink.jar not found at interfaces\discord_music\lavalink\Lavalink.jar
)
"%PY%" main.py --mode core
echo.
echo Core mode exited.
pause
goto menu

:end
endlocal
