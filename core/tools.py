"""
core/tools.py — Инструменты (Tools) для агента Нейры
──────────────────────────────────────────────────────
LLM может вызывать эти функции сама через Function Calling.

Текущие инструменты:
  • TimeContextTool   — текущее время и дата
  • SystemMonitorTool — состояние системы (безопасные команды)
  • WebSearchTool     — поиск через DuckDuckGo
  • MemorySearchTool  — поиск по ChromaDB
  • UpdateFriendFact  — записать новый факт о человеке
  • GetFriendInfo     — получить досье на человека
"""

from __future__ import annotations

import logging
import platform
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING

from langchain_core.tools import tool

if TYPE_CHECKING:
    from core.memory import FriendsDB, LongTermMemory

logger = logging.getLogger("neyra.tools")

# Будут заинжектированы при инициализации агента
_long_memory: "LongTermMemory | None" = None
_friends_db: "FriendsDB | None" = None
_assistant_cfg: dict | None = None


def init_tools(long_memory, friends_db, assistant_cfg: dict | None = None) -> None:
    """Инициализирует ссылки на модули памяти."""
    global _long_memory, _friends_db, _assistant_cfg
    _long_memory = long_memory
    _friends_db = friends_db
    _assistant_cfg = assistant_cfg or {}


# ─── TimeContextTool ─────────────────────────────────────────────────────────

@tool
def get_current_time() -> str:
    """
    Возвращает текущее время, дату, день недели и время суток.
    Используй когда нужно знать который сейчас час или день.
    """
    now = datetime.now()
    days_ru = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    months_ru = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря"
    ]

    hour = now.hour
    if 5 <= hour < 12:
        time_of_day = "утро"
    elif 12 <= hour < 17:
        time_of_day = "день"
    elif 17 <= hour < 22:
        time_of_day = "вечер"
    else:
        time_of_day = "ночь"

    return (
        f"{now.strftime('%H:%M')} — {time_of_day}, "
        f"{days_ru[now.weekday()]}, "
        f"{now.day} {months_ru[now.month]} {now.year} года"
    )


# ─── SystemMonitorTool ───────────────────────────────────────────────────────

# Whitelist безопасных команд (только чтение)
_SAFE_COMMANDS = {
    "uptime": ["uptime"],
    "disk": ["df", "-h"],
    "memory": ["free", "-h"],
    "cpu": ["top", "-bn1"],
    "python": ["python", "--version"],
}

# Для Windows — альтернативные команды
_SAFE_COMMANDS_WIN = {
    "uptime": ["powershell", "-Command", "(Get-Date) - (gcim Win32_OperatingSystem).LastBootUpTime"],
    "disk": ["powershell", "-Command", "Get-PSDrive -PSProvider FileSystem | Select-Object Name,Used,Free"],
    "memory": ["powershell", "-Command", "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory"],
    "cpu": ["powershell", "-Command", "Get-CimInstance Win32_Processor | Select-Object Name,LoadPercentage"],
    "python": ["python", "--version"],
}


@tool
def check_system(command: str) -> str:
    """
    Проверяет состояние системы.
    Доступные команды: uptime, disk, memory, cpu, python.
    Используй чтобы узнать как себя чувствует железо.
    """
    is_windows = platform.system() == "Windows"
    cmd_map = _SAFE_COMMANDS_WIN if is_windows else _SAFE_COMMANDS

    if command not in cmd_map:
        available = ", ".join(cmd_map.keys())
        return f"Неизвестная команда '{command}'. Доступны: {available}"

    try:
        result = subprocess.run(
            cmd_map[command],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return output if output else "Нет данных"
    except subprocess.TimeoutExpired:
        return "Команда завишла (таймаут 10 сек)"
    except Exception as e:
        return f"Ошибка выполнения команды: {e}"


# ─── WebSearchTool ───────────────────────────────────────────────────────────

@tool
def web_search(query: str) -> str:
    """
    Ищет информацию в интернете через DuckDuckGo.
    Используй когда нужна актуальная инфа: новости, документация, ответы на вопросы.
    query — поисковый запрос на русском или английском.
    """
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3, region="ru-ru"))

        if not results:
            return "Ничего не нашла. Попробуй переформулировать."

        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "Без названия")
            body = r.get("body", "")[:300]
            lines.append(f"[{i}] {title}\n{body}")

        return "\n\n".join(lines)

    except ImportError:
        return "Пакет ddgs не установлен. Запусти: pip install ddgs"
    except Exception as e:
        logger.error(f"WebSearch ошибка: {e}")
        return f"Поиск упал с ошибкой: {e}"


