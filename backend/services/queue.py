"""Background job queue.

Runs long jobs (generation, knowledge building) in a background thread so the
frontend can poll for status instead of blocking on a single request. The queue
is intentionally simple: one worker thread, jobs stored in SQLite, status
polled by the client.

Jobs are processed in FIFO order. A job that raises is marked `failed` with the
error message so the client can show an honest status. A job the user cancels is
marked `cancelled`: a `queued` job is stopped before it starts, and a `running`
job is stopped at its next checkpoint.
"""

from __future__ import annotations

import contextvars
import inspect
import threading
import time
from queue import Full, Queue
from typing import Any, Callable

from backend.config import PIPELINE_DEADLINE_SECONDS
from backend.database.database import (
    enqueue_item,
    finish_queue_item,
    get_queue_item,
    is_cancel_requested,
    list_queue_items,
    next_queued_item,
    reclaim_timed_out_items,
    request_cancel,
    requeue_stale_items,
    update_queue_item,
)
from backend.errors import JobCancelledError

HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {}
_worker: threading.Thread | None = None
_watchdog: threading.Thread | None = None
_stop = threading.Event()

# The job the current worker thread is running. Handlers report progress through
# `report_progress`, which needs to know which row to update without every
# handler having to thread an id through its own call stack.
_current_item: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "queue_current_item", default=None
)

# The job's activity log and progress snapshot live on the shared item dict, and
# the pipeline reports from several worker threads at once (concurrent
# departments and subtasks). A lock keeps the append/trim, the payload snapshot,
# and the progress write from interleaving.
_activity_lock = threading.Lock()

# Live listeners per job, used by the SSE endpoint to push progress instead of
# making the browser poll. Each subscriber gets its own bounded queue: a slow or
# abandoned reader fills its queue and is then skipped, so it can never stall the
# worker thread that is producing the updates.
_subscribers: dict[str, list[Queue]] = {}
_subscribers_lock = threading.Lock()

# Live listeners for the queue as a whole, used by the queue page and the
# sidebar badge. A per-job listener only hears about its own job; this one hears
# about every job, so a new job, a status change, or a progress write appears
# without the browser polling.
_feed_subscribers: list[Queue] = []
_feed_lock = threading.Lock()

# How many updates a single listener may fall behind before its queue is treated
# as full and further updates are dropped for it. Progress is a snapshot, not a
# log, so dropping intermediate frames is harmless: the next one supersedes it.
SUBSCRIBER_QUEUE_SIZE = 100

# A job that runs longer than this is considered hung and is failed so the
# single-worker queue can move on to the next job. The pipeline enforces its own
# wall-clock budget (`PIPELINE_DEADLINE_SECONDS`), so this is a safety net set
# slightly above it: a job that respects its budget is never reclaimed mid-run,
# while a genuinely hung job is cleared quickly instead of blocking the queue.
MAX_JOB_RUNTIME_SECONDS = PIPELINE_DEADLINE_SECONDS + 120
WATCHDOG_INTERVAL_SECONDS = 15

# Estimate used until a job is far enough along to project its own pace. The
# pipeline enforces `PIPELINE_DEADLINE_SECONDS`, so that is the honest ceiling
# to show for a job that has not started reporting meaningful progress yet.
DEFAULT_ESTIMATE_SECONDS = PIPELINE_DEADLINE_SECONDS

# How much weight a new projection carries when blended with the running one.
# The estimate is derived from `elapsed / percent`, which is noisy early on (a
# single slow provider call can double it), so it is smoothed to keep the
# displayed time remaining from jumping around. A low weight means the number
# converges steadily instead of flickering.
ETA_SMOOTHING = 0.3

# Below this percent the projection is meaningless: one slow first call would
# imply a wildly long job. Until then the default estimate is reported instead.
MIN_PERCENT_FOR_ETA = 5.0

# How many recent activity entries a job keeps. The activity log is a live
# commentary of what the pipeline is doing (which agent is working, what it is
# generating, what the checks found), so it is bounded: a long job must not grow
# the progress row without limit. The newest entries are kept.
MAX_ACTIVITY_ENTRIES = 60

