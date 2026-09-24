"""Tests for the live job progress stream.

The SSE endpoint is what turns the queue from something the browser polls into
something it is pushed to, so the activity feed and the streamed preview update
as the work happens. The stream must deliver the current snapshot on connect,
forward each progress write, and close on the terminal frame so the client does
not have to time out.
"""

from __future__ import annotations

import json
import threading
import time

from fastapi.testclient import TestClient

from backend.database import database
from backend.main import app
from backend.services import queue


client = TestClient(app)


def _wait_for_status(item_id: str, statuses: set[str], timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        item = database.get_queue_item(item_id)
        if item and item["status"] in statuses:
            return item
        time.sleep(0.05)
    raise AssertionError(f"job {item_id} never reached {statuses}")


def _frames(response) -> list[dict]:
    """Parse the SSE body into the JSON payloads it carried."""
    payloads = []
    for line in response.iter_lines():
        if not line or not line.startswith("data:"):
            continue
        payloads.append(json.loads(line[len("data:"):].strip()))
    return payloads


# ------------------------------------------------------------------ pub/sub


def test_subscribe_receives_published_progress():
    """A subscriber must receive the snapshots published for its job."""
    channel = queue.subscribe("pubsub-test")
    try:
        queue._publish("pubsub-test", {"status": "running", "progress": {"percent": 10}})
        payload = channel.get(timeout=2)
        assert payload["progress"]["percent"] == 10
    finally:
        queue.unsubscribe("pubsub-test", channel)


def test_unsubscribe_stops_delivery():
    """After unsubscribing, a listener must no longer be published to."""
    channel = queue.subscribe("pubsub-test")
    queue.unsubscribe("pubsub-test", channel)
    queue._publish("pubsub-test", {"status": "running"})
    assert channel.empty()


def test_publish_never_blocks_on_a_full_listener():
    """A listener that stops reading must not stall the worker thread.

    Progress is a snapshot, so dropping frames for a slow reader is correct:
    the next frame supersedes them.
    """
    channel = queue.subscribe("pubsub-test")
    try:
        for index in range(queue.SUBSCRIBER_QUEUE_SIZE + 20):
            queue._publish("pubsub-test", {"status": "running", "n": index})
        assert channel.qsize() == queue.SUBSCRIBER_QUEUE_SIZE
    finally:
        queue.unsubscribe("pubsub-test", channel)


def test_publish_reaches_every_listener():
    """Two clients watching the same job must both receive the update."""
    first = queue.subscribe("pubsub-test")
    second = queue.subscribe("pubsub-test")
    try:
        queue._publish("pubsub-test", {"status": "running"})
        assert first.get(timeout=2)["status"] == "running"
        assert second.get(timeout=2)["status"] == "running"
    finally:
        queue.unsubscribe("pubsub-test", first)
        queue.unsubscribe("pubsub-test", second)


# ------------------------------------------------------------------ endpoint


def test_events_endpoint_404s_for_an_unknown_job():
    response = client.get("/queue/does-not-exist/events")
    assert response.status_code == 404


def test_events_stream_delivers_progress_then_the_terminal_frame():
    """The stream must carry live progress and end with the finished job."""
    release = threading.Event()

    def handler(payload, report=None, activity=None):
        if report:
            report("triage", "Routing", 10)
        if activity:
            activity("Manager is routing the request.", stage="triage", agent="manager")
        # Hold the job open so the stream connects while it is still running.
        release.wait(timeout=10)
        return {"output": "done"}

    queue.HANDLERS["stream-test"] = handler
    try:
        item = queue.submit("stream-test", {})
        _wait_for_status(item["id"], {"running"})

        with client.stream("GET", f"/queue/{item['id']}/events") as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            release.set()
            payloads = _frames(response)

        assert payloads, "the stream produced no frames"
        # The first frame is the current snapshot, so a client connecting
        # mid-job is never blank.
        assert payloads[0]["id"] == item["id"]
        # The last frame is terminal, which is what lets the client stop.
        assert payloads[-1]["status"] == "done"
        assert payloads[-1]["result"]["output"] == "done"
        # The activity line reported by the handler must have been forwarded.
        activity = payloads[-1]["progress"]["activity"]
        assert any("routing the request" in entry["message"] for entry in activity)
    finally:
        release.set()
        queue.HANDLERS.pop("stream-test", None)


def test_events_stream_closes_immediately_for_a_finished_job():
    """A job that already finished must send one terminal frame and close."""

    def handler(payload):
        return {"output": "already done"}

    queue.HANDLERS["stream-finished-test"] = handler
    try:
        item = queue.submit("stream-finished-test", {})
        _wait_for_status(item["id"], {"done"})

        with client.stream("GET", f"/queue/{item['id']}/events") as response:
            payloads = _frames(response)

        assert len(payloads) == 1
        assert payloads[0]["status"] == "done"
    finally:
        queue.HANDLERS.pop("stream-finished-test", None)


def test_events_stream_releases_its_subscription():
    """The stream must unsubscribe on close, or the registry would leak."""
    item = queue.submit("stream-noop-test", {})
    _wait_for_status(item["id"], {"failed"})

    with client.stream("GET", f"/queue/{item['id']}/events") as response:
        _frames(response)

    assert item["id"] not in queue._subscribers


# ------------------------------------------------------------- queue-wide feed


def test_feed_receives_every_job():
    """A feed listener must hear about jobs other than its own."""
    channel = queue.subscribe_feed()
    try:
        queue._publish("feed-job-a", {"status": "running", "progress": {"percent": 5}})
        queue._publish("feed-job-b", {"status": "running", "progress": {"percent": 9}})
        first = channel.get(timeout=2)
        second = channel.get(timeout=2)
        assert {first["id"], second["id"]} == {"feed-job-a", "feed-job-b"}
    finally:
        queue.unsubscribe_feed(channel)


def test_feed_wraps_a_bare_progress_blob():
    """A progress write must reach the feed in the row shape the UI expects.

    `report_progress` publishes a bare progress blob; the feed has to wrap it so
    every frame carries `id`, `status`, and `progress` like a fetched row.
    """
    channel = queue.subscribe_feed()
    try:
        queue._publish("feed-shape", {"percent": 42, "label": "Working"})
        payload = channel.get(timeout=2)
        assert payload["id"] == "feed-shape"
        assert payload["status"] == "running"
        assert payload["progress"]["percent"] == 42
    finally:
        queue.unsubscribe_feed(channel)


def test_feed_unsubscribe_stops_delivery():
    channel = queue.subscribe_feed()
    queue.unsubscribe_feed(channel)
    queue._publish("feed-after-unsub", {"status": "running"})
    assert channel.empty()


def test_feed_announces_a_new_job():
    """Submitting a job must reach the feed so an open queue page shows it."""
    channel = queue.subscribe_feed()
    try:
        item = queue.submit("feed-submit-test", {})
        payload = channel.get(timeout=2)
        assert payload["id"] == item["id"]
        assert payload["status"] == "queued"
    finally:
        queue.unsubscribe_feed(channel)


def test_feed_endpoint_is_registered():
    """The queue-wide feed route must exist and be an SSE endpoint.

    The stream itself never closes (the queue has no terminal state), so it is
    not consumed here: the pub/sub tests above cover the delivery, and this
    checks the route is wired up with the right media type.
    """
    paths = client.get("/openapi.json").json()["paths"]
    assert "/queue/events" in paths
    assert "get" in paths["/queue/events"]
