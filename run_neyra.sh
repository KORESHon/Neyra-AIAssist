#!/usr/bin/env bash
# Neyra launcher for Linux/macOS (Git Bash on Windows OK). Usage: ./run_neyra.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
elif [[ -f "${ROOT}/.venv/Scripts/python.exe" ]]; then
  PY="${ROOT}/.venv/Scripts/python.exe"
else
  PY="python3"
fi

neyra_port() {
  "${PY}" -c "
from pathlib import Path
import yaml
p = Path('config.yaml')
if not p.is_file():
    print(8787)
    raise SystemExit(0)
d = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
api = d.get('internal_api') or {}
print(int(api.get('port') or 8787))
" 2>/dev/null || echo "8787"
}

neyra_backend() {
  "${PY}" -c "
from pathlib import Path
import yaml
p = Path('config.yaml')
if not p.is_file():
    print('(no config.yaml)')
    raise SystemExit(0)
d = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
print(str(d.get('BACKEND', 'openrouter')))
" 2>/dev/null || echo "?"
}

neyra_status() {
  echo "=== Neyra — статус ==="
  echo "Каталог: ${ROOT}"
  echo "Python:  ${PY}"
  echo "BACKEND: $(neyra_backend)"
  local port
  port="$(neyra_port)"
  echo "Порт API (из config.yaml): ${port}"
  echo "--- процессы main.py этого репозитория ---"
  if command -v pgrep >/dev/null 2>&1; then
    if pgrep -f "${ROOT}/main[.]py" >/dev/null 2>&1; then
      pgrep -af "${ROOT}/main[.]py" 2>/dev/null || true
    else
      echo "(нет совпадений по ${ROOT}/main.py)"
    fi
  else
    echo "(установите procps для pgrep или смотрите ps вручную)"
  fi
  echo "--- прослушивание порта ${port} ---"
  if command -v ss >/dev/null 2>&1; then
    ss -tlnp 2>/dev/null | grep -E ":${port}\\s" || echo "(ничего не слушает ${port} или нужны права)"
  elif command -v lsof >/dev/null 2>&1; then
    lsof -i ":${port}" -sTCP:LISTEN 2>/dev/null || echo "(нет LISTEN на ${port})"
  else
    echo "(нет ss/lsof — пропуск проверки порта)"
  fi
  echo "========================"
}

neyra_stop() {
  echo "Остановка процессов Neyra для этого клона (совпадение: ${ROOT}/main.py)..."
  if ! command -v pgrep >/dev/null 2>&1; then
    echo "Нужен pgrep (пакет procps). Остановите процессы вручную."
    return 1
  fi
  local pids
  pids="$(pgrep -f "${ROOT}/main[.]py" 2>/dev/null || true)"
  if [[ -z "${pids}" ]]; then
    echo "Нет запущенных процессов по шаблону."
    return 0
  fi
  echo "PID: ${pids}"
  read -r -p "Отправить SIGTERM этим PID? [y/N] " a
  if [[ ! "${a}" =~ ^[yY]$ ]]; then
    echo "Отменено."
    return 0
  fi
  kill ${pids} 2>/dev/null || true
  sleep 1
  pids="$(pgrep -f "${ROOT}/main[.]py" 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    read -r -p "Процессы живы. SIGKILL? [y/N] " b
    if [[ "${b}" =~ ^[yY]$ ]]; then
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
  echo "Готово."
}

neyra_updates() {
  echo "=== Проверка обновлений (git) ==="
  if ! command -v git >/dev/null 2>&1; then
    echo "git не найден."
    return 1
  fi
  git -C "${ROOT}" fetch origin 2>/dev/null || { echo "git fetch не удался (сеть / remote)."; return 1; }
  git -C "${ROOT}" status -sb
  echo "--- коммиты на origin, которых нет локально (если есть upstream) ---"
  if git -C "${ROOT}" rev-parse --verify @{u} >/dev/null 2>&1; then
    git -C "${ROOT}" log --oneline HEAD..@{u} 2>/dev/null | head -15 || true
  else
    echo "(upstream не настроен; смотрите git remote -v и git branch -vv)"
  fi
  echo "Обновить: git pull (из активной ветки)."
  echo "================================"
}

run_preflight_console() {
  "${PY}" "${ROOT}/scripts/healthcheck.py" --mode console --skip-http || return 1
}

run_preflight_core() {
  "${PY}" "${ROOT}/scripts/healthcheck.py" --mode core --skip-http || return 1
}

while true; do
  echo ""
  echo "========== Neyra =========="
  echo "1) Ядро (core) — API, дашборд, плагины"
  echo "2) Консоль (console) — только чат в терминале"
  echo "3) Статус (процессы, порт)"
  echo "4) Остановить Neyra (этот репозиторий)"
  echo "5) Проверить обновления (git fetch + статус)"
  echo "6) Выход"
  read -r -p "Выбор [1-6]: " choice
  case "${choice}" in
    1)
      if ! run_preflight_core; then
        read -r -p "Preflight не прошёл. Продолжить? [y/N] " c
        [[ "${c}" =~ ^[yY]$ ]] || continue
      fi
      "${PY}" "${ROOT}/main.py" --mode core
      ;;
    2)
      if ! run_preflight_console; then
        read -r -p "Preflight не прошёл. Продолжить? [y/N] " c
        [[ "${c}" =~ ^[yY]$ ]] || continue
      fi
      "${PY}" "${ROOT}/main.py" --mode console
      ;;
    3) neyra_status ;;
    4) neyra_stop ;;
    5) neyra_updates ;;
    6) exit 0 ;;
    *) echo "Неверный выбор" ;;
  esac
done
