"""Compat shim — prefer ``from core.voice import STTEngine`` or ``core.voice.stt``."""

from __future__ import annotations

from core.voice.stt import STTEngine

__all__ = ["STTEngine"]
