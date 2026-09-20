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


def test_generate_endpoint_reports_provider_failure_honestly():
    """Without a live provider the endpoint must report an error, not a fake answer."""
    response = client.post(
        "/generate",
        json={
            "prompt": "Write a marketing ad for Arizona homeowners about a solar evaluation.",
            "project_id": "demo-project",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "error"}
    assert "trace" in body
    if body["status"] == "error":
        # An error must always explain itself rather than returning empty content.
        assert body["error"] is not None
        assert body["error"]["message"]
        assert body["error"]["hint"]


def test_generate_endpoint_rejects_empty_prompt():
    response = client.post("/generate", json={"prompt": "", "project_id": "demo-project"})
    assert response.status_code == 422


def test_agents_endpoint_exposes_the_chain_of_command():
    response = client.get("/agents")
    assert response.status_code == 200
    agents = response.json()

    manager = next(agent for agent in agents if agent["id"] == "manager")
    assert manager["user_facing"] is True

    # Every other agent must be internal.
    for agent in agents:
        if agent["id"] != "manager":
            assert agent["user_facing"] is False

    heads = [agent for agent in agents if agent["role"] == "department_head"]
    assert {head["id"] for head in heads} == {"marketing", "sales", "automation"}

    specialists = [agent for agent in agents if agent["role"] == "specialist"]
    assert len(specialists) >= 6


def test_quality_gates_endpoint_documents_the_backtest_bar():
    response = client.get("/evaluations/quality-gates")
    assert response.status_code == 200
    gates = response.json()["sales_scripts"]
    assert gates["minimum_calls"] == 20
    assert gates["target_conversion_rate"] == 0.5
