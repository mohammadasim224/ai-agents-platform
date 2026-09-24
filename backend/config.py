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


def iter_knowledge_files(root: Path) -> list[Path]:
    """Every markdown file under `root`, skipping hidden directories.

    Backup folders such as `knowledge/business/.backup/` hold superseded copies
    of the knowledge base. They must never be indexed: doing so feeds the agents
    an older version of the business as if it were current. Any path segment that
    starts with a dot (`.backup`, `.git`, ...) is treated as hidden and skipped.
    """
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*.md")
        if not any(part.startswith(".") for part in path.relative_to(root).parts)
    )


OPENROUTER_API_KEY = get_env("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = get_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Base model. Per-role overrides (`MANAGER_MODEL`, `SALES_MODEL`, ...) are read
# on demand in `backend/llm/models.py`, which is the single place that resolves
# a role to a model.
DEFAULT_MODEL = get_env("DEFAULT_MODEL", "openrouter/free")

PROJECT_NAME = get_env("PROJECT_NAME", "AI Business Team")

# Reliability controls. A request that cannot be served well must fail loudly
# rather than fall back to an off-target answer.
LLM_MAX_ATTEMPTS = get_env_int("LLM_MAX_ATTEMPTS", 3)
LLM_RETRY_BACKOFF_SECONDS = get_env_float("LLM_RETRY_BACKOFF_SECONDS", 1.5)
LLM_TIMEOUT_SECONDS = get_env_int("LLM_TIMEOUT_SECONDS", 120)
LLM_TEMPERATURE = get_env_float("LLM_TEMPERATURE", 0.4)
LLM_MAX_TOKENS = get_env_int("LLM_MAX_TOKENS", 4000)

# Speed controls. The pipeline makes many sequential provider calls, so the
# wall-clock cost is dominated by how many calls run one after another. These
# knobs let independent calls run concurrently and cap how long a single job may
# spend, so a request finishes in minutes rather than tens of minutes.
#
# `PIPELINE_MAX_WORKERS` bounds the thread pool used for independent provider
# calls (departments, subtasks, and backtest batches). It is deliberately small:
# the provider rate-limits aggressive fan-out, and a bounded pool keeps the
# request predictable.
PIPELINE_MAX_WORKERS = get_env_int("PIPELINE_MAX_WORKERS", 6)

# Hard wall-clock budget for one generation job. When the budget is exhausted the
# pipeline stops starting new work and reports the best verified result it has,
# so a job can never run for tens of minutes. The queue watchdog uses a slightly
# larger value so a job that respects its own budget is never reclaimed mid-run.
PIPELINE_DEADLINE_SECONDS = get_env_int("PIPELINE_DEADLINE_SECONDS", 270)

# Minimum characters an agent deliverable must reach to be considered real work.
MIN_DELIVERABLE_CHARS = get_env_int("MIN_DELIVERABLE_CHARS", 120)

# Upload limits. A knowledge file is read into memory to be indexed, so an
# unbounded upload could exhaust memory. The limit is enforced while streaming
# the request body, not after it has already been buffered.
MAX_UPLOAD_BYTES = get_env_int("MAX_UPLOAD_MB", 25) * 1024 * 1024

# Sales script backtesting quality gate.
#
# The bar is per specialist: a closer script must close at least 20% of
# simulated calls, while a setter script must book at least 50%. The defaults
# below are the fallback for any specialist without an explicit target.
BACKTEST_TARGET_CONVERSION = get_env_float("BACKTEST_TARGET_CONVERSION", 0.5)
BACKTEST_MIN_CALLS = get_env_int("BACKTEST_MIN_CALLS", 20)
BACKTEST_MAX_CALLS = get_env_int("BACKTEST_MAX_CALLS", 40)
BACKTEST_BATCH_SIZE = get_env_int("BACKTEST_BATCH_SIZE", 4)
BACKTEST_MAX_ROUNDS = get_env_int("BACKTEST_MAX_ROUNDS", 5)

# Per-specialist conversion targets. A closer script is judged on closed deals
# (20%), a setter script on booked appointments (50%).
BACKTEST_TARGETS: dict[str, float] = {
    "closing": get_env_float("BACKTEST_TARGET_CLOSING", 0.20),
    "appointment_setting": get_env_float("BACKTEST_TARGET_APPOINTMENT_SETTING", 0.50),
}

# Wall-clock budget for a single backtest. The backtest runs its batches
# concurrently, so this bounds the whole gate rather than one batch. When the
# budget is exhausted the backtest reports the measured rate so far instead of
# running indefinitely.
BACKTEST_DEADLINE_SECONDS = get_env_int("BACKTEST_DEADLINE_SECONDS", 150)

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
