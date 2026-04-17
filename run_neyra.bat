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
"%PY%" scripts\healthcheck.py --mode model --skip-http
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
echo 1^) Model mode (console)
echo 2^) Discord text bot
echo 3^) Local voice agent (stub)
echo 4^) Laptop screen agent (stub)
echo 5^) Exit
echo.
set /p CHOICE=Select mode [1-5]: 

if "%CHOICE%"=="1" goto run_model
if "%CHOICE%"=="2" goto run_discord
if "%CHOICE%"=="3" goto run_voice
if "%CHOICE%"=="4" goto run_screen
if "%CHOICE%"=="5" goto end
echo Invalid choice.
pause
goto menu

:run_model
"%PY%" main.py --mode model
pause
goto menu

:run_discord
"%PY%" scripts\healthcheck.py --mode discord --skip-http
if errorlevel 1 (
  echo [WARN] Discord preflight failed.
  pause
  goto menu
)
"%PY%" main.py --mode discord
pause
goto menu

:run_voice
"%PY%" main.py --mode local_voice
pause
goto menu

:run_screen
"%PY%" main.py --mode screen
pause
goto menu

:end
endlocal
