from fastapi.testclient import TestClient

from backend.main import app
from backend.services.compliance import check_compliance


client = TestClient(app)


def test_compliance_rejects_free_solar_claims():
    result = check_compliance("Get free solar panels now")
    assert result["status"] == "blocked"
    assert result["issues"]


def test_task_creation_works_through_api():
    response = client.post(
        "/tasks",
        json={"project_id": "demo-project", "prompt": "Write an ad for Arizona homeowners."},
    )
    assert response.status_code == 200
    body = response.json()
    assert "task" in body
    assert body["task"]["agent"] in {"ad_copywriting", "ad_scripting"}
