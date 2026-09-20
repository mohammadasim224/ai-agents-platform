from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

KNOWLEDGE_DIR = ROOT_DIR / "knowledge"
PROMPTS_DIR = ROOT_DIR / "prompts"
UPLOADS_DIR = ROOT_DIR / "data" / "uploads"
ARTIFACTS_DIR = ROOT_DIR / "data" / "artifacts"


def get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


OPENROUTER_API_KEY = get_env("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = get_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
DEFAULT_MODEL = get_env("DEFAULT_MODEL", "openrouter/free")

MANAGER_MODEL = get_env("MANAGER_MODEL", DEFAULT_MODEL)
MARKETING_MODEL = get_env("MARKETING_MODEL", DEFAULT_MODEL)
SALES_MODEL = get_env("SALES_MODEL", DEFAULT_MODEL)
AUTOMATION_MODEL = get_env("AUTOMATION_MODEL", DEFAULT_MODEL)
EVALUATION_MODEL = get_env("EVALUATION_MODEL", DEFAULT_MODEL)

PROJECT_NAME = get_env("PROJECT_NAME", "AI Business Team")

# Reliability controls. A request that cannot be served well must fail loudly
# rather than fall back to an off-target answer.
LLM_MAX_ATTEMPTS = get_env_int("LLM_MAX_ATTEMPTS", 3)
LLM_RETRY_BACKOFF_SECONDS = get_env_float("LLM_RETRY_BACKOFF_SECONDS", 1.5)
LLM_TIMEOUT_SECONDS = get_env_int("LLM_TIMEOUT_SECONDS", 120)
LLM_TEMPERATURE = get_env_float("LLM_TEMPERATURE", 0.4)
LLM_MAX_TOKENS = get_env_int("LLM_MAX_TOKENS", 4000)

# Minimum characters an agent deliverable must reach to be considered real work.
MIN_DELIVERABLE_CHARS = get_env_int("MIN_DELIVERABLE_CHARS", 120)

# Sales script backtesting quality gate.
BACKTEST_TARGET_CONVERSION = get_env_float("BACKTEST_TARGET_CONVERSION", 0.5)
BACKTEST_MIN_CALLS = get_env_int("BACKTEST_MIN_CALLS", 20)
BACKTEST_MAX_CALLS = get_env_int("BACKTEST_MAX_CALLS", 40)
BACKTEST_BATCH_SIZE = get_env_int("BACKTEST_BATCH_SIZE", 4)
BACKTEST_MAX_ROUNDS = get_env_int("BACKTEST_MAX_ROUNDS", 5)

FRONTEND_ORIGINS = [
    origin.strip()
    for origin in get_env(
        "FRONTEND_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if origin.strip()
]

for directory in (UPLOADS_DIR, ARTIFACTS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
