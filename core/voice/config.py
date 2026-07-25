"""Resolve unified ``voice`` config (local vs cloud STT/TTS).

Canonical shape::

    voice:
      is_local: false
      language: "ru"
      fallback_to_local: true
      local:
        stt: { model, device, ... }
        tts: { ... }
      cloud:
        stt: { provider, openrouter/deepgram/groq, ... }
        tts: { provider, ... }

Legacy shapes (``voice.stt``, ``voice_cloud``) are accepted and normalized in-memory.
"""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_voice_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Return a normalized ``voice`` dict. Does not mutate ``config`` unless legacy
    roots need to be read; callers should use the returned structure.
    """
    raw = _as_dict(config.get("voice"))
    legacy_cloud = _as_dict(config.get("voice_cloud"))

    # Already new shape?
    if "local" in raw or "cloud" in raw or "is_local" in raw:
        voice = {
            "is_local": bool(raw.get("is_local", False)),
            "language": str(raw.get("language") or "ru"),
            "timeout_seconds": float(raw.get("timeout_seconds", 30.0)),
            "max_retries": int(raw.get("max_retries", 1)),
            "fallback_to_local": bool(raw.get("fallback_to_local", True)),
            "local": _as_dict(raw.get("local")),
            "cloud": _as_dict(raw.get("cloud")),
        }
        voice["local"].setdefault("stt", {})
        voice["local"].setdefault("tts", {})
        voice["cloud"].setdefault("stt", {})
        voice["cloud"].setdefault("tts", {})
        if not isinstance(voice["local"]["stt"], dict):
            voice["local"]["stt"] = {}
        if not isinstance(voice["local"]["tts"], dict):
            voice["local"]["tts"] = {}
        if not isinstance(voice["cloud"]["stt"], dict):
            voice["cloud"]["stt"] = {}
        if not isinstance(voice["cloud"]["tts"], dict):
            voice["cloud"]["tts"] = {}
        return voice

    # Legacy: voice.stt + voice_cloud
    old_stt = _as_dict(raw.get("stt"))
    lc_stt = _as_dict(legacy_cloud.get("stt"))
    lc_tts = _as_dict(legacy_cloud.get("tts"))

    engine = str(old_stt.get("engine") or lc_stt.get("provider") or "faster-whisper").strip().lower()
    is_local = engine in ("faster-whisper", "local", "whisper")

    cloud_stt: dict[str, Any] = {
        "provider": "deepgram" if is_local else engine,
        "openrouter": _as_dict(old_stt.get("openrouter")),
        "deepgram": _as_dict(old_stt.get("deepgram")),
        "groq": _as_dict(old_stt.get("groq")),
    }
    if not cloud_stt["deepgram"] and lc_stt:
        cloud_stt["deepgram"] = {
            "model": lc_stt.get("model", "nova-3"),
            "base_url": lc_stt.get("base_url", "https://api.deepgram.com/v1"),
            "api_key": lc_stt.get("deepgram_api_key") or lc_stt.get("api_key"),
        }
        if not is_local and engine == "deepgram":
            cloud_stt["provider"] = "deepgram"

    return {
        "is_local": is_local,
        "language": str(old_stt.get("language") or lc_stt.get("language") or "ru"),
        "timeout_seconds": float(old_stt.get("timeout_seconds") or lc_stt.get("timeout_seconds") or 30.0),
        "max_retries": int(old_stt.get("max_retries", 1)),
        "fallback_to_local": bool(old_stt.get("fallback_to_local", True)),
        "local": {
            "stt": {
                "model": old_stt.get("model", "small"),
                "device": old_stt.get("device", "cpu"),
            },
            "tts": {},
        },
        "cloud": {
            "stt": cloud_stt,
            "tts": lc_tts,
        },
    }


def resolve_stt_runtime(config: dict[str, Any]) -> dict[str, Any]:
    """
    Flatten voice config for STTEngine.

    Returns keys used by STTEngine:
    is_local, engine, language, timeout_seconds, max_retries, fallback_to_local,
    local_stt, cloud_stt, openrouter, deepgram, groq.
    """
    voice = normalize_voice_config(config)
    local_stt = _as_dict(voice["local"].get("stt"))
    cloud_stt = _as_dict(voice["cloud"].get("stt"))

    if voice["is_local"]:
        engine = "faster-whisper"
    else:
        engine = str(
            cloud_stt.get("provider") or cloud_stt.get("engine") or "deepgram"
        ).strip().lower()
        if engine in ("faster-whisper", "local", "whisper"):
            engine = "deepgram"

    return {
        "is_local": voice["is_local"],
        "engine": engine,
        "language": voice["language"],
        "timeout_seconds": voice["timeout_seconds"],
        "max_retries": voice["max_retries"],
        "fallback_to_local": voice["fallback_to_local"],
        "local_stt": local_stt,
        "cloud_stt": cloud_stt,
        "openrouter": _as_dict(cloud_stt.get("openrouter")),
        "deepgram": _as_dict(cloud_stt.get("deepgram")),
        "groq": _as_dict(cloud_stt.get("groq")),
    }


def resolve_tts_runtime(config: dict[str, Any]) -> dict[str, Any]:
    """Return active TTS block (local or cloud) plus is_local flag."""
    voice = normalize_voice_config(config)
    branch = "local" if voice["is_local"] else "cloud"
    tts = _as_dict(voice[branch].get("tts"))
    return {
        "is_local": voice["is_local"],
        "tts": tts,
        "language": voice["language"],
    }
