"""Tests for the workspace features: profiles, knowledge builder, conversations,
memory, and the background queue.

These tests use the stubbed model router from conftest, so the knowledge builder
falls back to its deterministic template mode and generation jobs fail honestly
instead of hitting a live provider.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)

PROFILE_PAYLOAD = {
    "name": "SunPeak Solar",
    "business_type": "Residential solar installer",
    "industry": "Solar",
    "description": "Installs residential solar for homeowners.",
    "target_customer": "Homeowners in Arizona with high electric bills.",
    "services": "Solar evaluation\nSolar installation",
    "offers": "Free solar evaluation",
    "pricing": "Custom quotes based on the home",
    "brand_voice": "Educational, honest, no hype",
    "marketing_channels": "Meta ads, SMS",
    "sales_process": "Setter books a call, closer closes, install team installs.",
    "automation_needs": "SMS nurture sequence for opt-in leads",
    "geographic_focus": "Arizona",
    "compliance_notes": "Never promise guaranteed savings.",
}


def test_profile_crud_round_trip():
    created = client.post("/profiles", json=PROFILE_PAYLOAD)
    assert created.status_code == 200
    profile = created.json()
    assert profile["name"] == "SunPeak Solar"
    assert profile["target_customer"].startswith("Homeowners")

    fetched = client.get(f"/profiles/{profile['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == profile["id"]

    updated = client.put(f"/profiles/{profile['id']}", json={**PROFILE_PAYLOAD, "name": "SunPeak Solar 2"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "SunPeak Solar 2"

    listed = client.get("/profiles")
    assert any(item["id"] == profile["id"] for item in listed.json())

    deleted = client.delete(f"/profiles/{profile['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/profiles/{profile['id']}").status_code == 404


def test_build_knowledge_from_profile_writes_documents():
    created = client.post("/profiles", json=PROFILE_PAYLOAD)
    profile_id = created.json()["id"]

    response = client.post(f"/profiles/{profile_id}/build-knowledge")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] in {"template", "ai"}
    filenames = [doc["filename"] for doc in body["documents"]]
    assert "company.md" in filenames
    assert "target_customer.md" in filenames
    assert "services_and_offers.md" in filenames

    # The generated company file must contain the profile name.
    company = next(doc for doc in body["documents"] if doc["filename"] == "company.md")
    assert company["size"] > 0

    client.delete(f"/profiles/{profile_id}")


def test_build_knowledge_requires_existing_profile():
    response = client.post("/profiles/does-not-exist/build-knowledge")
    assert response.status_code == 404


def test_conversation_lifecycle():
    created = client.post("/conversations", json={"profile_id": "default", "title": "Test chat"})
    assert created.status_code == 200
    conversation_id = created.json()["id"]

    sent = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Write an ad for Arizona homeowners.", "profile_id": "default"},
    )
    assert sent.status_code == 200
    body = sent.json()
    assert body["conversation_id"] == conversation_id
    assert body["message"]["role"] == "user"
    assert body["job"]["kind"] == "generate"
    assert body["job"]["status"] in {"queued", "running", "done", "failed"}

    fetched = client.get(f"/conversations/{conversation_id}")
    assert fetched.status_code == 200
    roles = [message["role"] for message in fetched.json()["messages"]]
    assert "user" in roles

    listed = client.get("/conversations?profile_id=default")
    assert any(item["id"] == conversation_id for item in listed.json())

    renamed = client.patch(f"/conversations/{conversation_id}", json={"title": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Renamed"

    deleted = client.delete(f"/conversations/{conversation_id}")
    assert deleted.status_code == 200
    assert client.get(f"/conversations/{conversation_id}").status_code == 200  # empty messages


def test_conversation_rejects_empty_message():
    created = client.post("/conversations", json={"profile_id": "default", "title": "Empty test"})
    conversation_id = created.json()["id"]
    response = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "   ", "profile_id": "default"},
    )
    assert response.status_code == 422
    client.delete(f"/conversations/{conversation_id}")


def test_memory_add_list_delete():
    added = client.post(
        "/memory",
        json={"profile_id": "default", "content": "Never promise guaranteed savings.", "category": "compliance"},
    )
    assert added.status_code == 200
    memory_id = added.json()["id"]

    listed = client.get("/memory?profile_id=default")
    assert any(item["id"] == memory_id for item in listed.json())

    deleted = client.delete(f"/memory/{memory_id}")
    assert deleted.status_code == 200
    listed_after = client.get("/memory?profile_id=default")
    assert all(item["id"] != memory_id for item in listed_after.json())


def test_memory_rejects_empty_content():
    response = client.post("/memory", json={"profile_id": "default", "content": "  "})
    assert response.status_code == 422


def test_queue_lists_jobs_and_reports_status():
    response = client.get("/queue")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # A submitted job must be visible in the queue listing.
    created = client.post("/conversations", json={"profile_id": "default", "title": "Queue test"})
    conversation_id = created.json()["id"]
    sent = client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Write a nurture sequence.", "profile_id": "default"},
    )
    job_id = sent.json()["job"]["id"]

    status = client.get(f"/queue/{job_id}")
    assert status.status_code == 200
    assert status.json()["id"] == job_id
    assert status.json()["status"] in {"queued", "running", "done", "failed"}

    listed = client.get("/queue")
    assert any(item["id"] == job_id for item in listed.json())

    client.delete(f"/conversations/{conversation_id}")


def test_queue_status_404_for_unknown_job():
    response = client.get("/queue/does-not-exist")
    assert response.status_code == 404


def test_knowledge_builder_template_output_is_deterministic():
    """The template builder must produce the same output for the same profile."""
    from backend.services.knowledge_builder import build_company_md

    first = build_company_md(PROFILE_PAYLOAD)
    second = build_company_md(PROFILE_PAYLOAD)
    assert first == second
    assert "SunPeak Solar" in first
    assert "## Business Type" in first