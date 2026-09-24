from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.services import conversations

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations_route(profile_id: str | None = None):
    return conversations.list_for_profile(profile_id)


@router.post("")
async def create_conversation_route(payload: dict):
    return conversations.start_conversation(
        payload.get("profile_id", "default"),
        payload.get("title", "New conversation"),
    )


@router.get("/{conversation_id}")
async def get_conversation_route(conversation_id: str):
    messages = conversations.get_messages(conversation_id)
    return {"id": conversation_id, "messages": messages}


@router.post("/{conversation_id}/messages")
async def send_message_route(conversation_id: str, payload: dict):
    content = str(payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message content cannot be empty")
    return conversations.send_message(
        conversation_id,
        content,
        profile_id=payload.get("profile_id", "default"),
        attachment_ids=payload.get("attachment_ids") or [],
    )


@router.patch("/{conversation_id}")
async def rename_conversation_route(conversation_id: str, payload: dict):
    conversation = conversations.rename(conversation_id, payload.get("title", ""))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/{conversation_id}")
async def delete_conversation_route(conversation_id: str):
    conversations.remove(conversation_id)
    return {"status": "ok"}