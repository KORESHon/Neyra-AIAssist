"""
core.agent — Neyra orchestration package (Phase 1R).

Canonical: ``from core.agent import NeyraAgent``.
"""

from __future__ import annotations

from core.agent.neyra import (
    DEPRECATED_OPENROUTER_MODELS,
    EMPTY_REPLY_PLACEHOLDER,
    LYRICS_REQUEST_MARKER,
    NeyraAgent,
)

__all__ = [
    "DEPRECATED_OPENROUTER_MODELS",
    "EMPTY_REPLY_PLACEHOLDER",
    "LYRICS_REQUEST_MARKER",
    "NeyraAgent",
]
