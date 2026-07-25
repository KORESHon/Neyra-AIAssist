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
        # Canonical: voice.cloud.stt.groq.api_key (+ legacy voice.stt / voice_cloud mirrors)
        cloud_stt = (
            cfg.setdefault("voice", {})
            .setdefault("cloud", {})
            .setdefault("stt", {})
        )
        groq_block = cloud_stt.setdefault("groq", {})
        if isinstance(groq_block, dict):
            groq_block["api_key"] = g
        legacy_stt = cfg.setdefault("voice", {}).setdefault("stt", {})
        if isinstance(legacy_stt, dict):
            legacy_stt.setdefault("groq", {})["api_key"] = g
        vc = cfg.setdefault("voice_cloud", {})
        stt = vc.setdefault("stt", {})
        stt["groq_api_key"] = g

    dg = _s("DEEPGRAM_API_KEY")
    if dg:
        cloud_stt = (
            cfg.setdefault("voice", {})
            .setdefault("cloud", {})
            .setdefault("stt", {})
        )
        dg_block = cloud_stt.setdefault("deepgram", {})
        if isinstance(dg_block, dict):
            dg_block["api_key"] = dg
        legacy_stt = cfg.setdefault("voice", {}).setdefault("stt", {})
        if isinstance(legacy_stt, dict):
            legacy_stt.setdefault("deepgram", {})["api_key"] = dg
        vc = cfg.setdefault("voice_cloud", {})
        stt = vc.setdefault("stt", {})
        stt["deepgram_api_key"] = dg

    d = _s("DISCORD_TOKEN")
    if d:
        cfg.setdefault("discord", {})["token"] = d

    hf = _s("HF_TOKEN") or _s("HUGGING_FACE_HUB_TOKEN")
    if hf:
        cfg.setdefault("memory", {})["hf_token"] = hf

    sp = _s("SCREEN_PROXY_SECRET")
    if sp:
        # Будущий отдельный модуль screen-proxy (не vision.*); см. PLAN / документацию плагина.
        plug = cfg.setdefault("screen_proxy_plugin", {})
        if isinstance(plug, dict):
            plug["secret"] = sp

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

    bind_h = _s("INTERNAL_API_BIND_HOST")
    if bind_h:
        cfg.setdefault("internal_api", {})["host"] = bind_h

    iv = _s("INTERNAL_API_VIEWER_TOKEN")
    if iv:
        cfg.setdefault("internal_api", {})["viewer_token"] = iv

    im = _s("INTERNAL_API_MAINT_TOKEN")
    if im:
        cfg.setdefault("internal_api", {})["maint_token"] = im

    wh_in = _s("WEBHOOK_INBOUND_SECRET")
    if wh_in:
        cfg.setdefault("internal_api", {})["webhook_inbound_secret"] = wh_in

    yk = _s("YANDEX_API_KEY")
    yf = _s("YANDEX_FOLDER_ID") or _s("YANDEX_ID_KEY")
    if yk or yf:
        cloud_tts = (
            cfg.setdefault("voice", {})
            .setdefault("cloud", {})
            .setdefault("tts", {})
        )
        if yk:
            cloud_tts["api_key"] = yk
        if yf:
            cloud_tts["folder_id"] = yf
        # Legacy mirror for older callers still reading voice_cloud.tts
        vc = cfg.setdefault("voice_cloud", {})
        tts = vc.setdefault("tts", {})
        if yk:
            tts["api_key"] = yk
        if yf:
            tts["folder_id"] = yf