# How much of a streamed generation to keep as a live preview. The preview is
# what the user watches appear while a specialist writes, so it is capped to the
# tail of the text: the beginning is already visible in the activity log, and an
# unbounded preview would bloat every progress write.
MAX_ACTIVITY_PREVIEW_CHARS = 600



def utc_now() -> str:
    """UTC timestamp matching SQLite's `CURRENT_TIMESTAMP` format.

    All queue timestamps must use the same clock. `CURRENT_TIMESTAMP` is UTC, so
    writing local time here would skew durations by the machine's UTC offset.
    """
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())


def register_handler(kind: str) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Decorator to register a job handler for a queue kind.

    A handler may accept a `report` keyword argument to publish progress. The
    worker inspects the signature and only passes it when the handler wants it,
    so simple handlers keep the plain `handler(payload)` shape.
    """

    def decorator(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        HANDLERS[kind] = fn
        return fn

    return decorator


def report_progress(
    stage: str,
    label: str,
    percent: float,
    *,
    detail: str = "",
) -> None:
    """Publish progress for the job running on this thread.

    Safe to call from anywhere inside a handler: when no job is running (for
    example a direct call in a test) it is a no-op. Progress is best-effort and
    never raises, because a failed progress write must not fail the job itself.

    The time remaining is derived from the job's own measured pace rather than
    guessed up front: `elapsed / percent` projects the total duration, and the
    difference from the elapsed time is what is actually left. The projection is
    smoothed across reports so the number converges instead of flickering.
    """
    item = _current_item.get()
    if not item:
        return
    clamped = max(0.0, min(100.0, round(float(percent), 1)))
    elapsed = _elapsed_seconds(item)
    projected_total, eta = _project_eta(item, clamped, elapsed)
    payload = {
        "stage": stage,
        "label": label,
        "percent": clamped,
        "detail": detail,
        # `estimate_seconds` is the projected total duration of the job, which
        # the UI uses to draw a time-based bar. `eta_seconds` is what is left.
        "estimate_seconds": round(projected_total),
        "eta_seconds": None if eta is None else round(eta),
        "elapsed_seconds": round(elapsed),
        "updated_at": utc_now(),
    }
    # Carry the live activity log forward. Progress is written as a whole JSON
    # blob, so the log has to be re-attached on every write or it would be lost.
    with _activity_lock:
        activity = item.get("_activity")
        if activity:
            payload["activity"] = list(activity)
        # Remember what was last written so `report_activity` can persist a new
        # log line without recomputing the timing (which would inflate the ETA).
        item["_last_payload"] = payload
    try:
        update_queue_item(item["id"], progress=payload)
    except Exception:  # noqa: BLE001 - progress must never break the job
        pass
    # Push the same snapshot to live listeners. Published after the write so a
    # listener that re-reads the row sees consistent data.
    _publish(item["id"], payload)


def report_activity(
    message: str,
    *,
    stage: str = "",
    agent: str = "",
    kind: str = "info",
    preview: str | None = None,
) -> None:
    """Append a live activity entry to the job running on this thread.

    This is the streaming channel for the pipeline: every meaningful step (an
    agent starting, a deliverable being generated, a check passing or failing)
    is appended here so the UI can show exactly what is happening while it
    happens, instead of only a percentage. Safe to call from any thread inside a
    handler and never raises: a failed activity write must not fail the job.

    `preview` carries the tail of a streamed generation so the user can watch
    the text appear. A streamed update does NOT append a new line: it rewrites
    the previous streaming entry for the same agent, so a long generation stays
    one growing line instead of flooding the log with dozens of identical
    "is writing..." entries that would push the meaningful steps out of view.

    The log lives on the job's in-memory item, so it reaches the UI on the next
    progress write rather than needing a write of its own.
    """
    item = _current_item.get()
    if not item:
        return
    text = " ".join(str(message or "").split())
    if not text and not preview:
        return
    entry: dict[str, Any] = {
        "at": utc_now(),
        "stage": stage,
        "agent": agent,
        "kind": kind,
        "message": text,
    }
    if preview:
        entry["preview"] = preview[-MAX_ACTIVITY_PREVIEW_CHARS:]
        entry["streaming"] = True
    with _activity_lock:
        log = item.setdefault("_activity", [])
        # A streamed update rewrites the open streaming entry for this agent
        # rather than appending, so the log stays readable.
        if preview and log and log[-1].get("streaming") and log[-1].get("agent") == agent:
            log[-1].update(entry)
        else:
            log.append(entry)
        if len(log) > MAX_ACTIVITY_ENTRIES:
            del log[: len(log) - MAX_ACTIVITY_ENTRIES]
        # A new log line must reach the UI before the next progress write, so the
        # last payload is re-published with the updated log attached. The percent
        # and timing are carried over unchanged, so the bar does not move and the
        # ETA is not re-projected (which would inflate it at a later elapsed time).
        payload = dict(item.get("_last_payload") or {})
        payload["activity"] = list(log)
        try:
            update_queue_item(item["id"], progress=payload)
        except Exception:  # noqa: BLE001 - activity must never break the job
            pass
        # A new activity line is exactly what the live view is waiting for, so it
        # is pushed immediately rather than waiting for the next progress write.
        _publish(item["id"], payload)


def _elapsed_seconds(item: dict[str, Any]) -> float:
    """Seconds since the worker started this job.

    Uses a monotonic clock captured when the job started, so a system clock
    change (or the UTC/local skew that bit the queue before) cannot produce a
    negative or wildly wrong elapsed time.
    """
    started = item.get("_started_monotonic")
    if started is None:
        return 0.0
    return max(0.0, time.monotonic() - started)


def _project_eta(
    item: dict[str, Any], percent: float, elapsed: float
) -> tuple[float, float | None]:
    """Project the job's total duration and the time remaining.

    Returns `(projected_total_seconds, eta_seconds)`. `eta_seconds` is None while
    the job is too early to project, which tells the UI to show the default
    estimate rather than a number derived from a single slow call.
    """
    if percent < MIN_PERCENT_FOR_ETA or elapsed <= 0:
        return float(DEFAULT_ESTIMATE_SECONDS), None

    # A job at 100% has nothing left to do; report that rather than dividing by
    # a percent that is already at the ceiling.
    if percent >= 99.5:
        item["_projected_total"] = elapsed
        return elapsed, 0.0

    projected = elapsed / (percent / 100.0)
    previous = item.get("_projected_total")
    if previous:
        projected = previous * (1 - ETA_SMOOTHING) + projected * ETA_SMOOTHING
    # Never project longer than the job is allowed to run: the pipeline stops
    # itself at its budget, so a larger number would be a lie.
    projected = max(1.0, min(projected, float(MAX_JOB_RUNTIME_SECONDS)))
    item["_projected_total"] = projected
    return projected, max(0.0, projected - elapsed)


def _handler_accepts(handler: Callable[..., dict[str, Any]], name: str) -> bool:
    """Whether a handler wants the optional keyword argument `name`.

    Handlers stay simple: one that does not declare `report` or `cancel_check`
    keeps the plain `handler(payload)` shape and is called without them.
    """
    try:
        parameters = inspect.signature(handler).parameters
    except (TypeError, ValueError):
        return False
    if name in parameters:
        return True
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def submit(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Enqueue a job and make sure the worker is running."""
    item = enqueue_item(kind, payload)
    _ensure_worker()
    # Announce the new job so a queue page that is already open shows it without
    # waiting for the next poll.
    if _feed_subscribers:
        _publish_feed(item)
    return item


