"""
core/tools.py — Инструменты (Tools) для агента Нейры
──────────────────────────────────────────────────────
LLM может вызывать эти функции сама через Function Calling.

Динамические MCP-инструменты подмешиваются в рантайме (core/mcp_client.py + NeyraAgent._ensure_mcp),
их имена вида mcp_<server>_<tool>.

Текущие инструменты:
  • TimeContextTool   — текущее время и дата
  • SystemMonitorTool — состояние системы (безопасные команды)
  • WebSearchTool     — поиск через DuckDuckGo
  • MemorySearchTool  — поиск по ChromaDB
  • RememberKnowledge — сохранить фрагмент в ChromaDB (любая полезная информация)
  • UpdatePersonFact  — записать новый факт о человеке
  • GetPersonInfo     — получить досье на человека
"""

from __future__ import annotations

import logging
import platform
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING

from langchain_core.tools import tool

if TYPE_CHECKING:
    from core.memory import LongTermMemory, PeopleDB

logger = logging.getLogger("neyra.tools")

# Будут заинжектированы при инициализации агента
_long_memory: "LongTermMemory | None" = None
_people_db: "PeopleDB | None" = None
_assistant_cfg: dict | None = None


def init_tools(long_memory, people_db, assistant_cfg: dict | None = None) -> None:
    """Инициализирует ссылки на модули памяти."""
    global _long_memory, _people_db, _assistant_cfg
    _long_memory = long_memory
    _people_db = people_db
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
    Ищет в долгосрочной памяти по смыслу: прошлые фрагменты диалогов и сохранённые знания (RAG).
    Используй, когда нужно вспомнить факты, о чём договаривались, что сохраняли через remember_knowledge.
    query — суть того, что нужно найти.
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


@tool
def remember_knowledge(text: str, category: str = "general") -> str:
    """
    Сохраняет фрагмент в долгосрочную векторную память (RAG), чтобы позже найти через search_memory.

    Используй для **любой нормальной информации**, которую разумно вспоминать позже: факты, новости, ситуации, договорённости,
    предпочтения, контекст чата, заметки о проекте, ссылки на события — не только мемы и шутки.
    Отдельно про людей: если речь о конкретном человеке из досье — чаще уместен update_person_fact; для всего остального
    универсального контекста — remember_knowledge.

    Для **мемов, приколов, локальных шуток, интернет-отсылок** тоже сохраняй: удобно передать category=\"meme\" или \"шутки\";
    при необходимости можно начать text с «[Категория: Мемы/Шутки]».

    text — что запомнить (кратко, 1–5 предложений, своими словами).
    category — необязательная метка: general, news, situation, meme, fact, шутки и т.п.
    """
    if _long_memory is None:
        return "Долгосрочная память не инициализирована."

    meta = {"source": "agent_tool", "category": (category or "general").strip()[:120]}
    ok, info = _long_memory.add_knowledge(text.strip(), meta)
    if ok:
        return f"Запомнила в долгую память (документ {info})."
    return f"Не удалось сохранить: {info}"


# ─── UpdatePersonFact ────────────────────────────────────────────────────────

@tool
def update_person_fact(person_id: str, fact: str) -> str:
    """
    Записывает новый факт о человеке в базу досье (PeopleDB).
    Используй когда узнала что-то новое о друге или знакомом.
    person_id — ID человека (maxim, kutyr, timofey, andrey_griniks, bogdan, foxy, erik).
    fact — что именно узнала (кратко, своими словами).
    """
    if _people_db is None:
        return "PeopleDB не инициализирована."

    success = _people_db.update_fact(person_id, fact)
    if success:
        return f"Записала. Теперь знаю про {person_id}: {fact}"
    else:
        # Попробуем найти по нечёткому совпадению
        person = _people_db.find(person_id)
        if person:
            _people_db.update_fact(person["id"], fact)
            return f"Нашла по имени и записала про {person['names'][0]}: {fact}"
        return f"Не нашла человека '{person_id}' в базе. Проверь ID."


# ─── GetPersonInfo ───────────────────────────────────────────────────────────

@tool
def get_person_info(name_or_id: str) -> str:
    """
    Получает досье на человека из базы.
    Используй когда нужно вспомнить кто это такой и что о нём знаешь.
    name_or_id — имя, ник или ID человека.
    """
    if _people_db is None:
        return "PeopleDB не инициализирована."

    person = _people_db.find(name_or_id)
    if not person:
        return f"Никого с именем/ником '{name_or_id}' в базе нет. Может это новый человек?"

    summary = _people_db.get_summary(person["id"])
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


# ─── Plugin Builder Tool (E3) ─────────────────────────────────────────────────

@tool
def create_or_edit_plugin(plugin_id: str, task: str, api_key: str = "") -> str:
    """
    Личный инструмент для **создания/редактирования плагинов Neyra** в `interfaces/<plugin_id>`.

    **ВАЖНО ДЛЯ МОДЕЛИ (brain_model):**
    - Если пользователь просит *создать / написать / изменить / исправить / сгенерировать* плагин/модуль Neyra
      (всё, что относится к `interfaces/`), **нужно вызывать ТОЛЬКО этот инструмент**.
    - **КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО** делать web-поиск, Wikipedia, “как написать плагин” и т.п. — это внутренняя задача проекта.
      Не трать tool-calls на `web_search` для таких запросов.

    - Пишет СТРОГО внутри `interfaces/<plugin_id>` (Path Jail).
    - Блокирует изменения критических плагинов: discord, internal_api, laptop_screen.
    - Генерация кода делегируется облачной модели OpenRouter.

    api_key: опционально. Если пусто — берётся из OPENROUTER_API_KEY (env/.env).
    """
    try:
        logger.info("Tool create_or_edit_plugin: start | plugin_id=%s", (plugin_id or "").strip())
        from core.plugin_builder_tool import create_or_edit_plugin_impl

        out = create_or_edit_plugin_impl(plugin_id=plugin_id, task=task, api_key=api_key or None)
        # Возвращаем строку (для tool-calls), но в JSON-формате для наглядности.
        import json

        logger.info("Tool create_or_edit_plugin: done | ok=%s", bool(out.get("ok")))
        return json.dumps(out, ensure_ascii=False)
    except Exception as e:
        logger.exception("Tool create_or_edit_plugin: failed | plugin_id=%s", (plugin_id or "").strip())
        return f"create_or_edit_plugin failed: {e}"


# ─── Список всех инструментов для агента ─────────────────────────────────────

ALL_TOOLS = [
    get_current_time,
    check_system,
    web_search,
    search_memory,
    remember_knowledge,
    update_person_fact,
    get_person_info,
    get_character_profile,
    create_or_edit_plugin,
]
