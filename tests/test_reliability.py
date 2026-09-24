"""Regression tests for reliability bugs found during debugging.

Each test here pins a specific failure that was observed in the running system:

1. A transient DNS failure produced a raw, unhelpful error and retried poorly.
2. A hung job blocked the single-worker queue, so every later job stayed
   `queued` forever.
3. Queue timestamps mixed UTC (`created_at`) with local time (`started_at`),
   which skewed durations by the machine's UTC offset.
4. The test suite wrote into the real `data/` database.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import requests

from backend.database import database
from backend.errors import ProviderError
from backend.llm import router
from backend.services import queue


# --------------------------------------------------------------------- provider


def _dns_error() -> requests.exceptions.ConnectionError:
    """Build the exact error shape requests raises on a DNS failure."""
    exc = requests.exceptions.ConnectionError(
        "HTTPSConnectionPool(host='openrouter.ai', port=443): Max retries exceeded "
        "(Caused by NameResolutionError(\"Failed to resolve 'openrouter.ai'\"))"
    )
    try:
        socket.getaddrinfo("this-host-does-not-exist-xyz.invalid", 443)
    except socket.gaierror as cause:
        exc.__cause__ = cause
    return exc


def test_dns_failure_is_detected_through_the_exception_chain():
    assert router._is_dns_failure(_dns_error())


def test_dns_failure_produces_an_actionable_error():
    """The user must get a real explanation, not a raw urllib3 string."""
    error = router._network_error(_dns_error(), "some/model", 1)
    assert isinstance(error, ProviderError)
    assert "resolve" in error.message.lower()
    assert error.user_hint  # an error without a hint is not actionable
    assert error.details["model"] == "some/model"


def test_backoff_grows_and_is_capped():
    """Backoff must grow exponentially but never stall a request indefinitely."""
    delays = [router._backoff_seconds(attempt) for attempt in range(1, 9)]
    assert delays[1] > delays[0]  # growth
    assert all(delay <= router.MAX_BACKOFF_SECONDS * 1.25 for delay in delays)  # capped


def test_timeout_is_reported_as_a_timeout():
    error = router._network_error(requests.exceptions.Timeout("too slow"), "m", 2)
    assert "did not respond" in error.message


def test_provider_health_reports_dns_and_reachability():
    health = router.check_provider_health(timeout=0.001)
    assert health["dns_ok"] is True  # openrouter.ai resolves in this environment
    assert "api_key_configured" in health
    assert "host" in health


def test_provider_health_never_raises_on_a_bad_host(monkeypatch):
    """A broken base URL must be reported as data, not as an exception."""
    monkeypatch.setattr(router, "OPENROUTER_BASE_URL", "https://nope.invalid/api/v1")
    health = router.check_provider_health(timeout=0.5)
    assert health["dns_ok"] is False
    assert health["error"]


def test_health_endpoint_stays_cheap_and_provider_endpoint_reports_status():
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}

    provider = client.get("/health/provider")
    assert provider.status_code == 200
    body = provider.json()
    assert body["status"] in {"ok", "degraded"}
    assert "provider" in body


# ------------------------------------------------------------------------ queue


def test_queue_is_fifo_even_with_identical_timestamps():
    """Several jobs can share a second-level timestamp; order must still hold."""
    ids = [database.enqueue_item("fifo-test", {"n": n})["id"] for n in range(3)]
    assert database.next_queued_item()["id"] == ids[0]
    assert [item["id"] for item in database.list_queue_items(3)] == ids[::-1]


def test_stale_running_jobs_are_requeued_on_startup():
    """A job left `running` by a crash must not hang forever."""
    item = database.enqueue_item("stale-test", {})
    database.update_queue_item(item["id"], status="running", started_at=queue.utc_now())

    assert database.requeue_stale_items() >= 1
    assert database.get_queue_item(item["id"])["status"] == "queued"


def test_timed_out_jobs_are_reclaimed_so_the_queue_can_continue():
    """A hung job must be failed, otherwise it blocks every later job."""
    item = database.enqueue_item("hang-test", {})
    # Pretend the job started long ago and has been running ever since.
    database.update_queue_item(item["id"], status="running", started_at="2000-01-01 00:00:00")

    reclaimed = database.reclaim_timed_out_items(max_runtime_seconds=60)
    assert item["id"] in reclaimed
    stored = database.get_queue_item(item["id"])
    assert stored["status"] == "failed"
    assert "maximum runtime" in stored["error"]


def test_healthy_running_job_is_not_reclaimed():
    item = database.enqueue_item("healthy-test", {})
    database.update_queue_item(item["id"], status="running", started_at=queue.utc_now())

    assert database.reclaim_timed_out_items(max_runtime_seconds=3600) == []
    assert database.get_queue_item(item["id"])["status"] == "running"


def test_finish_only_completes_the_job_the_worker_owns():
    """A late result must not resurrect a job the watchdog already failed."""
    item = database.enqueue_item("owner-test", {})
    started_at = queue.utc_now()
    database.update_queue_item(item["id"], status="running", started_at=started_at)

    assert database.finish_queue_item(item["id"], started_at, status="done", result={"ok": True})
    # A second completion attempt (or one with a different start time) must fail.
    assert not database.finish_queue_item(item["id"], started_at, status="done", result={})
    assert not database.finish_queue_item(item["id"], "1999-01-01 00:00:00", status="done")


def test_queue_timestamps_use_utc_consistently():
    """`created_at` is SQLite UTC, so `started_at` must be UTC too.

    Mixing local time in here skews durations by the machine's UTC offset and
    would make the watchdog reclaim healthy jobs (or never reclaim hung ones).
    """
    item = database.enqueue_item("clock-test", {})
    database.update_queue_item(item["id"], status="running", started_at=queue.utc_now())

    with database.get_connection() as connection:
        skew = connection.execute(
            "SELECT ABS(strftime('%s', started_at) - strftime('%s', created_at)) "
            "FROM queue_items WHERE id = ?",
            (item["id"],),
        ).fetchone()[0]

    assert skew < 5, f"created_at and started_at disagree by {skew}s"


def test_worker_processes_a_submitted_job():
    """End-to-end: a submitted job must actually run, not sit queued."""
    done = threading.Event()
    result_holder: dict[str, object] = {}

    def handler(payload):
        result_holder.update(payload)
        done.set()
        return {"ok": True}

    queue.HANDLERS["worker-test"] = handler
    try:
        item = queue.submit("worker-test", {"value": 42})
        assert done.wait(timeout=10), "the worker never ran the job"
        assert result_holder == {"value": 42}

        # The handler returning is not the same as the job being finalized, so
        # wait for the worker to record the terminal status.
        deadline = time.time() + 10
        while time.time() < deadline and database.get_queue_item(item["id"])["status"] == "running":
            time.sleep(0.05)
        assert database.get_queue_item(item["id"])["status"] == "done"
    finally:
        queue.HANDLERS.pop("worker-test", None)


def test_failing_job_is_marked_failed_with_its_error():
    def handler(payload):
        raise RuntimeError("boom")

    queue.HANDLERS["fail-test"] = handler
    try:
        item = queue.submit("fail-test", {})
        deadline = time.time() + 10
        while time.time() < deadline:
            stored = database.get_queue_item(item["id"])
            if stored["status"] == "failed":
                break
            time.sleep(0.1)
        stored = database.get_queue_item(item["id"])
        assert stored["status"] == "failed"
        assert "boom" in stored["error"]
    finally:
        queue.HANDLERS.pop("fail-test", None)


# --------------------------------------------------------------- test isolation


def test_suite_does_not_write_to_the_real_database():
    """Tests must never touch `data/ai_business_team.db`.

    Before this was fixed, running the suite inserted real conversations and
    queue jobs into the developer's database.
    """
    from backend.database.database import DB_PATH

    assert DB_PATH.name == "test.db"
    assert DB_PATH.parent.name.startswith("test_")  # pytest tmp_path
    assert "data" not in DB_PATH.parts
