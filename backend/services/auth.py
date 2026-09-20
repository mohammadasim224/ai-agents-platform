from __future__ import annotations

import hashlib
import uuid

from backend.services.jwt_auth import create_token

USERS: dict[str, dict] = {}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def register_user(email: str, password: str, name: str) -> dict:
    if email in USERS:
        raise ValueError("User already exists")
    user_id = str(uuid.uuid4())
    USERS[email] = {"id": user_id, "email": email, "name": name, "password": hash_password(password)}
    return {
        "token": create_token(user_id, email),
        "user": {"id": user_id, "email": email, "name": name},
    }


def login_user(email: str, password: str) -> dict:
    user = USERS.get(email)
    if not user:
        raise ValueError("Invalid credentials")
    if user["password"] != hash_password(password):
        raise ValueError("Invalid credentials")
    return {
        "token": create_token(user["id"], email),
        "user": {"id": user["id"], "email": email, "name": user["name"]},
    }