def status(item_id: str) -> dict[str, Any] | None:
    return get_queue_item(item_id)


def subscribe(item_id: str) -> Queue:
    """Register a live listener for a job's progress.

    Returns a bounded queue that receives a snapshot on every progress write.
    The caller must pair this with `unsubscribe` (a `finally` block) or the
    registry would grow for the lifetime of the process.
    """
    channel: Queue = Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
    with _subscribers_lock:
        _subscribers.setdefault(item_id, []).append(channel)
    return channel


def unsubscribe(item_id: str, channel: Queue) -> None:
    """Remove a listener registered with `subscribe`."""
    with _subscribers_lock:
        channels = _subscribers.get(item_id)
        if not channels:
            return
        if channel in channels:
            channels.remove(channel)
        if not channels:
            _subscribers.pop(item_id, None)


def _publish(item_id: str, payload: dict[str, Any]) -> None:
    """Fan a job snapshot out to live listeners.

    Best-effort and non-blocking: a listener whose queue is full is skipped
    rather than waited on, because the worker thread must never be held up by a
    slow reader. Progress is a snapshot, so a dropped frame is superseded by the
    next one.

    Two shapes reach here: a full job row (from `_publish_current`, carrying
    `status` and `result`) and a bare progress blob (from `report_progress` and
    `report_activity`). The blob is wrapped into the row shape so every frame a
    client receives has the same `{id, status, progress}` fields, which is what
    lets the UI treat a live update and a fetched row identically.
    """
    if "status" not in payload:
        payload = {"id": item_id, "status": "running", "progress": payload}
    with _subscribers_lock:
        channels = list(_subscribers.get(item_id, ()))
    for channel in channels:
        try:
            channel.put_nowait(payload)
        except Full:
            pass
    # The queue-wide feed hears about every job, so the queue page and the badge
    # update live. The payload is tagged with its job id because a feed listener
    # is watching many jobs at once.
    if _feed_subscribers:
        _publish_feed({**payload, "id": payload.get("id") or item_id})


