#!/usr/bin/env python3
"""
Cyber-Core — Проект «Нейра»
Главная точка входа.

Использование:
  python main.py                  # Model-режим (консоль)
  python main.py --mode model     # то же, что console
  python main.py --mode discord   # Discord text-бот
  python main.py --mode local_voice  # Заглушка local voice интерфейса
  python main.py --mode screen       # Заглушка screen интерфейса

Команды в консольном режиме:
  /reset     — сбросить краткосрочную память
  /stats     — статистика агента
  /journal   — последние записи дневника
  /reflect   — запустить рефлексию вручную
  /search <запрос> — поиск по памяти (RAG)
  /time — дата и время
  /sys <uptime|disk|memory|cpu|python> — железо
  /web <запрос> — DuckDuckGo
  /friend <имя|id> — досье из FriendsDB
  exit / quit — выход
"""

# ─── КРИТИЧНО: прячем GPU от Python/torch ДО любых импортов ──────────────────
# sentence-transformers в этом процессе не должны занимать VRAM там,
# где мешают другим демонам (исторически — Ollama).
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
# Секреты из .env (см. .env.example) — до CUDA и до загрузки config.yaml
from core.secrets_loader import apply_env_secrets, load_dotenv_file

load_dotenv_file(_PROJECT_ROOT)
os.environ["CUDA_VISIBLE_DEVICES"] = ""
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import argparse
import logging
import subprocess

import yaml

# ─── Загрузка конфига ─────────────────────────────────────────────────────────

CONFIG_PATH = _PROJECT_ROOT / "config.yaml"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[FATAL] Конфиг не найден: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        data = {}
    apply_env_secrets(data)
    return data


config = load_config()
BACKEND = str(config.get("BACKEND", "openrouter")).lower()

# Hugging Face: токен не обязателен, если модели уже в кэше; даёт выше лимиты на скачивание
_mem = config.get("memory") or {}
_hf = (_mem.get("hf_token") or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN") or "").strip()
if _hf:
    os.environ["HF_TOKEN"] = _hf
# На Windows без Developer Mode warning про symlink-кэш HF очень шумный и бесполезный.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# ─── Логирование ──────────────────────────────────────────────────────────────

log_dir = Path("./logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config["logging"]["level"], logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config["logging"]["system_log"], encoding="utf-8"),
    ],
)
logger = logging.getLogger("cyber-core")

# Подавляем шумные httpx/httpcore логи в консоли — они идут только в файл
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)
logging.getLogger("torch").setLevel(logging.WARNING)
logging.getLogger("torch._subclasses").setLevel(logging.WARNING)

# ─── Баннер ───────────────────────────────────────────────────────────────────

BANNER = f"""
╔════════════════════════════════════════════════════╗
║        CYBER-CORE  //  Ассистент «Нейра»          ║
║  Backend: {BACKEND.upper():<9}  Model: {'loading...':<16}║
╚════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
Команды:
  /reset             — сбросить краткосрочную память (новый диалог)
  /stats             — статистика агента
  /journal           — записи дневника за 7 дней
  /diary             — личный дневник Нейры (последние записи)
  /diary_add <текст> — вручную добавить заметку в личный дневник
  /reflect           — запустить ночную рефлексию вручную
  /search <текст>    — поиск по долгосрочной памяти (RAG)
  /time              — дата и время
  /sys <команда>    — uptime | disk | memory | cpu | python
  /web <запрос>      — поиск в интернете (ddgs)
  /friend <имя|id>   — досье FriendsDB
  /launch <discord|local_voice|screen> — запустить интерфейс-плагин в фоне
  /running           — показать запущенные интерфейсы
  exit / quit        — выход

  В Discord: текстовые slash-команды (reset, stats, search, web, friend, ...)
"""

_SPAWNED_INTERFACES: dict[str, subprocess.Popen] = {}


def launch_interface_mode(mode: str) -> tuple[bool, str]:
    mode = (mode or "").strip().lower()
    if mode not in {"discord", "local_voice", "screen"}:
        return False, "Неизвестный режим. Доступно: discord | local_voice | screen"
    proc = _SPAWNED_INTERFACES.get(mode)
    if proc and proc.poll() is None:
        return False, f"Интерфейс {mode} уже запущен (pid={proc.pid})"
    py = Path(".venv/Scripts/python.exe")
    python_exe = str(py if py.exists() else Path(sys.executable))
    p = subprocess.Popen([python_exe, str(_PROJECT_ROOT / "main.py"), "--mode", mode])
    _SPAWNED_INTERFACES[mode] = p
    return True, f"Запущен интерфейс {mode} (pid={p.pid})"


# ─── Консольный режим ─────────────────────────────────────────────────────────