# ─── MemorySearchTool ────────────────────────────────────────────────────────

@tool
def search_memory(query: str) -> str:
    """
    Ищет в долгосрочной памяти (прошлые диалоги) похожие разговоры.
    Используй когда нужно вспомнить что-то из прошлых бесед.
    query — то, что нужно вспомнить.
    """
    if _long_memory is None:
        return "Долгосрочная память не инициализирована."

    results = _long_memory.search(query)
    if not results:
        return "Ничего не нашла в памяти. Либо мы это ещё не обсуждали, либо память пустая."

    lines = ["Нашла в памяти:"]
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r[:400]}")

    return "\n\n".join(lines)


# ─── UpdateFriendFact ────────────────────────────────────────────────────────

@tool
def update_friend_fact(person_id: str, fact: str) -> str:
    """
    Записывает новый факт о человеке в базу досье (FriendsDB).
    Используй когда узнала что-то новое о друге или знакомом.
    person_id — ID человека (maxim, kutyr, timofey, andrey_griniks, bogdan, foxy, erik).
    fact — что именно узнала (кратко, своими словами).
    """
    if _friends_db is None:
        return "FriendsDB не инициализирована."

    success = _friends_db.update_fact(person_id, fact)
    if success:
        return f"Записала. Теперь знаю про {person_id}: {fact}"
    else:
        # Попробуем найти по нечёткому совпадению
        person = _friends_db.find(person_id)
        if person:
            _friends_db.update_fact(person["id"], fact)
            return f"Нашла по имени и записала про {person['names'][0]}: {fact}"
        return f"Не нашла человека '{person_id}' в базе. Проверь ID."


# ─── GetFriendInfo ───────────────────────────────────────────────────────────

@tool
def get_friend_info(name_or_id: str) -> str:
    """
    Получает досье на человека из базы.
    Используй когда нужно вспомнить кто это такой и что о нём знаешь.
    name_or_id — имя, ник или ID человека.
    """
    if _friends_db is None:
        return "FriendsDB не инициализирована."

    person = _friends_db.find(name_or_id)
    if not person:
        return f"Никого с именем/ником '{name_or_id}' в базе нет. Может это новый человек?"

    summary = _friends_db.get_summary(person["id"])
    return summary or f"Досье на {name_or_id} есть, но оно пустое."


@tool
def get_character_profile() -> str:
    """
    Возвращает краткий профиль характера Нейры и базовые правила стиля.
    Используй, если нужно свериться с тоном, манерой речи и ограничениями.
    """
    cfg = _assistant_cfg or {}
    name = str(cfg.get("name") or "Нейра")
    prompt = str(cfg.get("system_prompt") or "")
    # Короткая выжимка, чтобы не раздувать контекст при tool-call.
    return (
        f"Профиль: {name}. Тон: живой разговорный, с иронией по ситуации; русский язык; "
        "короткие ответы 1-3 предложения; без markdown/служебных тегов; "
        "без инструкций для реального вреда."
        + (f" В системном промпте настроено: {prompt[:220]}..." if prompt else "")
    )


# ─── Список всех инструментов для агента ─────────────────────────────────────

ALL_TOOLS = [
    get_current_time,
    check_system,
    web_search,
    search_memory,
    update_friend_fact,
    get_friend_info,
    get_character_profile,
]
