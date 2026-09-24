from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.services import queue

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("")
async def list_queue_route(limit: int = 50):
    return queue.list_jobs(limit)


# Declared before `/{item_id}` so "config" is not captured as a job id.
@router.get("/config")
async def queue_config_route():
    """Timing constants for the UI, so the frontend hard-codes no estimate."""
    return queue.config()


@router.get("/{item_id}")
async def queue_status_route(item_id: str):
    item = queue.status(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return item


@router.post("/{item_id}/cancel")
async def cancel_queue_route(item_id: str):
    """Ask a job to stop.

    A `queued` job is cancelled immediately; a `running` job stops at its next
    checkpoint. Cancelling a job that already finished is a no-op, so the
    endpoint is safe to call twice or from a stale UI.
    """
    item = queue.cancel(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return item