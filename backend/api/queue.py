from __future__ import annotations

import asyncio
import json
from queue import Empty

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.services import queue

router = APIRouter(prefix="/queue", tags=["queue"])

# Terminal statuses. The stream sends one final frame and then closes, so the
# client does not have to poll to learn the job finished.
TERMINAL_STATUSES = {"done", "failed", "cancelled"}

# How long the stream waits for an update before emitting a keep-alive comment.
# A comment frame is ignored by `EventSource` but keeps proxies and load
# balancers from closing a connection that is merely idle between reports.
STREAM_IDLE_SECONDS = 15.0


@router.get("")
async def list_queue_route(limit: int = 50):
    return queue.list_jobs(limit)


# Declared before `/{item_id}` so "config" is not captured as a job id.
@router.get("/config")
async def queue_config_route():
    """Timing constants for the UI, so the frontend hard-codes no estimate."""
    return queue.config()


@router.get("/events")
async def queue_feed_route():
    """Stream every job's updates as Server-Sent Events.

    This is the queue-wide counterpart to `GET /queue/{item_id}/events`: the
    queue page and the sidebar badge listen here instead of polling, so a new
    job, a status change, or a progress write appears as it happens. Each frame
    is a job snapshot tagged with its `id`, because one listener is watching
    many jobs at once.

    Unlike the per-job stream this one never closes on its own: the queue has no
    terminal state, so the client keeps listening for as long as the page is
    open and the connection is dropped when it navigates away.
    """
    async def event_stream():
        channel = queue.subscribe_feed()
        try:
            # Send the current rows first so a client that connects mid-job is
            # never blank, then forward each update as it is published.
            for item in queue.list_jobs():
                yield _sse(item)
            while True:
                try:
                    # `q.get` blocks, so it runs off the event loop; otherwise a
                    # single idle stream would freeze every other request.
                    payload = await asyncio.to_thread(
                        channel.get, True, STREAM_IDLE_SECONDS
                    )
                except Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(payload)
        finally:
            queue.unsubscribe_feed(channel)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tells nginx not to buffer the stream, which would defeat the point.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{item_id}")
async def queue_status_route(item_id: str):
    item = queue.status(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    return item


@router.get("/{item_id}/events")
async def queue_events_route(item_id: str):
    """Stream a job's progress as Server-Sent Events.

    This is the push counterpart to `GET /queue/{item_id}`: instead of the
    browser polling every couple of seconds, each progress write is forwarded as
    it happens, so the activity feed and the streamed preview update live.

    The current row is sent first so a client that connects mid-job is never
    blank, and the stream closes after the terminal frame so the client can stop
    listening without a timeout.
    """
    if not queue.status(item_id):
        raise HTTPException(status_code=404, detail="Queue item not found")

    async def event_stream():
        channel = queue.subscribe(item_id)
        try:
            current = queue.status(item_id)
            if current:
                yield _sse(current)
                if current.get("status") in TERMINAL_STATUSES:
                    return
            while True:
                try:
                    # `q.get` blocks, so it runs off the event loop; otherwise a
                    # single idle stream would freeze every other request.
                    payload = await asyncio.to_thread(
                        channel.get, True, STREAM_IDLE_SECONDS
                    )
                except Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(payload)
                if payload.get("status") in TERMINAL_STATUSES:
                    return
        finally:
            queue.unsubscribe(item_id, channel)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tells nginx not to buffer the stream, which would defeat the point.
            "X-Accel-Buffering": "no",
        },
    )


def _sse(payload: dict) -> str:
    """Format one Server-Sent Events data frame."""
    return f"data: {json.dumps(payload)}\n\n"


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