from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_projects_endpoint():
    response = client.get("/projects")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_generate_endpoint_returns_output():
    response = client.post(
        "/generate",
        json={
            "prompt": "Write a marketing ad for Arizona homeowners about a free solar consultation.",
            "project_id": "demo-project",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "output" in body
    assert len(body["output"]) > 50
    assert "decision" in body
