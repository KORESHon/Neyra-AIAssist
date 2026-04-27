#!/usr/bin/env bash
# Neyra launcher for Linux/macOS.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PY="${ROOT}/.venv/bin/python"
elif [[ -x "${ROOT}/.venv/Scripts/python.exe" ]]; then
  PY="${ROOT}/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
elif command -v python >/dev/null 2>&1; then
  PY="python"
else
  echo "[ERROR] Python is not installed or not in PATH."
  echo "Install Python 3.10+ and rerun this launcher."
  exit 1
fi

PIP="${PY} -m pip"

start_lavalink_background() {
  local jar="${ROOT}/interfaces/discord_music/lavalink/Lavalink.jar"
  local logf="${ROOT}/interfaces/discord_music/lavalink/lavalink.log"
  if [[ ! -f "${jar}" ]]; then
    echo "[WARN] Lavalink.jar not found: ${jar}"
    return 0
  fi
  if command -v pgrep >/dev/null 2>&1 && pgrep -f "Lavalink.jar" >/dev/null 2>&1; then
    echo "Lavalink already running."
    return 0
  fi
  echo "Starting Lavalink in background..."
  (
    cd "${ROOT}/interfaces/discord_music/lavalink" || exit 1
    nohup java -Dfile.encoding=UTF-8 -jar Lavalink.jar > "${logf}" 2>&1 &
  )
  sleep 2
}

print_header() {
  echo
  echo "=========================================="
  echo "  Neyra 2.0 Launcher (Unix)"
  echo "=========================================="
  echo "Python: $("${PY}" -c 'import sys; print(sys.executable)')"
  if [[ -x "${ROOT}/.venv/bin/python" || -x "${ROOT}/.venv/Scripts/python.exe" ]]; then
    echo "Virtualenv: detected (.venv)"
  else
    echo "Virtualenv: not found (using global interpreter)"
  fi
  echo
}

check_system_deps() {
  echo "[1/3] Checking system dependencies..."
  local missing=()
  command -v git >/dev/null 2>&1 || missing+=("git")
  command -v ffmpeg >/dev/null 2>&1 || missing+=("ffmpeg")
  if ((${#missing[@]} > 0)); then
    echo "[WARN] Missing system tools: ${missing[*]}"
    echo "       git is recommended for updates, ffmpeg is recommended for media workflows."
  else
    echo "[OK] System dependencies are installed."
  fi
  echo
}

check_python_deps() {
  echo "[2/3] Checking Python dependencies in the active interpreter..."
  local missing=()
  local modules=(
    yaml dotenv requests fastapi uvicorn discord wavelink PIL
    langchain langchain_openai chromadb sentence_transformers apscheduler ddgs
  )
  local m
  for m in "${modules[@]}"; do
    if ! "${PY}" -c "import ${m}" >/dev/null 2>&1; then
      missing+=("${m}")
    fi
  done

  if ((${#missing[@]} > 0)); then
    echo "[WARN] Missing Python modules: ${missing[*]}"
    read -r -p "Install missing dependencies from requirements.txt now? [y/N]: " yn
    if [[ ! "${yn}" =~ ^[yY]$ ]]; then
      echo "[ERROR] Cannot continue with missing dependencies."
      return 1
    fi
    if ! ${PIP} install -r requirements.txt; then
      echo "[ERROR] Dependency installation failed."
      return 1
    fi
    missing=()
    for m in "${modules[@]}"; do
      if ! "${PY}" -c "import ${m}" >/dev/null 2>&1; then
        missing+=("${m}")
      fi
    done
    if ((${#missing[@]} > 0)); then
      echo "[ERROR] Still missing modules after install: ${missing[*]}"
      return 1
    fi
    echo "[OK] All Python dependencies are installed."
  else
    echo "[OK] All Python dependencies are installed."
  fi
  echo
}

run_initial_healthcheck() {
  echo "[3/3] Running healthcheck..."
  if ! "${PY}" scripts/healthcheck.py --mode console --skip-http; then
    read -r -p "Healthcheck reported issues. Continue anyway? [y/N]: " yn
    [[ "${yn}" =~ ^[yY]$ ]] || return 1
  fi
  return 0
}

run_preflight() {
  print_header
  check_system_deps
  check_python_deps || return 1
  run_initial_healthcheck || return 1
  return 0
}

run_preflight || exit 1

while true; do
  echo
  echo "=========================================="
  echo "   Neyra 2.0 Launcher"
  echo "=========================================="
  echo "1) Console (model) - terminal chat only, no HTTP"
  echo "2) Core - API + dashboard + resident plugins"
  echo "3) Re-run dependency checks"
  echo "4) Exit"
  read -r -p "Select mode [1-4]: " choice

  case "${choice}" in
    1)
      "${PY}" main.py --mode console || true
      read -r -p "Console mode exited. Press Enter to continue..."
      ;;
    2)
      if ! "${PY}" scripts/healthcheck.py --mode core --skip-http; then
        read -r -p "Core healthcheck failed. Continue anyway? [y/N]: " yn
        [[ "${yn}" =~ ^[yY]$ ]] || continue
      fi
      start_lavalink_background
      "${PY}" main.py --mode core || true
      read -r -p "Core mode exited. Press Enter to continue..."
      ;;
    3)
      run_preflight || {
        echo "[ERROR] Preflight checks failed."
        read -r -p "Press Enter to continue..."
      }
      ;;
    4)
      exit 0
      ;;
    *)
      echo "Invalid choice."
      ;;
  esac
done
