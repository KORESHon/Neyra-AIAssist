@echo off
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

:preflight
echo Running preflight checks...
if not exist ".env" (
  echo [WARN] .env not found. Create it from .env.example first.
)
"%PY%" scripts\healthcheck.py --mode console --skip-http
if errorlevel 1 (
  echo [WARN] Healthcheck reported issues.
  set /p CONT=Continue anyway? [y/N]:
  if /I not "%CONT%"=="y" goto end
)

:menu
cls
echo ==========================================
echo   Neyra 2.0 Launcher
echo ==========================================
echo 1^) Console (model) — только чат в терминале, без HTTP
echo 2^) Core — API + dashboard + resident-плагины (Discord и др. из config)
echo 3^) Exit
echo.
set /p CHOICE=Select mode [1-3]: 

if "%CHOICE%"=="1" goto run_console
if "%CHOICE%"=="2" goto run_core
if "%CHOICE%"=="3" goto end
echo Invalid choice.
pause
goto menu

:run_console
"%PY%" main.py --mode console
pause
goto menu

:run_core
"%PY%" scripts\healthcheck.py --mode core --skip-http
if errorlevel 1 (
  echo [WARN] Core preflight failed.
  pause
  goto menu
)
"%PY%" main.py --mode core
pause
goto menu

:end
endlocal
