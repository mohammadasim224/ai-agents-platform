"""Memory service.

Persistent facts the user wants every agent run to remember. Memory items are
scoped to a business profile and injected into the orchestrator's business
context so the whole chain of command is grounded in them.
"""

from __future__ import annotations

from typing import Any

from backend.database.database import (
    add_memory,
    delete_memory,
    list_memory,
)


def add(profile_id: str, content: str, category: str = "general", source: str = "manual") -> dict[str, Any]:
    content = (content or "").strip()
    if not content:
        raise ValueError("Memory content cannot be empty.")
    return add_memory(profile_id or "default", content, category, source)


def list_for_profile(profile_id: str | None = None) -> list[dict[str, Any]]:
    return list_memory(profile_id or None)


def remove(memory_id: str) -> None:
    delete_memory(memory_id)


def render_memory_block(profile_id: str | None = None, max_chars: int = 4000) -> str:
    """Render the memory items as a prompt block for the orchestrator."""
    items = list_memory(profile_id or None)
    if not items:
        return ""
    lines = [f"- {item['content']}" for item in items]
    block = "## Persistent Business Memory\n\n" + "\n".join(lines)
    return block[:max_chars]