"""Compat shim — prefer ``from core.llm import fetch_openrouter_key_usage``."""

from __future__ import annotations

from core.llm.openrouter_balance import fetch_openrouter_key_usage

__all__ = ["fetch_openrouter_key_usage"]
