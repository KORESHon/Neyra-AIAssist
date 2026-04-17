"""
Совместимость с новой структурой Neyra 2.0.

Активный runtime текстового бота не использует TTS напрямую, но модуль
оставлен в core/voice для облачных сценариев/будущих интерфейсов.
"""

from core.yandex_tts import YandexTTS  # re-export

__all__ = ["YandexTTS"]

