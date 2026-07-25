"""Compat shim — prefer ``from core.runtime import apply_env_secrets, load_dotenv_file``."""

from __future__ import annotations

from core.runtime.secrets import apply_env_secrets, load_dotenv_file

__all__ = ["apply_env_secrets", "load_dotenv_file"]
