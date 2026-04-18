"""
Единый слой подключения к LLM через OpenAI-compatible HTTP API.

Провайдеры с нативно не-OpenAI API (anthropic, gemini) поддерживаются только
если задан llm.base_url на совместимый шлюз (OpenRouter, LiteLLM, прокси).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

# Пресеты: дефолтный base_url и переменные окружения для api_key (в порядке приоритета).
_OPENAI_COMPATIBLE_PRESETS: dict[str, dict[str, Any]] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": ("OPENROUTER_API_KEY",),
        "default_model": "qwen/qwen-2.5-72b-instruct",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": ("OPENAI_API_KEY",),
    },
    "ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key_env": (),
    },
    "lmstudio": {
        "base_url": "http://127.0.0.1:1234/v1",
        "api_key_env": (),
    },
    "vllm": {
        "base_url": "",
        "api_key_env": ("VLLM_API_KEY", "OPENAI_API_KEY"),
        "requires_base_url": True,
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": ("GROQ_API_KEY",),
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": ("MISTRAL_API_KEY",),
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "api_key_env": ("TOGETHER_API_KEY",),
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "api_key_env": ("FIREWORKS_API_KEY",),
    },
    # Нужен OpenAI-compatible endpoint в llm.base_url
    "anthropic": {
        "base_url": "",
        "api_key_env": ("ANTHROPIC_API_KEY", "LLM_API_KEY"),
        "requires_openai_compatible_base_url": True,
    },
    "gemini": {
        "base_url": "",
        "api_key_env": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_API_KEY"),
        "requires_openai_compatible_base_url": True,
    },
}

_DEFAULT_CAPABILITIES: dict[str, bool] = {
    "supports_stream": True,
    "supports_vision": True,
    "supports_tool_calls": False,
}


@dataclass(frozen=True)
class OpenAICompatibleConnection:
    """Параметры подключения ChatOpenAI (LangChain)."""

    provider: str
    base_url: str
    api_key: str
    default_headers: Mapping[str, str] = field(default_factory=dict)
    capabilities: dict[str, bool] = field(default_factory=dict)


def _first_env(*names: str) -> str:
    for name in names:
        v = (os.environ.get(name) or "").strip()
        if v:
            return v
    return ""


def resolved_primary_model(cfg: dict, provider: str) -> str:
    """Имя основной модели: llm.model → openrouter.model / primary_model → пресет."""
    llm = cfg.get("llm") or {}
    or_block = cfg.get("openrouter") or {}
    if isinstance(llm, dict) and llm.get("model"):
        return str(llm["model"]).strip()
    if isinstance(or_block, dict):
        for key in ("model", "primary_model"):
            v = or_block.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
    preset = _OPENAI_COMPATIBLE_PRESETS.get(provider, {})
    dm = preset.get("default_model")
    if dm:
        return str(dm).strip()
    return "gpt-4o-mini"


def merge_llm_tuning_options(cfg: dict) -> dict[str, Any]:
    """
    Параметры сэмплинга, таймаутов и т.д.: блок openrouter + переопределения из llm.

    Зарезервированные ключи llm не попадают в «тюнинг».
    """
    reserved = {
        "provider",
        "base_url",
        "api_key",
        "model",
        "capabilities",
        "default_headers",
        "referer",
        "app_title",
    }
    out: dict[str, Any] = dict(cfg.get("openrouter") or {})
    llm = cfg.get("llm") or {}
    if not isinstance(llm, dict):
        return out
    for k, v in llm.items():
        if k in reserved:
            continue
        if v is not None:
            out[k] = v
    return out


def resolve_openai_compatible_connection(cfg: dict) -> OpenAICompatibleConnection:
    """
    Собирает base_url / api_key / заголовки для OpenAI-compatible клиента.

    Приоритет провайдера: llm.provider -> BACKEND -> openrouter.
    """
    if not isinstance(cfg, dict):
        raise TypeError("config must be a dict")

    backend = str(cfg.get("BACKEND") or "openrouter").strip().lower()
    llm = cfg.get("llm") or {}
    if not isinstance(llm, dict):
        llm = {}

    provider = str(llm.get("provider") or backend).strip().lower()
    if not provider:
        provider = "openrouter"

    if provider not in _OPENAI_COMPATIBLE_PRESETS:
        known = ", ".join(sorted(_OPENAI_COMPATIBLE_PRESETS))
        raise ValueError(
            f"Неизвестный LLM-провайдер '{provider}'. "
            f"Допустимые значения: {known}. "
            "Для кастомного endpoint используйте провайдер с дефолтным URL и задайте llm.base_url."
        )

    preset = _OPENAI_COMPATIBLE_PRESETS[provider]
    or_block = cfg.get("openrouter") or {}
    if not isinstance(or_block, dict):
        or_block = {}

    base_url = str(llm.get("base_url") or or_block.get("base_url") or preset.get("base_url") or "").strip()
    if preset.get("requires_base_url") and not base_url:
        raise ValueError(
            f"Провайдер '{provider}' требует явного llm.base_url (или openrouter.base_url) "
            "на OpenAI-compatible endpoint."
        )
    if preset.get("requires_openai_compatible_base_url") and not base_url:
        raise ValueError(
            f"Провайдер '{provider}' не использует нативный OpenAI Chat Completions API. "
            "Укажите llm.base_url на OpenAI-compatible шлюз (например OpenRouter, LiteLLM proxy)."
        )

    api_key = str(llm.get("api_key") or or_block.get("api_key") or "").strip()
    if not api_key:
        for env_name in preset.get("api_key_env") or ():
            api_key = _first_env(env_name)
            if api_key:
                break
    if not api_key and provider == "openrouter":
        api_key = _first_env("OPENROUTER_API_KEY")
    if not api_key and provider == "ollama":
        # Ollama часто не требует ключа; LangChain принимает placeholder.
        api_key = "ollama"

    caps = dict(_DEFAULT_CAPABILITIES)
    raw_caps = llm.get("capabilities")
    if isinstance(raw_caps, dict):
        for k, v in raw_caps.items():
            if k in _DEFAULT_CAPABILITIES:
                caps[k] = bool(v)

    headers: dict[str, str] = {}
    if isinstance(llm.get("default_headers"), dict):
        for hk, hv in llm["default_headers"].items():
            if hk and hv is not None:
                headers[str(hk)] = str(hv)

    if provider == "openrouter":
        referer = str(llm.get("referer") or "https://aiassist.local").strip()
        title = str(llm.get("app_title") or "Neyra AI").strip()
        headers.setdefault("HTTP-Referer", referer)
        headers.setdefault("X-Title", title)

    return OpenAICompatibleConnection(
        provider=provider,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        default_headers=headers,
        capabilities=caps,
    )


def is_local_openai_compatible_provider(provider: str) -> bool:
    """Локальные/self-host профили для подсказок в системном промпте."""
    return provider.strip().lower() in {"ollama", "lmstudio", "vllm"}
