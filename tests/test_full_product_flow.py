from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_register_login_and_project_access():
    register = client.post(
        "/auth/register",
        json={"email": "owner@example.com", "password": "secret123", "name": "Owner"},
    )
    assert register.status_code == 200
    token = register.json()["token"]

    project = client.post(
        "/projects",
        json={"name": "Client Project", "description": "Demo product"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert project.status_code == 200
    project_id = project.json()["id"]

    fetched = client.get(f"/projects/{project_id}", headers={"Authorization": f"Bearer {token}"})
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Client Project"


def test_team_workflow_route_returns_structured_output():
    response = client.post(
        "/workflows/team-campaign",
        json={"prompt": "Create a campaign for Arizona homeowners about solar evaluations."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workflow"] == "team-campaign"
    assert body["status"] in {"ok", "error"}
    assert "trace" in body
    if body["status"] == "error":
        assert body["error"]["message"]


def test_team_workflow_rejects_empty_prompt():
    response = client.post("/workflows/team-campaign", json={"prompt": ""})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "empty_prompt"
