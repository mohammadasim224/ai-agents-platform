"""Conversation service.

Persists chat conversations and their messages, and runs generation jobs through
the background queue so long requests do not block the API. Each conversation is
scoped to a business profile so switching profiles shows the right history.
"""

from __future__ import annotations

from typing import Any

from backend.database.database import (
    add_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    list_messages,
    rename_conversation,
    touch_conversation,
)
from backend.services.queue import submit


def start_conversation(profile_id: str, title: str = "New conversation") -> dict[str, Any]:
    return create_conversation(profile_id or "default", title or "New conversation")


def list_for_profile(profile_id: str | None = None) -> list[dict[str, Any]]:
    return list_conversations(profile_id or None)


def get_messages(conversation_id: str) -> list[dict[str, Any]]:
    return list_messages(conversation_id)


def rename(conversation_id: str, title: str) -> dict[str, Any] | None:
    conversation = get_conversation(conversation_id)
    if not conversation:
        return None
    rename_conversation(conversation_id, title or conversation["title"])
    return get_conversation(conversation_id)


def remove(conversation_id: str) -> None:
    delete_conversation(conversation_id)


def send_message(
    conversation_id: str,
    content: str,
    *,
    profile_id: str = "default",
    attachment_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Record the user message and enqueue the generation job.

    Returns the queue item so the client can poll for the result.
    """
    conversation = get_conversation(conversation_id)
    if not conversation:
        conversation = create_conversation(profile_id, content[:60])
        conversation_id = conversation["id"]

    user_message = add_message(conversation_id, "user", content)
    touch_conversation(conversation_id)

    job = submit(
        "generate",
        {
            "conversation_id": conversation_id,
            "prompt": content,
            "profile_id": profile_id,
            "attachment_ids": attachment_ids or [],
        },
    )
    return {"conversation_id": conversation_id, "message": user_message, "job": job}


def record_assistant_message(conversation_id: str, content: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return add_message(conversation_id, "assistant", content, meta)