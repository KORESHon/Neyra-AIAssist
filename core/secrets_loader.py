"""Загрузка .env и подстановка секретов в конфиг (ключи не хранятся в config.yaml)."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv_file(root: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    p = root / ".env"
    if p.is_file():
        load_dotenv(p, override=False)


def _s(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def apply_env_secrets(cfg: dict) -> None:
    """Непустые переменные из окружения перезаписывают соответствующие поля конфига."""
    if not isinstance(cfg, dict):
        return

    k = _s("OPENROUTER_API_KEY")
    if k:
        cfg.setdefault("openrouter", {})["api_key"] = k

    lk = _s("LLM_API_KEY")
    if lk:
        raw_llm = cfg.get("llm")
        llm_block = raw_llm if isinstance(raw_llm, dict) else {}
        if not str(llm_block.get("api_key") or "").strip():
            merged = dict(llm_block)
            merged["api_key"] = lk
            cfg["llm"] = merged

    g = _s("GROQ_API_KEY")
    if g:
        vc = cfg.setdefault("voice_cloud", {})
        stt = vc.setdefault("stt", {})
        stt["groq_api_key"] = g

    dg = _s("DEEPGRAM_API_KEY")
    if dg:
        vc = cfg.setdefault("voice_cloud", {})
        stt = vc.setdefault("stt", {})
        stt["deepgram_api_key"] = dg

    d = _s("DISCORD_TOKEN")
    if d:
        cfg.setdefault("discord", {})["token"] = d

    hf = _s("HF_TOKEN") or _s("HUGGING_FACE_HUB_TOKEN")
    if hf:
        cfg.setdefault("memory", {})["hf_token"] = hf

    ex = _s("EXTERNAL_API_KEY")
    if ex:
        cfg.setdefault("external_api", {})["api_key"] = ex

    sp = _s("SCREEN_PROXY_SECRET")
    if sp:
        vis = cfg.setdefault("vision", {})
        vis.setdefault("screen_proxy", {})["secret"] = sp

    tid = _s("TELEGRAM_API_ID")
    if tid:
        cfg.setdefault("telegram", {})["api_id"] = tid

    tah = _s("TELEGRAM_API_HASH")
    if tah:
        cfg.setdefault("telegram", {})["api_hash"] = tah

    apk = _s("AGENT_PROXY_SECRET_KEY")
    if apk:
        cfg.setdefault("agent_proxy", {})["secret_key"] = apk

    iat = _s("INTERNAL_API_TOKEN")
    if iat:
        cfg.setdefault("internal_api", {})["token"] = iat

    yk = _s("YANDEX_API_KEY")
    yf = _s("YANDEX_FOLDER_ID") or _s("YANDEX_ID_KEY")
    if yk or yf:
        vc = cfg.setdefault("voice_cloud", {})
        tts = vc.setdefault("tts", {})
        if yk:
            tts["api_key"] = yk
        if yf:
            tts["folder_id"] = yf
