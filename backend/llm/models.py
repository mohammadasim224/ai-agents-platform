"""Model selection per role.

Roles follow the chain of command. `manager` covers the top-level manager,
`marketing`/`sales`/`automation` cover department heads and their specialists,
and `evaluation` covers the lead simulator, scoring, and verification agents.
"""

from __future__ import annotations

import os

from backend.config import DEFAULT_MODEL

MODEL_MAP = {
    "manager": DEFAULT_MODEL,
    "marketing": DEFAULT_MODEL,
    "sales": DEFAULT_MODEL,
    "automation": DEFAULT_MODEL,
    "evaluation": DEFAULT_MODEL,
}


def get_model_for(role: str) -> str:
    """Resolve the model for a role, allowing per-role environment overrides."""
    env_key = f"{role.upper()}_MODEL"
    value = os.getenv(env_key)
    if value:
        return value

    return MODEL_MAP.get(role, DEFAULT_MODEL)
