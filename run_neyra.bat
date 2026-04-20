@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "LANG_MODE=RU"

:lang_menu
cls
echo ==========================================
echo   Neyra Launcher
echo ==========================================
echo 1^) Русский
echo 2^) English
echo.
set /p LANG_CHOICE=Select language [1-2]:
if "%LANG_CHOICE%"=="1" set "LANG_MODE=RU" & goto preflight
if "%LANG_CHOICE%"=="2" set "LANG_MODE=EN" & goto preflight
goto lang_menu

:preflight
if /I "%LANG_MODE%"=="RU" (
  echo Запуск предварительных проверок...
) else (
  echo Running preflight checks...
)
if not exist ".env" (
  if /I "%LANG_MODE%"=="RU" (
    echo [WARN] Файл .env не найден. Сначала создайте его из .env.example.
  ) else (
    echo [WARN] .env not found. Create it from .env.example first.
  )
)
"%PY%" scripts\healthcheck.py --mode console --skip-http
if errorlevel 1 (
  if /I "%LANG_MODE%"=="RU" (
    echo [WARN] Healthcheck нашел проблемы.
    set /p CONT=Продолжить несмотря на ошибки? [y/N]:
  ) else (
    echo [WARN] Healthcheck reported issues.
    set /p CONT=Continue anyway? [y/N]:
  )
  if /I not "%CONT%"=="y" goto end
)

:menu
cls
echo ==========================================
echo   Neyra 2.0 Launcher
echo ==========================================
if /I "%LANG_MODE%"=="RU" (
  echo 1^) Console ^(model^) — только чат в терминале, без HTTP
  echo 2^) Core — API + dashboard + resident-плагины ^(Discord и др. из config^)
  echo 3^) Выход
) else (
  echo 1^) Console ^(model^) - terminal chat only, no HTTP
  echo 2^) Core - API + dashboard + resident plugins ^(Discord etc. from config^)
  echo 3^) Exit
)
echo.
set /p CHOICE=Select mode [1-3]: 

if "%CHOICE%"=="1" goto run_console
if "%CHOICE%"=="2" goto run_core
if "%CHOICE%"=="3" goto end
if /I "%LANG_MODE%"=="RU" (
  echo Некорректный выбор.
) else (
  echo Invalid choice.
)
pause
goto menu

:run_console
"%PY%" main.py --mode console
pause
goto menu

:run_core
"%PY%" scripts\healthcheck.py --mode core --skip-http
if errorlevel 1 (
  if /I "%LANG_MODE%"=="RU" (
    echo [WARN] Проверка Core перед запуском не пройдена.
  ) else (
    echo [WARN] Core preflight failed.
  )
  pause
  goto menu
)
"%PY%" main.py --mode core
pause
goto menu

:end
endlocal
