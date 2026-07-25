"""
Cloud voice adapters (STT/TTS) for Neyra.

Canonical: ``from core.voice.stt import STTEngine``,
``from core.voice.yandex_tts import synthesize_to_wav_bytes``.
Root ``core.stt`` / ``core.yandex_tts`` remain as compat shims.
"""

from __future__ import annotations

from typing import Any

__all__ = ["STTEngine", "synthesize_to_wav_bytes"]


def __getattr__(name: str) -> Any:
    if name == "STTEngine":
        from core.voice.stt import STTEngine

        return STTEngine
    if name == "synthesize_to_wav_bytes":
        from core.voice.yandex_tts import synthesize_to_wav_bytes

        return synthesize_to_wav_bytes
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
