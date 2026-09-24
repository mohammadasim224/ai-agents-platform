"""Tests for job cancellation and dynamic time-remaining estimates.

Two behaviours are covered here:

1. **Cancellation.** A user must be able to stop a job. A `queued` job is
   cancelled before it starts; a `running` job is stopped at its next
   checkpoint, because a provider call already in flight cannot be aborted
   safely from another thread. Cancelling is a deliberate action, so it is
   recorded as `cancelled` rather than `failed`.

2. **Dynamic ETAs.** The time remaining must be derived from the job's own
   measured pace (`elapsed / percent`) instead of a number guessed before the
   job started, so it reflects how long the work is actually taking.
"""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from backend.database import database
from backend.errors import JobCancelledError
from backend.main import app
from backend.services import queue


client = TestClient(app)


def _wait_for_status(item_id: str, statuses: set[str], timeout: float = 10.0) -> dict:
    """Poll a job until it reaches one of `statuses`, then return its row."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        item = database.get_queue_item(item_id)
        if item and item["status"] in statuses:
            return item
        time.sleep(0.05)
    raise AssertionError(
        f"job {item_id} never reached {statuses}; last status was "
        f"{database.get_queue_item(item_id)['status']}"
    )


# --------------------------------------------------------------- cancellation


def test_queued_job_is_cancelled_before_it_starts():
    """A job cancelled while queued must never run its handler."""
    ran = threading.Event()

    def handler(payload):
        ran.set()
        return {"ok": True}

    queue.HANDLERS["cancel-queued-test"] = handler
    try:
        # Block the single worker so the second job stays queued.
        release = threading.Event()

        def blocker(payload):
            release.wait(timeout=10)
            return {"ok": True}

        queue.HANDLERS["cancel-blocker-test"] = blocker
        queue.submit("cancel-blocker-test", {})
        time.sleep(0.3)

        item = queue.submit("cancel-queued-test", {})
        cancelled = queue.cancel(item["id"])
        assert cancelled["status"] == "cancelled"
        assert cancelled["cancel_requested"] is True

        release.set()
        time.sleep(0.5)
        assert not ran.is_set(), "a cancelled queued job still ran"
        assert database.get_queue_item(item["id"])["status"] == "cancelled"
    finally:
        queue.HANDLERS.pop("cancel-queued-test", None)
        queue.HANDLERS.pop("cancel-blocker-test", None)


def test_running_job_is_cancelled_at_its_next_checkpoint():
    """A running job that honours `cancel_check` is recorded as cancelled."""
    started = threading.Event()

    def handler(payload, cancel_check=None):
        started.set()
        # Stand in for the pipeline's stage checkpoints.
        deadline = time.time() + 10
        while time.time() < deadline:
            if cancel_check and cancel_check():
                raise JobCancelledError("The user cancelled this request.", stage="cancelled")
            time.sleep(0.05)
        return {"ok": True}

    queue.HANDLERS["cancel-running-test"] = handler
    try:
        item = queue.submit("cancel-running-test", {})
        assert started.wait(timeout=10), "the worker never started the job"
        queue.cancel(item["id"])
        stored = _wait_for_status(item["id"], {"cancelled"})
        assert stored["status"] == "cancelled"
        assert "cancel" in stored["error"].lower()
    finally:
        queue.HANDLERS.pop("cancel-running-test", None)


def test_cancelling_a_finished_job_is_a_noop():
    """Cancelling a job that already finished must not rewrite its outcome."""
    done = threading.Event()

    def handler(payload):
        done.set()
        return {"ok": True}

    queue.HANDLERS["cancel-done-test"] = handler
    try:
        item = queue.submit("cancel-done-test", {})
        assert done.wait(timeout=10)
        _wait_for_status(item["id"], {"done"})
        result = queue.cancel(item["id"])
        assert result["status"] == "done"
    finally:
        queue.HANDLERS.pop("cancel-done-test", None)


def test_cancel_unknown_job_returns_none():
    assert queue.cancel("does-not-exist") is None


def test_cancel_endpoint_reports_404_for_unknown_job():
    response = client.post("/queue/does-not-exist/cancel")
    assert response.status_code == 404


def test_cancel_endpoint_cancels_a_queued_job():
    release = threading.Event()

    def blocker(payload):
        release.wait(timeout=10)
        return {"ok": True}

    queue.HANDLERS["cancel-api-blocker"] = blocker
    try:
        queue.submit("cancel-api-blocker", {})
        time.sleep(0.3)
        item = database.enqueue_item("cancel-api-target", {})
        response = client.post(f"/queue/{item['id']}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
    finally:
        release.set()
        queue.HANDLERS.pop("cancel-api-blocker", None)


def test_stale_cancelled_job_is_not_requeued_on_startup():
    """A job cancelled before a restart must not be run again."""
    item = database.enqueue_item("stale-cancel-test", {})
    database.update_queue_item(item["id"], status="running", started_at=queue.utc_now())
    database.request_cancel(item["id"])

    database.requeue_stale_items()

    stored = database.get_queue_item(item["id"])
    assert stored["status"] == "cancelled"


def test_cancelled_jobs_are_skipped_by_the_worker():
    """A cancel that raced with the worker must not start the job anyway."""
    item = database.enqueue_item("skip-cancelled-test", {})
    database.request_cancel(item["id"])
    # The row is `cancelled`, so the worker's FIFO pick must not return it.
    assert database.next_queued_item() is None or database.next_queued_item()["id"] != item["id"]


def test_watchdog_reports_a_cancelled_job_as_cancelled_not_failed():
    """A cancelled job that also times out must not be reported as a failure."""
    item = database.enqueue_item("watchdog-cancel-test", {})
    database.update_queue_item(item["id"], status="running", started_at="2000-01-01 00:00:00")
    database.request_cancel(item["id"])

    database.reclaim_timed_out_items(1)

    stored = database.get_queue_item(item["id"])
    assert stored["status"] == "cancelled"
    assert "cancel" in stored["error"].lower()


# ------------------------------------------------------------------ dynamic ETA


def test_eta_is_projected_from_the_jobs_measured_pace():
    """The reported time remaining must shrink as the job actually progresses."""
    captured: list[dict] = []
    holder: dict[str, str] = {}
    ready = threading.Event()

    def handler(payload, report=None):
        # Wait until the test knows this job's id, so the handler can read back
        # the progress the queue stored for it.
        ready.wait(timeout=10)
        # 10% after ~0.2s implies a ~2s total, so the ETA must be well under the
        # static default rather than the pre-computed guess.
        time.sleep(0.2)
        report("triage", "Routing", 10)
        captured.append(database.get_queue_item(holder["id"])["progress"])
        time.sleep(0.2)
        report("plan", "Planning", 50)
        captured.append(database.get_queue_item(holder["id"])["progress"])
        return {"ok": True}

    queue.HANDLERS["eta-test"] = handler
    try:
        item = queue.submit("eta-test", {})
        holder["id"] = item["id"]
        ready.set()
        _wait_for_status(item["id"], {"done"})

        assert len(captured) == 2, "the handler did not report progress"
        first, second = captured
        assert first["eta_seconds"] is not None
        assert second["eta_seconds"] is not None
        # The job is further along, so less time must remain.
        assert second["eta_seconds"] < first["eta_seconds"]
        # The projection is the job's own pace, not the static default.
        assert first["estimate_seconds"] < queue.DEFAULT_ESTIMATE_SECONDS
    finally:
        queue.HANDLERS.pop("eta-test", None)


def test_eta_is_absent_until_the_job_is_far_enough_along():
    """Early progress must not project a wild ETA from one slow call."""
    captured: list[dict] = []
    holder: dict[str, str] = {}
    ready = threading.Event()

    def handler(payload, report=None):
        ready.wait(timeout=10)
        report("starting", "Starting", 2)
        captured.append(database.get_queue_item(holder["id"])["progress"])
        return {"ok": True}

    queue.HANDLERS["eta-early-test"] = handler
    try:
        item = queue.submit("eta-early-test", {})
        holder["id"] = item["id"]
        ready.set()
        _wait_for_status(item["id"], {"done"})
        assert captured[0]["eta_seconds"] is None
        assert captured[0]["estimate_seconds"] == queue.DEFAULT_ESTIMATE_SECONDS
    finally:
        queue.HANDLERS.pop("eta-early-test", None)


def test_eta_never_exceeds_the_job_runtime_budget():
    """A projection larger than the enforced budget would be a lie."""
    # 5% after 1000s implies a ~5.5 hour job, far beyond the enforced budget.
    item = {"id": "eta-budget-test", "_started_monotonic": time.monotonic() - 1000}
    projected, eta = queue._project_eta(item, 5.1, 1000.0)
    assert projected <= queue.MAX_JOB_RUNTIME_SECONDS
    assert eta is not None and eta >= 0


def test_eta_is_smoothed_so_it_does_not_flicker():
    """A single noisy report must not swing the projection wildly."""
    item = {"id": "eta-smooth-test", "_started_monotonic": time.monotonic() - 10}
    first, _ = queue._project_eta(item, 20.0, 10.0)
    # A sudden jump in percent would imply a much shorter job; smoothing must
    # keep the new projection close to the previous one.
    second, _ = queue._project_eta(item, 60.0, 10.0)
    assert second < first
    assert second > first * 0.5


def test_progress_reports_elapsed_seconds():
    """The UI shows elapsed time, so it must be reported with each update."""
    captured: list[dict] = []
    holder: dict[str, str] = {}
    ready = threading.Event()

    def handler(payload, report=None):
        ready.wait(timeout=10)
        time.sleep(0.15)
        report("triage", "Routing", 10)
        captured.append(database.get_queue_item(holder["id"])["progress"])
        return {"ok": True}

    queue.HANDLERS["elapsed-test"] = handler
    try:
        item = queue.submit("elapsed-test", {})
        holder["id"] = item["id"]
        ready.set()
        _wait_for_status(item["id"], {"done"})
        assert captured[0]["elapsed_seconds"] >= 0
    finally:
        queue.HANDLERS.pop("elapsed-test", None)


# ------------------------------------------------------- default estimate


def test_the_default_estimate_is_used_before_projection():
    """A job that has barely started must show the default, not a wild guess."""
    assert queue.config()["default_estimate_seconds"] == queue.DEFAULT_ESTIMATE_SECONDS
    _, eta = queue._project_eta({}, queue.MIN_PERCENT_FOR_ETA - 1, 10.0)
    assert eta is None


def test_the_default_estimate_is_the_pipeline_budget():
    """The estimate a job is measured against is the budget it is allowed."""
    from backend.config import PIPELINE_DEADLINE_SECONDS

    assert queue.DEFAULT_ESTIMATE_SECONDS == PIPELINE_DEADLINE_SECONDS


def test_projection_is_clamped_inside_the_honest_range():
    """An estimate outside the enforced runtime would be a lie."""
    item: dict = {}
    projected, _ = queue._project_eta(item, 5.1, 10_000.0)
    assert projected <= queue.MAX_JOB_RUNTIME_SECONDS
    # A projection that rounds down to zero is unusable, so it never goes below 1.
    assert queue._project_eta({}, 100.0, 0.0)[0] >= 1.0


def test_queue_config_endpoint_exposes_the_timing_constants():
    """The UI reads its estimate from the backend instead of hard-coding one."""
    response = client.get("/queue/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default_estimate_seconds"] == queue.DEFAULT_ESTIMATE_SECONDS
    assert payload["max_runtime_seconds"] == queue.MAX_JOB_RUNTIME_SECONDS
    assert payload["min_percent_for_eta"] == queue.MIN_PERCENT_FOR_ETA



# ------------------------------------------------------- orchestrator cancel


def test_orchestrator_stops_when_cancelled():
    """The pipeline must raise JobCancelledError at its first checkpoint."""
    from backend.orchestrator import Orchestrator

    orchestrator = Orchestrator("cancel-test", cancel_check=lambda: True)
    try:
        orchestrator.run("Write an ad for my business")
    except JobCancelledError:
        return
    raise AssertionError("a cancelled pipeline did not stop")


def test_orchestrator_runs_when_not_cancelled():
    """A pipeline that is not cancelled must not raise JobCancelledError."""
    from backend.orchestrator import Orchestrator

    orchestrator = Orchestrator("cancel-test", cancel_check=lambda: False)
    # The provider is stubbed offline in tests, so the pipeline reports an
    # honest error result rather than raising a cancellation.
    result = orchestrator.run("Write an ad for my business")
    assert result.status in {"ok", "error"}


def test_broken_cancel_check_does_not_break_the_pipeline():
    """A cancel check that raises must be treated as 'not cancelled'."""
    from backend.orchestrator import Orchestrator

    def explode():
        raise RuntimeError("cancel check is down")

    orchestrator = Orchestrator("cancel-test", cancel_check=explode)
    result = orchestrator.run("Write an ad for my business")
    assert result.status in {"ok", "error"}