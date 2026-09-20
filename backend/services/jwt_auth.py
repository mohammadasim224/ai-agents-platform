from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-me")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _encode(value: dict) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def create_token(user_id: str, email: str) -> str:
    header = _encode({"alg": "HS256", "typ": "JWT"})
    payload = _encode({"sub": user_id, "email": email, "exp": int(time.time()) + 86400})
    unsigned = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), unsigned, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{header}.{payload}.{encoded_signature}"


def verify_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
        unsigned = f"{header}.{payload}".encode("ascii")
        expected = hmac.new(SECRET_KEY.encode("utf-8"), unsigned, hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("Invalid token")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if claims.get("exp", 0) < int(time.time()):
            raise ValueError("Token expired")
        return claims
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid token") from exc
