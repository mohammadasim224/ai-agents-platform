from fastapi.testclient import TestClient

from backend.main import app
from backend.services.compliance import check_compliance


client = TestClient(app)


def test_compliance_rejects_free_solar_claims():
    result = check_compliance("Get free solar panels now")
    assert result["status"] == "blocked"
    assert result["issues"]


def test_compliance_rejects_fabricated_anecdotes():
    result = check_compliance("My neighbor installed panels and her bill dropped.")
    assert result["status"] == "blocked"
    assert any(issue["type"] == "fabricated_anecdote" for issue in result["issues"])


def test_compliance_rejects_guaranteed_bill_elimination():
    result = check_compliance("We guarantee savings and eliminate your electric bill.")
    assert result["status"] == "blocked"


def test_compliance_allows_conditional_language():
    result = check_compliance(
        "Solar may reduce your electricity costs depending on your utility and home, "
        "if you qualify."
    )
    assert result["status"] == "pass"
    assert result["issues"] == []


def test_task_creation_works_through_api():
    response = client.post(
        "/tasks",
        json={"project_id": "demo-project", "prompt": "Write an ad for Arizona homeowners."},
    )
    assert response.status_code == 200
    body = response.json()
    # The task is recorded regardless of whether the provider is reachable.
    assert "task" in body
    assert body["task"]["agent"] in {"marketing", "sales", "automation", "unassigned"}
    assert body["status"] in {"ok", "error"}


def test_task_creation_rejects_empty_prompt():
    response = client.post("/tasks", json={"project_id": "demo-project", "prompt": ""})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "empty_prompt"
