from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


OPENROUTER_API_KEY = get_env("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = get_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
DEFAULT_MODEL = get_env("DEFAULT_MODEL", "openrouter/free")
MANAGER_MODEL = get_env("MANAGER_MODEL", DEFAULT_MODEL)
MARKETING_MODEL = get_env("MARKETING_MODEL", DEFAULT_MODEL)
SALES_MODEL = get_env("SALES_MODEL", DEFAULT_MODEL)
AUTOMATION_MODEL = get_env("AUTOMATION_MODEL", DEFAULT_MODEL)
EVALUATION_MODEL = get_env("EVALUATION_MODEL", DEFAULT_MODEL)
PROJECT_NAME = get_env("PROJECT_NAME", "AI Business Team")
