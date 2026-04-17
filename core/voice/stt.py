"""
Совместимость с новой структурой Neyra 2.0.

Активный runtime текстового бота не использует STT напрямую, но модуль
оставлен в core/voice для облачных сценариев/будущих интерфейсов.
"""

from core.stt import STTEngine  # re-export

__all__ = ["STTEngine"]

