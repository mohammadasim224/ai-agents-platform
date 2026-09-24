"""Business profile service.

Profiles are the source of truth for a business: who they are, who they sell to,
what they offer, and how they want to sound. A profile can be converted into a
knowledge base (see `backend.services.knowledge_builder`) that the agents then
ground every deliverable in.
"""

from __future__ import annotations

from typing import Any

from backend.database.database import (
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    update_profile,
)


def create(data: dict[str, Any]) -> dict[str, Any]:
    return create_profile(data)


def list_all() -> list[dict[str, Any]]:
    return list_profiles()


def get(profile_id: str) -> dict[str, Any] | None:
    return get_profile(profile_id)


def update(profile_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    return update_profile(profile_id, data)


def remove(profile_id: str) -> None:
    delete_profile(profile_id)