#!/usr/bin/env python3
"""
Simple project healthcheck for Neyra 2.0.

Checks:
- required files exist
- .env availability
- required env vars for selected modes
- optional HTTP probe for OpenRouter models endpoint
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


def check_env(mode: str) -> list[str]:
    errors: list[str] = []
    if not os.environ.get("OPENROUTER_API_KEY"):
        errors.append("OPENROUTER_API_KEY is not set")
    if mode == "discord" and not os.environ.get("DISCORD_TOKEN"):
        errors.append("DISCORD_TOKEN is not set (required for discord mode)")
    return errors


def check_openrouter_probe() -> list[str]:
    errs: list[str] = []
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        return errs
    try:
        import httpx

        r = httpx.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=12.0,
        )
        if r.status_code >= 400:
            errs.append(f"OpenRouter probe failed: HTTP {r.status_code}")
    except Exception as e:
        errs.append(f"OpenRouter probe exception: {e}")
    return errs


def main() -> int:
    parser = argparse.ArgumentParser(description="Neyra 2.0 healthcheck")
    parser.add_argument("--mode", choices=["model", "discord"], default="model")
    parser.add_argument("--skip-http", action="store_true", help="Skip OpenRouter HTTP probe")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    load_dotenv(root)

    errors: list[str] = []
    errors.extend(check_files(root))
    errors.extend(check_env(args.mode))
    if not args.skip_http:
        errors.extend(check_openrouter_probe())

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
    print("- Required environment variables are set")
    if args.skip_http:
        print("- OpenRouter probe skipped")
    else:
        print("- OpenRouter probe passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