async def run_console():
    """Интерактивный консольный режим с реальным агентом."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    console = Console()

    console.print(BANNER, style="bold cyan")
    console.print("Проверяю связь с LLM backend...", style="yellow")

    # Проверяем доступность OpenAI-compatible endpoint (/v1/models)
    import httpx, time as _time

    from core.llm_profile import resolve_openai_compatible_connection

    conn = resolve_openai_compatible_connection(config)
    backend_name = conn.provider.upper()
    check_url = conn.base_url.rstrip("/")
    check_endpoint = f"{check_url}/models"
    start_tip = f"Проверь доступ к {check_url} и API-ключ для провайдера «{conn.provider}» (.env / config)."

    console.print(f"Проверяю связь с LLM ({backend_name}, {check_url})...", style="yellow")
    for attempt in range(5):
        try:
            headers = {}
            ak = (conn.api_key or "").strip()
            if ak and ak != "ollama":
                headers["Authorization"] = f"Bearer {ak}"
            r = httpx.get(check_endpoint, timeout=10, headers=headers)
            console.print(f"  {backend_name} ✓", style="green")
            models = [m.get("id", "") for m in r.json().get("data", []) if isinstance(m, dict)]
            if models:
                console.print(f"  Доступно: {', '.join(models[:4])}", style="dim")
            break
        except Exception as e:
            if attempt < 4:
                console.print(f"  [yellow]Попытка {attempt+1}/5: {e} — жду...[/yellow]")
                _time.sleep(3)
            else:
                console.print(f"[red]{backend_name} недоступен после 5 попыток: {e}[/red]")
                console.print(f"[yellow]{start_tip}[/yellow]")
                sys.exit(1)

    console.print("Инициализирую агента...", style="yellow")

    # Инициализация агента
    try:
        from core.agent import NeyraAgent
        agent = NeyraAgent(config)
    except Exception as e:
        console.print(f"[red]ОШИБКА инициализации агента: {e}[/red]")
        console.print("[yellow]Проверь OPENROUTER_API_KEY в .env и доступ к интернету.[/yellow]")
        logger.exception(e)
        sys.exit(1)

    # Инициализация рефлексии
    from core.reflection import ReflectionEngine
    reflection = ReflectionEngine(config, agent)
    reflection.start_scheduler()

    # Обновляем баннер с реальной моделью
    stats = agent.get_stats()
    console.clear()
    banner_updated = (
        f"\n╔════════════════════════════════════════════════════╗\n"
        f"║        CYBER-CORE  //  Ассистент «Нейра»          ║\n"
        f"║  LLM: {str(stats.get('llm_provider', BACKEND)).upper():<12}  Model: {stats['model'][:16]:<16}║\n"
        f"╚════════════════════════════════════════════════════╝\n"
    )
    console.print(banner_updated, style="bold cyan")
    console.print(
        f"  RAM памяти: {stats['short_memory_size']} сообщений | "
        f"RAG: {stats['long_memory_records']} записей | "
        f"Друзья: {stats['friends_db_records']}",
        style="dim"
    )
    console.print(HELP_TEXT, style="dim")
    console.print("─" * 52 + "\n", style="dim")

    while True:
        try:
            user_input = input("Ты: ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[bold cyan]Нейра: Чё? Ладно, ухожу.[/bold cyan]")
            break

        if not user_input:
            continue

        # ── Команды ──
        if user_input.lower() in ("exit", "quit", "выход", "q"):
            console.print("[bold cyan]Нейра: Давай, пока.[/bold cyan]")
            break

        if user_input == "/reset":
            agent.reset_context()
            console.print("[dim]── Память сброшена. Новый диалог. ──[/dim]")
            continue

        if user_input == "/stats":
            s = agent.get_stats()
            console.print(Panel(
                f"Режим: [bold]{s['mode']}[/bold]\n"
                f"Модель: [bold]{s['model']}[/bold]\n"
                f"История: {s['short_memory_size']} сообщений\n"
                f"RAG записей: {s['long_memory_records']}\n"
                f"Друзей в базе: {s['friends_db_records']}\n"
                f"Инструментов: {s['tools_count']}",
                title="Статистика",
                border_style="cyan"
            ))
            continue

        if user_input == "/journal":
            journal = reflection.get_recent_journal(7)
            console.print(Panel(journal, title="Дневник (последние 7 дней)", border_style="magenta"))
            continue

        if user_input == "/diary":
            diary = agent.get_recent_diary(12)
            console.print(Panel(diary, title="Личный дневник Нейры", border_style="magenta"))
            continue

        if user_input.startswith("/diary_add "):
            note = user_input[len("/diary_add ") :].strip()
            if not note:
                console.print("[red]Добавь текст заметки после /diary_add[/red]")
                continue
            ok = agent.add_diary_entry(note, source="manual_console", meta={"author": "ebluffy"})
            console.print("[green]Записала в личный дневник.[/green]" if ok else "[red]Не смогла записать.[/red]")
            continue

        if user_input == "/reflect":
            console.print("[dim]Запускаю рефлексию...[/dim]")
            summary = await reflection.reflect(force=True)
            if summary:
                console.print(Panel(summary, title="Рефлексия", border_style="magenta"))
            else:
                console.print("[dim]Нечего рефлексировать (нет логов за вчера).[/dim]")
            continue

        if user_input.startswith("/search "):
            query = user_input[8:].strip()
            if query:
                results = agent.long_memory.search(query)
                if results:
                    text = "\n\n".join(r[:300] for r in results)
                    console.print(Panel(text, title=f"Поиск: '{query}'", border_style="blue"))
                else:
                    console.print("[dim]Ничего не нашла в памяти.[/dim]")
            continue

        if user_input == "/time":
            out = agent.tools["get_current_time"].invoke({})
            console.print(Panel(str(out), title="Время", border_style="green"))
            continue

        if user_input.startswith("/sys "):
            cmd = user_input[5:].strip().split()[0].lower()
            allowed = ("uptime", "disk", "memory", "cpu", "python")
            if cmd not in allowed:
                console.print(f"[red]Нужно: {' | '.join(allowed)}[/red]")
                continue
            raw = agent.tools["check_system"].invoke({"command": cmd})
            console.print(Panel(str(raw), title=f"Система: {cmd}", border_style="green"))
            continue

        if user_input.startswith("/web "):
            q = user_input[5:].strip()
            if q:
                raw = agent.tools["web_search"].invoke({"query": q[:500]})
                console.print(Panel(str(raw), title="Web", border_style="blue"))
            continue

        if user_input.startswith("/friend "):
            q = user_input[8:].strip()
            if q:
                raw = agent.tools["get_friend_info"].invoke({"name_or_id": q[:120]})
                console.print(Panel(str(raw), title=f"Досье: {q}", border_style="cyan"))
            continue

        if user_input.startswith("/launch "):
            mode = user_input[len("/launch ") :].strip()
            ok, msg = launch_interface_mode(mode)
            console.print(f"[green]{msg}[/green]" if ok else f"[yellow]{msg}[/yellow]")
            continue

        if user_input == "/running":
            alive = []
            for m, p in _SPAWNED_INTERFACES.items():
                if p.poll() is None:
                    alive.append(f"{m} (pid={p.pid})")
            console.print(Panel("\n".join(alive) if alive else "Нет активных интерфейсов.", title="Интерфейсы"))
            continue

        # ── Отправляем в агент (стриминг) ──
        sounds = []
        error_occurred = False

        # Печатаем "Нейра: " и сразу начинаем вывод токенов
        print("\nНейра: ", end="", flush=True)

        try:
            async for chunk in agent.chat_stream(user_input, username="ebluffy"):
                if chunk["type"] == "token":
                    # Просто печатаем всё как есть — быстро и надёжно
                    print(chunk["text"], end="", flush=True)

                elif chunk["type"] == "done":
                    sounds = chunk.get("sounds", [])
                    # DEBUG: показываем think-блоки если включено
                    if config["logging"]["level"] == "DEBUG" and chunk.get("thoughts"):
                        console.print(
                            f"\n[dim][think: {chunk['thoughts'][:200]}][/dim]"
                        )

                elif chunk["type"] == "error":
                    err = chunk["text"]
                    if err:  # Пустые ошибки игнорируем
                        console.print(f"\n[red]Ошибка: {err}[/red]")
                    error_occurred = True
                    break

            print()  # Перенос строки после ответа

        except Exception as e:
            print()
            console.print(f"[red]Критическая ошибка: {e}[/red]")
            logger.exception(e)
            continue

        # Звуки пока отключены — позже добавим саундпад
        # TODO: воспроизводить sounds через soundpad когда будет готов


# ─── Discord режим ────────────────────────────────────────────────────────────

async def run_discord():
    """Запускает Discord text-бот."""
    from interfaces.discord_text_bot import run_discord_text_bot
    from core.agent import NeyraAgent
    from rich.console import Console

    console = Console()
    console.print(BANNER, style="bold cyan")
    console.print("Режим: [bold magenta]Discord[/bold magenta]")

    agent = NeyraAgent(config)

    # run_discord_text_bot — блокирующий, запускаем в executor чтобы не блокировать loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_discord_text_bot, agent, config)


async def run_local_voice():
    """Запускает local voice интерфейс (заглушка)."""
    from interfaces.local_voice_agent import run_local_voice_agent

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_local_voice_agent, config)


async def run_screen():
    """Запускает screen интерфейс (заглушка)."""
    from interfaces.laptop_screen_agent import run_laptop_screen_agent

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_laptop_screen_agent, config)


# ─── Точка входа ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Cyber-Core — Ассистент «Нейра»",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["model", "console", "discord", "local_voice", "screen"],
        default="model",
        help="Режим запуска (по умолчанию: model)",
    )
    args = parser.parse_args()

    # Создаём нужные директории
    for d in ["./logs", "./memory", "./sounds", "./memory/chroma_db", "./memory/friends_db"]:
        Path(d).mkdir(parents=True, exist_ok=True)

    logger.info(f"Старт | mode={args.mode} | backend={BACKEND}")

    mode_map = {
        "model": run_console,
        "console": run_console,
        "discord": run_discord,
        "local_voice": run_local_voice,
        "screen": run_screen,
    }

    try:
        asyncio.run(mode_map[args.mode]())
    except KeyboardInterrupt:
        logger.info("Получен Ctrl+C. Завершение...")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
