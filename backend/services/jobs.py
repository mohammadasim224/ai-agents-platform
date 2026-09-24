"""Queue job handlers.

Registers the concrete jobs the queue can run. Importing this module wires the
handlers into the queue registry; `backend.main` imports it at startup.
"""

from __future__ import annotations

from typing import Any, Callable

from backend.database.database import get_profile
from backend.orchestrator import run_pipeline
from backend.services import conversations
from backend.services.knowledge_builder import build_knowledge_base_ai
from backend.services.memory import render_memory_block
from backend.services.queue import register_handler

ProgressReporter = Callable[..., None]
CancelCheck = Callable[[], bool]
ActivityReporter = Callable[..., None]


@register_handler("generate")
def handle_generate(
    payload: dict[str, Any],
    report: ProgressReporter | None = None,
    cancel_check: CancelCheck | None = None,
    activity: ActivityReporter | None = None,
) -> dict[str, Any]:
    """Run the chain of command and record the assistant message."""
    prompt = str(payload.get("prompt") or "").strip()
    conversation_id = payload.get("conversation_id")
    profile_id = payload.get("profile_id", "default")
    attachment_ids = payload.get("attachment_ids") or []

    memory_block = render_memory_block(profile_id)
    if memory_block:
        prompt = f"{prompt}\n\n{memory_block}"

    result = run_pipeline(
        prompt,
        project_id=profile_id,
        attachment_ids=attachment_ids,
        progress=report,
        cancel_check=cancel_check,
        activity=activity,
    )
    body = result.to_dict()

    if conversation_id:
        conversations.record_assistant_message(
            conversation_id,
            body.get("output") or body.get("message") or "",
            meta={
                "status": body.get("status"),
                "departments": body.get("departments"),
                "artifacts": body.get("artifacts"),
                "error": body.get("error"),
                "knowledge_used": body.get("knowledge_used"),
            },
        )

    return body


@register_handler("build-knowledge")
def handle_build_knowledge(payload: dict[str, Any], report: ProgressReporter | None = None) -> dict[str, Any]:
    """Convert a profile into a knowledge base in the background."""
    profile = get_profile(payload.get("profile_id", ""))
    if not profile:
        raise ValueError("Profile not found")
    if report:
        report("build-knowledge", "Expanding your profile into knowledge files", 35)
    result = build_knowledge_base_ai(profile)
    if report:
        report("build-knowledge", "Knowledge base built", 100)
    return result