def _publish_current(item_id: str) -> None:
    """Publish the job's stored row, used for terminal states.

    The progress writes carry only the progress blob, so the final frame is read
    back from the database to include the status and result the client needs to
    finish. A missing row is ignored: the job may have been reclaimed.
    """
    item = get_queue_item(item_id)
    if item:
        _publish(item_id, item)


def subscribe_feed() -> Queue:
    """Register a listener for every job's updates.

    This is the queue-wide counterpart to `subscribe`: the queue page and the
    sidebar badge use it to stay live without polling. The caller must pair it
    with `unsubscribe_feed` (a `finally` block) or the registry would grow for
    the lifetime of the process.
    """
    channel: Queue = Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
    with _feed_lock:
        _feed_subscribers.append(channel)
    return channel


def unsubscribe_feed(channel: Queue) -> None:
    """Remove a listener registered with `subscribe_feed`."""
    with _feed_lock:
        if channel in _feed_subscribers:
            _feed_subscribers.remove(channel)


def _publish_feed(payload: dict[str, Any]) -> None:
    """Fan a job snapshot out to every queue-wide listener.

    Best-effort and non-blocking, exactly like `_publish`: a listener whose
    queue is full is skipped rather than waited on, because the worker thread
    must never be held up by a slow reader.
    """
    with _feed_lock:
        channels = list(_feed_subscribers)
    for channel in channels:
        try:
            channel.put_nowait(payload)
        except Full:
            pass


def config() -> dict[str, Any]:
    """The queue's timing constants, so the UI needs no hard-coded numbers."""
    return {
        "default_estimate_seconds": DEFAULT_ESTIMATE_SECONDS,
        "max_runtime_seconds": MAX_JOB_RUNTIME_SECONDS,
        "min_percent_for_eta": MIN_PERCENT_FOR_ETA,
    }


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    return list_queue_items(limit)


def cancel(item_id: str) -> dict[str, Any] | None:
    """Ask a job to stop, returning its updated row (or None if unknown).

    A `queued` job is cancelled immediately. A `running` job is flagged and the
    worker stops it at its next checkpoint, because a provider call already in
    flight cannot be aborted safely from another thread.
    """
    item = request_cancel(item_id)
    # A queued job is cancelled outright, so its new status must reach the live
    # feed immediately; a running job is only flagged, and its next progress
    # write carries the flag.
    if item and _feed_subscribers:
        _publish_feed(item)
    return item


def _ensure_worker() -> None:
    global _worker, _watchdog
    if _worker is not None and _worker.is_alive():
        return
    # Recover jobs left `running` by a previous crash or restart before the
    # worker starts, so they are picked up again instead of hanging forever.
    requeue_stale_items()
    _stop.clear()
    _worker = threading.Thread(target=_run_worker, name="queue-worker", daemon=True)
    _worker.start()

    if _watchdog is None or not _watchdog.is_alive():
        _watchdog = threading.Thread(target=_run_watchdog, name="queue-watchdog", daemon=True)
        _watchdog.start()


