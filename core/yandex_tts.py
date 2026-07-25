"""Compat shim — prefer ``from core.voice.yandex_tts import synthesize_to_wav_bytes``."""

from __future__ import annotations

from core.voice.yandex_tts import (
    DEFAULT_ENDPOINT,
    synthesize_to_wav_bytes,
)

__all__ = ["DEFAULT_ENDPOINT", "synthesize_to_wav_bytes"]
