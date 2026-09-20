from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_user_registration_and_login():
    register = client.post(
        "/auth/register",
        json={"email": "demo@example.com", "password": "secret123", "name": "Demo User"},
    )
    assert register.status_code == 200
    body = register.json()
    assert body["user"]["email"] == "demo@example.com"

    login = client.post(
        "/auth/login",
        json={"email": "demo@example.com", "password": "secret123"},
    )
    assert login.status_code == 200
    assert "token" in login.json()