def start_worker() -> None:
    """Start the queue worker and watchdog.

    Called at server startup so jobs left `queued` by a restart are picked up
    immediately, instead of waiting for someone to submit a new job (which is the
    only thing that used to start the worker). Idempotent: calling it when the
    worker is already running is a no-op.
    """
    _ensure_worker()


def _run_worker() -> None:
    while not _stop.is_set():
        try:
            item = _next_queued()
            if item is None:
                _stop.wait(0.5)
                continue
            _process(item)
        except Exception:  # noqa: BLE001 - the worker must never die
            # The queue has a single worker, so an exception escaping `_process`
            # (a database fault while writing the terminal status, say) would
            # kill the thread and silently stall every future job. Swallow it and
            # keep serving the queue; the job itself is left for the watchdog.
            _stop.wait(0.5)


def _run_watchdog() -> None:
    """Fail hung jobs so a single stuck request cannot stall the whole queue."""
    while not _stop.is_set():
        try:
            reclaim_timed_out_items(MAX_JOB_RUNTIME_SECONDS)
        except Exception:  # noqa: BLE001 - the watchdog must never die
            pass
        _stop.wait(WATCHDOG_INTERVAL_SECONDS)


def _next_queued() -> dict[str, Any] | None:
    return next_queued_item()


def _finish(item: dict[str, Any], started_at: str, **fields: Any) -> None:
    """Complete a job and push the terminal row to live listeners.

    Every exit path from `_process` goes through here so the SSE stream always
    receives a final frame carrying the status and result, which is what lets the
    client close the connection instead of waiting for a timeout.
    """
    finish_queue_item(item["id"], started_at, **fields)
    _publish_current(item["id"])


def _process(item: dict[str, Any]) -> None:
    handler = HANDLERS.get(item["kind"])
    started_at = utc_now()
    # The contextvar holds this same dict, so recording the monotonic start here
    # is what lets `report_progress` measure the job's real pace.
    item["_started_monotonic"] = time.monotonic()
    update_queue_item(item["id"], status="running", started_at=started_at)

    if handler is None:
        _finish(
            item,
            started_at,
            status="failed",
            error=f"No handler registered for queue kind '{item['kind']}'.",
        )
        return

    # The user may have cancelled between the job being picked and this point.
    # Honour it before spending any provider calls on work nobody wants.
    if is_cancel_requested(item["id"]):
        _finish(
            item,
            started_at,
            status="cancelled",
            error="Cancelled by the user before it started.",
        )
        return

    token = _current_item.set(item)
    try:
        report_progress("starting", "Starting the request", 2)
        report_activity("Job accepted by the worker.", stage="starting", kind="info")
        kwargs: dict[str, Any] = {}
        if _handler_accepts(handler, "report"):
            kwargs["report"] = report_progress
        if _handler_accepts(handler, "activity"):
            kwargs["activity"] = report_activity
        if _handler_accepts(handler, "cancel_check"):
            kwargs["cancel_check"] = lambda: is_cancel_requested(item["id"])
        result = handler(item["payload"], **kwargs)
    except JobCancelledError:
        # Cancellation is the requested outcome, not a failure, so it is
        # recorded as `cancelled` rather than `failed`.
        _finish(
            item,
            started_at,
            status="cancelled",
            error="Cancelled by the user.",
        )
        return
    except Exception as exc:  # noqa: BLE001 - job failures are reported, not fatal
        _finish(item, started_at, status="failed", error=str(exc))
        return
    finally:
        _current_item.reset(token)

    # A cancel that arrived while the handler was finishing still wins: the user
    # asked for the work to stop, so the result is discarded rather than shown.
    if is_cancel_requested(item["id"]):
        _finish(
            item,
            started_at,
            status="cancelled",
            error="Cancelled by the user.",
        )
        return

    # `finish_queue_item` is a no-op when the watchdog already failed this job
    # for exceeding its runtime, which prevents a late result from resurrecting it.
    _finish(item, started_at, status="done", result=result)


def shutdown() -> None:
    _stop.set()