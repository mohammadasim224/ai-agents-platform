"""Tests for live job activity streaming.

The activity log is the running commentary of what a job is doing: which agent
is working, what it generated, and what the quality gates found. It is what lets
the UI show the work as it happens instead of only a percentage, so it must be
recorded, bounded, and carried on every progress write.
"""

from __future__ import annotations

import threading
import time

from backend.database import database
from backend.services import queue


def _wait_for_status(item_id: str, statuses: set[str], timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        item = database.get_queue_item(item_id)
        if item and item["status"] in statuses:
            return item
        time.sleep(0.05)
    raise AssertionError(f"job {item_id} never reached {statuses}")


# ------------------------------------------------------------------ activity


def test_report_activity_is_a_noop_outside_a_job():
    """Calling the activity reporter with no job running must not raise."""
    queue.report_activity("Nothing is running.", stage="triage")


def test_activity_is_recorded_on_the_job_progress():
    """An activity line must reach the stored progress payload."""
    done = threading.Event()

    def handler(payload, report=None, activity=None):
        if report:
            report("triage", "Routing", 10)
        if activity:
            activity("Manager is routing the request.", stage="triage", agent="manager")
        done.set()
        return {"ok": True}

    queue.HANDLERS["activity-handler-test"] = handler
    try:
        item = queue.submit("activity-handler-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
        stored = _wait_for_status(item["id"], {"done"})
        activity = stored["progress"]["activity"]
        assert any("routing the request" in entry["message"] for entry in activity)
        assert activity[-1]["agent"] == "manager"
    finally:
        queue.HANDLERS.pop("activity-handler-test", None)


def test_activity_survives_a_later_progress_write():
    """A progress update must not wipe the activity log already recorded."""
    done = threading.Event()

    def handler(payload, report=None, activity=None):
        if activity:
            activity("First line.", stage="triage")
        if report:
            report("plan", "Planning", 24)
        if activity:
            activity("Second line.", stage="plan")
        done.set()
        return {"ok": True}

    queue.HANDLERS["activity-carry-test"] = handler
    try:
        item = queue.submit("activity-carry-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
        stored = _wait_for_status(item["id"], {"done"})
        messages = [entry["message"] for entry in stored["progress"]["activity"]]
        assert "First line." in messages
        assert "Second line." in messages
    finally:
        queue.HANDLERS.pop("activity-carry-test", None)


def test_activity_log_is_bounded():
    """A long job must not grow the activity log without limit."""
    done = threading.Event()

    def handler(payload, report=None, activity=None):
        if report:
            report("specialist", "Producing", 50)
        if activity:
            for index in range(queue.MAX_ACTIVITY_ENTRIES + 25):
                activity(f"Line {index}", stage="specialist")
        done.set()
        return {"ok": True}

    queue.HANDLERS["activity-bound-test"] = handler
    try:
        item = queue.submit("activity-bound-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
        stored = _wait_for_status(item["id"], {"done"})
        activity = stored["progress"]["activity"]
        assert len(activity) == queue.MAX_ACTIVITY_ENTRIES
        # The newest entries are the ones kept.
        assert activity[-1]["message"] == f"Line {queue.MAX_ACTIVITY_ENTRIES + 24}"
    finally:
        queue.HANDLERS.pop("activity-bound-test", None)


def test_activity_preview_is_capped():
    """A streamed preview must be capped so a long generation cannot bloat it."""
    done = threading.Event()

    def handler(payload, report=None, activity=None):
        if report:
            report("specialist", "Producing", 50)
        if activity:
            activity("Writing...", stage="specialist", preview="x" * 5000)
        done.set()
        return {"ok": True}

    queue.HANDLERS["activity-preview-test"] = handler
    try:
        item = queue.submit("activity-preview-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
        stored = _wait_for_status(item["id"], {"done"})
        preview = stored["progress"]["activity"][-1]["preview"]
        assert len(preview) == queue.MAX_ACTIVITY_PREVIEW_CHARS
    finally:
        queue.HANDLERS.pop("activity-preview-test", None)


def test_worker_passes_an_activity_reporter_to_handlers_that_want_one():
    """A handler declaring `activity` receives a callable it can use."""
    captured: dict[str, object] = {}
    done = threading.Event()

    def handler(payload, activity=None):
        captured["activity"] = activity
        done.set()
        return {"ok": True}

    queue.HANDLERS["activity-inject-test"] = handler
    try:
        item = queue.submit("activity-inject-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
        assert callable(captured["activity"])
    finally:
        queue.HANDLERS.pop("activity-inject-test", None)


def test_plain_handlers_still_work_without_an_activity_reporter():
    """A handler that declares neither `report` nor `activity` still runs."""
    done = threading.Event()

    def handler(payload):
        done.set()
        return {"ok": True}

    queue.HANDLERS["activity-plain-test"] = handler
    try:
        item = queue.submit("activity-plain-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
        stored = _wait_for_status(item["id"], {"done"})
        assert stored["status"] == "done"
    finally:
        queue.HANDLERS.pop("activity-plain-test", None)


def test_activity_does_not_inflate_the_eta():
    """An activity line must not move the bar or inflate the time estimate.

    Activity re-publishes the current progress so the new line reaches the UI.
    Re-projecting the ETA at a later elapsed time with an unchanged percent would
    make the estimate grow on every line, so the last timing is reused instead.
    """
    done = threading.Event()
    captured: list[dict] = []

    def handler(payload, report=None, activity=None):
        if report:
            report("specialist", "Producing", 50)
        captured.append(database.get_queue_item(holder["id"])["progress"])
        if activity:
            activity("A line that must not move the bar.", stage="specialist")
        captured.append(database.get_queue_item(holder["id"])["progress"])
        done.set()
        return {"ok": True}

    holder: dict[str, str] = {}
    queue.HANDLERS["activity-eta-test"] = handler
    try:
        item = queue.submit("activity-eta-test", {})
        holder["id"] = item["id"]
        assert done.wait(timeout=10), "the worker never ran the job"
        before, after = captured[0], captured[1]
        assert after["percent"] == before["percent"]
        assert after["estimate_seconds"] == before["estimate_seconds"]
        assert after["eta_seconds"] == before["eta_seconds"]
    finally:
        queue.HANDLERS.pop("activity-eta-test", None)


def test_streamed_previews_coalesce_into_one_entry():
    """A long generation must stay one growing line, not flood the log.

    The router reports the text generated so far many times per second. If each
    report appended a line, a single deliverable would fill the whole activity
    log with identical "is writing..." entries and push the meaningful steps out
    of view.
    """
    done = threading.Event()

    def handler(payload, report=None, activity=None):
        if report:
            report("specialist", "Producing", 50)
        if activity:
            activity("Agent is working.", stage="specialist", agent="closing")
            for index in range(30):
                activity(
                    "Agent is writing...",
                    stage="specialist",
                    agent="closing",
                    preview="x" * (index + 1),
                )
            activity("Agent produced 500 characters.", stage="specialist", agent="closing", kind="ok")
        done.set()
        return {"ok": True}

    queue.HANDLERS["activity-coalesce-test"] = handler
    try:
        item = queue.submit("activity-coalesce-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
        stored = _wait_for_status(item["id"], {"done"})
        activity = stored["progress"]["activity"]
        messages = [entry["message"] for entry in activity]
        # The 30 streamed reports collapse into a single entry.
        assert messages.count("Agent is writing...") == 1
        # The surrounding meaningful steps are preserved.
        assert "Agent is working." in messages
        assert "Agent produced 500 characters." in messages
        # The single streaming entry holds the newest preview.
        streaming = [entry for entry in activity if entry.get("streaming")]
        assert len(streaming) == 1
        assert streaming[0]["preview"] == "x" * 30
    finally:
        queue.HANDLERS.pop("activity-coalesce-test", None)


def test_a_new_agent_starts_a_new_streaming_entry():
    """Two agents streaming in turn must not overwrite each other's line."""
    done = threading.Event()

    def handler(payload, report=None, activity=None):
        if report:
            report("specialist", "Producing", 50)
        if activity:
            activity("A is writing...", stage="specialist", agent="a", preview="aaa")
            activity("B is writing...", stage="specialist", agent="b", preview="bbb")
        done.set()
        return {"ok": True}

    queue.HANDLERS["activity-two-agents-test"] = handler
    try:
        item = queue.submit("activity-two-agents-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
        stored = _wait_for_status(item["id"], {"done"})
        activity = stored["progress"]["activity"]
        agents = [entry["agent"] for entry in activity if entry.get("streaming")]
        assert agents == ["a", "b"]
    finally:
        queue.HANDLERS.pop("activity-two-agents-test", None)


# --------------------------------------------------------------- orchestrator


def test_orchestrator_emits_activity_for_the_stages_it_reaches():
    """The orchestrator must publish live activity, not only a percentage."""
    from backend.orchestrator import Orchestrator

    lines: list[str] = []

    def note(message, **kwargs):
        lines.append(message)

    orchestrator = Orchestrator("activity-test", activity=note)
    # The provider is stubbed by conftest, so the pipeline fails at triage. The
    # activity callback must still have fired for the stages it reached.
    orchestrator.run("Write a marketing ad for Arizona homeowners.")

    assert lines, "no activity was reported"
    assert any("Manager is reading the request" in line for line in lines)


def test_orchestrator_activity_failure_does_not_break_the_pipeline():
    """A broken activity sink must not fail the request."""
    from backend.orchestrator import Orchestrator

    def explode(*args, **kwargs):
        raise RuntimeError("activity sink is down")

    orchestrator = Orchestrator("activity-test", activity=explode)
    result = orchestrator.run("Write a marketing ad for Arizona homeowners.")
    assert result.status == "error"


def test_activity_from_worker_threads_reaches_the_job():
    """Activity emitted from a concurrent worker must reach the job's log.

    The pipeline runs departments and subtasks in a thread pool, and
    `ThreadPoolExecutor` does not copy the caller's contextvars into its workers.
    Without propagating the context, every live update from concurrent work was
    silently dropped, which is exactly where the generation happens.
    """
    done = threading.Event()

    def handler(payload, report=None, activity=None):
        from concurrent.futures import ThreadPoolExecutor

        from backend.orchestrator import Orchestrator

        if report:
            report("specialist", "Producing", 50)

        orchestrator = Orchestrator("activity-thread-test", activity=activity)

        def worker():
            orchestrator._note("Emitted from a worker thread.", stage="specialist")

        with ThreadPoolExecutor(max_workers=1) as pool:
            orchestrator._submit(pool, worker).result()
        done.set()
        return {"ok": True}

    queue.HANDLERS["activity-thread-test"] = handler
    try:
        item = queue.submit("activity-thread-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
        stored = _wait_for_status(item["id"], {"done"})
        messages = [entry["message"] for entry in stored["progress"]["activity"]]
        assert "Emitted from a worker thread." in messages
    finally:
        queue.HANDLERS.pop("activity-thread-test", None)


# ------------------------------------------------------------------- router


def test_stream_assembles_content_and_reports_deltas():
    """The streaming call must assemble the text and report it as it arrives."""
    from backend.llm import router

    class FakeResponse:
        status_code = 200

        def iter_lines(self, decode_unicode=True):
            yield 'data: {"id":"abc","choices":[{"delta":{"content":"Hello "}}]}'
            yield ""
            yield 'data: {"choices":[{"delta":{"content":"world"}}]}'
            yield 'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":2}}'
            yield "data: [DONE]"

        def close(self):
            pass

    reported: list[str] = []
    original_post = router.requests.post
    original_key = router.OPENROUTER_API_KEY
    router.OPENROUTER_API_KEY = "test-key"
    router.requests.post = lambda *args, **kwargs: FakeResponse()
    try:
        result = router.call_openrouter_stream(
            "test-model",
            "hi",
            on_delta=reported.append,
        )
    finally:
        router.requests.post = original_post
        router.OPENROUTER_API_KEY = original_key

    assert result["content"] == "Hello world"
    assert result["usage"]["output_tokens"] == 2
    assert reported, "no deltas were reported"
    assert reported[-1] == "Hello world"


def test_stream_raises_on_an_empty_completion():
    """A stream that ends without content must fail honestly, not return empty."""
    import pytest

    from backend.errors import ProviderError
    from backend.llm import router

    class FakeResponse:
        status_code = 200

        def iter_lines(self, decode_unicode=True):
            yield "data: [DONE]"

        def close(self):
            pass

    original_post = router.requests.post
    original_key = router.OPENROUTER_API_KEY
    original_attempts = router.LLM_MAX_ATTEMPTS
    router.OPENROUTER_API_KEY = "test-key"
    router.LLM_MAX_ATTEMPTS = 1
    router.requests.post = lambda *args, **kwargs: FakeResponse()
    try:
        with pytest.raises(ProviderError):
            router.call_openrouter_stream("test-model", "hi")
    finally:
        router.requests.post = original_post
        router.OPENROUTER_API_KEY = original_key
        router.LLM_MAX_ATTEMPTS = original_attempts
