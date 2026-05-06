from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from core.plugin_loader import PluginLoader


@dataclass(frozen=True)
class PluginBuilderSettings:
    """
    Личный tool: минимальные настройки прямо в файле (без config.yaml).

    Приоритет ключа:
    1) api_key (в аргументах tool-call)
    2) OPENROUTER_API_KEY из .env / окружения
    """

    # OpenRouter OpenAI-compatible endpoint
    base_url: str = "https://openrouter.ai/api/v1"
    # Минимально-адекватная дефолтная модель для код-генерации. Меняй здесь при необходимости.
    model: str = "qwen/qwen3-coder"
    # Защита: блокируем изменение этих плагинов из tool-а
    plugin_blacklist: tuple[str, ...] = ("discord", "internal_api", "laptop_screen")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _interfaces_dir(root: Path) -> Path:
    return (root / "interfaces").resolve()


def _normalize_plugin_id(plugin_id: str) -> str:
    return (plugin_id or "").strip().lower()


def _path_jail_check(abs_path: Path, allowed_root: Path) -> None:
    """
    Разрешаем запись строго внутри allowed_root.
    """

    abs_path = abs_path.resolve()
    allowed_root = allowed_root.resolve()
    try:
        abs_path.relative_to(allowed_root)
    except Exception as e:
        raise PermissionError(f"Path jail violation: {abs_path} is outside {allowed_root}") from e


def _openrouter_key(explicit_key: str | None) -> str | None:
    k = (explicit_key or "").strip()
    if k:
        return k
    k = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    return k or None


def _call_openrouter_chat(
    *,
    settings: PluginBuilderSettings,
    api_key: str,
    system: str,
    user: str,
    timeout_s: float = 120.0,
) -> str:
    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # Рекомендованные заголовки OpenRouter (не обязательны)
        "HTTP-Referer": "https://github.com/KORESHon/Neyra-AIAssist",
        "X-Title": "Neyra Plugin Builder Tool",
    }
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        return json.dumps(data, ensure_ascii=False)


def create_or_edit_plugin_impl(
    *,
    plugin_id: str,
    task: str,
    api_key: str | None = None,
    settings: PluginBuilderSettings | None = None,
) -> dict[str, Any]:
    """
    Генерирует/правит файлы плагина внутри interfaces/<plugin_id>.

    Возвращает структурированный результат (дикт), чтобы агент мог кратко пересказать.
    """

    settings = settings or PluginBuilderSettings()
    pid = _normalize_plugin_id(plugin_id)
    if not pid:
        return {"ok": False, "error": "plugin_id is empty"}
    if pid in set(settings.plugin_blacklist):
        return {"ok": False, "error": f"Access denied: plugin '{pid}' is blacklisted"}

    root = _repo_root()
    interfaces = _interfaces_dir(root)
    plugin_dir = (interfaces / pid).resolve()
    _path_jail_check(plugin_dir, interfaces)

    key = _openrouter_key(api_key)
    if not key:
        return {"ok": False, "error": "OpenRouter API key missing (api_key arg or OPENROUTER_API_KEY env)"}

    loader = PluginLoader(root=root)
    existed = plugin_dir.exists()
    backup_ok = False
    backup_path = None
    if existed:
        backup_ok, backup_path = loader.create_plugin_backup(pid)

    # Подготовим минимальный контекст: существующие файлы (только верхний уровень, без рекурсии).
    existing_files: dict[str, str] = {}
    if existed:
        try:
            for p in sorted(plugin_dir.glob("*.py")):
                existing_files[p.name] = p.read_text(encoding="utf-8", errors="replace")[:20000]
            for p in sorted(plugin_dir.glob("*.yaml")):
                existing_files[p.name] = p.read_text(encoding="utf-8", errors="replace")[:20000]
            for p in sorted(plugin_dir.glob("*.md")):
                existing_files[p.name] = p.read_text(encoding="utf-8", errors="replace")[:20000]
        except Exception:
            # не критично — просто без контекста
            existing_files = {}

    system = (
        "Ты — инженер по плагинам проекта Neyra.\n"
        "Нужно сгенерировать изменения плагина в interfaces/<plugin_id>.\n"
        "ВЫХОД СТРОГО: JSON вида {\"files\": [{\"path\": \"relative/path\", \"content\": \"...\"}], \"notes\": \"...\"}.\n"
        "Запрещено менять что-либо вне interfaces/<plugin_id>.\n"
        "Не трогай плагины: discord, internal_api, laptop_screen.\n"
        "Если создаёшь новый плагин: добавь plugin.yaml и минимальный main.py с run_plugin(ctx).\n"
        "Не добавляй бинарные данные.\n"
    )
    user = json.dumps(
        {
            "plugin_id": pid,
            "task": task,
            "existing_files": existing_files,
        },
        ensure_ascii=False,
    )

    raw = _call_openrouter_chat(settings=settings, api_key=key, system=system, user=user)
    try:
        plan = json.loads(raw)
    except Exception as e:
        # При плохом JSON не пишем ничего
        return {"ok": False, "error": f"Model output is not valid JSON: {e}", "raw": raw[:4000]}

    files = plan.get("files")
    if not isinstance(files, list) or not files:
        return {"ok": False, "error": "Model output JSON missing 'files' list", "raw": raw[:2000]}

    written: list[str] = []
    try:
        plugin_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            if not isinstance(f, dict):
                continue
            rel = str(f.get("path") or "").replace("\\", "/").lstrip("/")
            content = f.get("content")
            if not rel or not isinstance(content, str):
                continue
            target = (plugin_dir / rel).resolve()
            _path_jail_check(target, plugin_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(rel)
    except Exception as e:
        if existed and backup_ok and backup_path:
            loader.rollback_plugin(pid, backup_path=backup_path)
        return {"ok": False, "error": f"Write failed: {e}", "written": written}

    # Reload: если reload упадёт, откатываемся (если есть бэкап)
    ok, msg = loader.reload_plugin(pid)
    if not ok and existed and backup_ok and backup_path:
        loader.rollback_plugin(pid, backup_path=backup_path)
        ok2, msg2 = loader.reload_plugin(pid)
        return {
            "ok": False,
            "error": f"Reload failed: {msg}. Rolled back: {msg2}",
            "written": written,
        }

    return {
        "ok": True,
        "plugin_id": pid,
        "existed": existed,
        "backup": backup_path if backup_ok else None,
        "written": written,
        "notes": str(plan.get("notes") or "")[:2000],
    }

