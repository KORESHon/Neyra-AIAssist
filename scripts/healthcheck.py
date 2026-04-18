#!/usr/bin/env python3
"""
Simple project healthcheck for Neyra 2.0.

Checks:
- required files exist
- .env availability
- required env vars for selected modes (LLM provider из config.yaml)
- optional HTTP probe: GET {llm base_url}/models (OpenAI-compatible)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def load_dotenv(root: Path) -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    env_file = root / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=False)


def load_config(root: Path) -> dict:
    import yaml

    from core.secrets_loader import apply_env_secrets

    cfg_path = root / "config.yaml"
    if not cfg_path.is_file():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return {}
    apply_env_secrets(data)
    return data


def check_files(root: Path) -> list[str]:
    required = [
        "main.py",
        "config.yaml",
        "requirements.txt",
        ".env.example",
        "interfaces/discord_text_bot.py",
    ]
    errors: list[str] = []
    for rel in required:
        if not (root / rel).exists():
            errors.append(f"Missing required file: {rel}")
    return errors


def check_llm_config_and_env(cfg: dict) -> list[str]:
    from core.llm_profile import resolve_openai_compatible_connection

    errs: list[str] = []
    try:
        conn = resolve_openai_compatible_connection(cfg)
    except Exception as e:
        errs.append(f"LLM config invalid: {e}")
        return errs

    ak = (conn.api_key or "").strip()
    if conn.provider == "ollama":
        return errs
    if not ak or ak == "ollama":
        errs.append(
            f"LLM API key missing for provider '{conn.provider}' "
            "(set llm.api_key / openrouter.api_key or provider env / LLM_API_KEY)"
        )
    return errs


def check_discord_token(mode: str) -> list[str]:
    if mode != "discord":
        return []
    if not (os.environ.get("DISCORD_TOKEN") or "").strip():
        return ["DISCORD_TOKEN is not set (required for discord mode)"]
    return []


def check_llm_models_probe(cfg: dict) -> list[str]:
    from core.llm_profile import resolve_openai_compatible_connection

    errs: list[str] = []
    try:
        conn = resolve_openai_compatible_connection(cfg)
    except Exception as e:
        errs.append(f"LLM probe skipped (bad config): {e}")
        return errs

    base = conn.base_url.rstrip("/")
    url = f"{base}/models"
    headers: dict[str, str] = {}
    ak = (conn.api_key or "").strip()
    if ak and ak != "ollama":
        headers["Authorization"] = f"Bearer {ak}"

    try:
        import httpx

        r = httpx.get(url, headers=headers, timeout=12.0)
        if r.status_code >= 400:
            errs.append(f"LLM models probe failed ({conn.provider}): HTTP {r.status_code} @ {url}")
    except Exception as e:
        errs.append(f"LLM models probe exception ({conn.provider}): {e}")
    return errs


def main() -> int:
    parser = argparse.ArgumentParser(description="Neyra 2.0 healthcheck")
    parser.add_argument("--mode", choices=["model", "discord"], default="model")
    parser.add_argument("--skip-http", action="store_true", help="Skip LLM /v1/models HTTP probe")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    r = str(root)
    if r not in sys.path:
        sys.path.insert(0, r)
    load_dotenv(root)
    cfg = load_config(root)

    errors: list[str] = []
    errors.extend(check_files(root))
    errors.extend(check_llm_config_and_env(cfg))
    errors.extend(check_discord_token(args.mode))
    if not args.skip_http:
        errors.extend(check_llm_models_probe(cfg))

    print("== Neyra Healthcheck ==")
    print(f"Root: {root}")
    print(f"Mode: {args.mode}")
    if errors:
        print("Status: FAIL")
        for e in errors:
            print(f"- {e}")
        return 1

    print("Status: OK")
    print("- Core files present")
    print("- LLM configuration and secrets look usable for this mode")
    if args.skip_http:
        print("- LLM HTTP probe skipped")
    else:
        print("- LLM OpenAI-compatible /v1/models probe passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
