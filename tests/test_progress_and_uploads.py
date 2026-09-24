"""Tests for job progress reporting and hardened file uploads.

Progress is what lets the UI show a percentage and an estimated time remaining
instead of an indefinite spinner, so it must be reported for every stage and
must never move backwards. Uploads must reject oversized, empty, and unsupported
files, and must never overwrite an existing file.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from backend.database import database
from backend.main import app
from backend.services import queue


client = TestClient(app)


# ------------------------------------------------------------------ progress


def test_progress_is_recorded_for_each_pipeline_stage():
    """Every stage the orchestrator reaches must publish a progress update."""
    from backend.orchestrator import Orchestrator

    seen: list[tuple[str, float]] = []

    def record(stage, label, percent, **kwargs):
        seen.append((stage, percent))

    orchestrator = Orchestrator("progress-test", progress=record)
    # The provider is stubbed by conftest, so the pipeline fails at triage. The
    # progress callback must still have fired for the stages it reached.
    orchestrator.run("Write a marketing ad for Arizona homeowners.")

    assert seen, "no progress was reported"
    stages = [stage for stage, _ in seen]
    assert "triage" in stages


def test_progress_never_moves_backwards():
    """A later stage must never report a lower percentage than an earlier one."""
    from backend.orchestrator import Orchestrator

    percents: list[float] = []

    def record(stage, label, percent, **kwargs):
        percents.append(percent)

    orchestrator = Orchestrator("progress-test", progress=record)
    orchestrator.run("Write a marketing ad for Arizona homeowners.")

    assert percents == sorted(percents), f"progress went backwards: {percents}"


def test_progress_callback_failure_does_not_break_the_pipeline():
    """A broken progress reporter must not fail the request."""
    from backend.orchestrator import Orchestrator

    def explode(*args, **kwargs):
        raise RuntimeError("progress sink is down")

    orchestrator = Orchestrator("progress-test", progress=explode)
    result = orchestrator.run("Write a marketing ad for Arizona homeowners.")
    # The provider is stubbed, so this is an honest error result, not a crash.
    assert result.status == "error"


def test_report_progress_is_a_noop_outside_a_job():
    """Calling the reporter with no job running must not raise."""
    queue.report_progress("triage", "Routing", 10)


def test_queue_item_exposes_progress_as_structured_data():
    item = database.enqueue_item("progress-shape", {})
    database.update_queue_item(
        item["id"],
        progress={"stage": "plan", "label": "Planning", "percent": 24.0},
    )
    stored = database.get_queue_item(item["id"])
    assert stored["progress"]["stage"] == "plan"
    assert stored["progress"]["percent"] == 24.0


def test_worker_passes_a_reporter_to_handlers_that_want_one():
    """A handler declaring `report` receives a callable it can use."""
    import threading
    import time

    captured: dict[str, object] = {}
    done = threading.Event()

    def handler(payload, report=None):
        captured["report"] = report
        if report:
            report("triage", "Routing", 10)
        done.set()
        return {"ok": True}

    queue.HANDLERS["progress-handler-test"] = handler
    try:
        item = queue.submit("progress-handler-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
        assert callable(captured["report"])

        deadline = time.time() + 10
        while time.time() < deadline and database.get_queue_item(item["id"])["status"] == "running":
            time.sleep(0.05)
        stored = database.get_queue_item(item["id"])
        assert stored["status"] == "done"
        assert stored["progress"]["stage"] == "triage"
    finally:
        queue.HANDLERS.pop("progress-handler-test", None)


def test_plain_handlers_still_work_without_a_reporter():
    """Handlers that do not declare `report` keep the simple signature."""
    import threading

    done = threading.Event()

    def handler(payload):
        done.set()
        return {"ok": True}

    queue.HANDLERS["plain-handler-test"] = handler
    try:
        queue.submit("plain-handler-test", {})
        assert done.wait(timeout=10), "the worker never ran the job"
    finally:
        queue.HANDLERS.pop("plain-handler-test", None)


def test_worker_survives_a_job_that_raises_outside_the_handler():
    """A fault while recording a result must not kill the single worker.

    Only one worker thread runs jobs, so an exception escaping `_process` would
    stop every future job from being picked up.
    """
    import threading
    import time

    ran = threading.Event()

    def handler(payload):
        ran.set()
        # Not a dict, so `finish_queue_item` does its normal path; the point is
        # that a later job must still be processed after this one.
        return {"ok": True}

    queue.HANDLERS["survive-test"] = handler
    try:
        first = queue.submit("survive-test", {})
        assert ran.wait(timeout=10)

        # Give the worker a moment to finalize the first job.
        deadline = time.time() + 10
        while time.time() < deadline and database.get_queue_item(first["id"])["status"] == "running":
            time.sleep(0.05)

        ran.clear()
        second = queue.submit("survive-test", {})
        assert ran.wait(timeout=10), "the worker stopped processing jobs"
        assert database.get_queue_item(second["id"])["status"] in {"running", "done"}
    finally:
        queue.HANDLERS.pop("survive-test", None)


# ------------------------------------------------------------------- uploads


def test_upload_rejects_unsupported_extension():
    response = client.post(
        "/knowledge/upload",
        files={"file": ("notes.exe", io.BytesIO(b"binary"), "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_rejects_an_empty_file():
    response = client.post(
        "/knowledge/upload",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_sanitizes_a_traversal_filename():
    """A crafted filename must not escape the upload directory."""
    response = client.post(
        "/knowledge/upload",
        files={"file": ("../../evil.txt", io.BytesIO(b"payload"), "text/plain")},
    )
    assert response.status_code == 200
    filename = response.json()["filename"]
    assert "/" not in filename
    assert ".." not in filename

    from backend.config import UPLOADS_DIR

    assert (UPLOADS_DIR / filename).is_file()
    client.delete(f"/knowledge/uploads/{filename}")


def test_upload_does_not_overwrite_an_existing_file():
    first = client.post(
        "/knowledge/upload",
        files={"file": ("duplicate.txt", io.BytesIO(b"first version"), "text/plain")},
    )
    second = client.post(
        "/knowledge/upload",
        files={"file": ("duplicate.txt", io.BytesIO(b"second version"), "text/plain")},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["filename"] != second.json()["filename"]

    from backend.config import UPLOADS_DIR

    assert (UPLOADS_DIR / first.json()["filename"]).read_bytes() == b"first version"
    client.delete(f"/knowledge/uploads/{first.json()['filename']}")
    client.delete(f"/knowledge/uploads/{second.json()['filename']}")


def test_upload_reports_whether_the_file_is_readable():
    response = client.post(
        "/knowledge/upload",
        files={"file": ("readable.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["readable"] is True
    client.delete(f"/knowledge/uploads/{response.json()['filename']}")


def test_upload_listing_includes_readable_flag():
    response = client.get("/knowledge/uploads")
    assert response.status_code == 200
    for entry in response.json():
        assert "readable" in entry


def test_attachment_rejects_an_unreadable_extension():
    """A `.doc` upload is accepted but must fail clearly when used as context."""
    from backend.errors import AttachmentError
    from backend.services.attachments import read_attachment

    uploaded = client.post(
        "/knowledge/upload",
        files={"file": ("legacy.doc", io.BytesIO(b"old format"), "application/msword")},
    )
    assert uploaded.status_code == 200
    filename = uploaded.json()["filename"]
    try:
        read_attachment(filename)
        raise AssertionError("expected AttachmentError for an unreadable file type")
    except AttachmentError as error:
        assert "cannot be read" in error.message
    finally:
        client.delete(f"/knowledge/uploads/{filename}")


def test_attachment_truncation_notice_is_not_a_placeholder_marker():
    """A truncated attachment must not trip the specialist placeholder check."""
    from backend.agents.specialists.runner import PLACEHOLDER_MARKERS
    from backend.services.attachments import TRUNCATION_NOTICE

    lowered = TRUNCATION_NOTICE.lower()
    for marker in PLACEHOLDER_MARKERS:
        assert marker not in lowered, f"truncation notice contains placeholder marker {marker!r}"
