from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.services.auth import login_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(payload: dict):
    try:
        return register_user(payload["email"], payload["password"], payload.get("name", "Demo User"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login")
async def login(payload: dict):
    try:
        return login_user(payload["email"], payload["password"])
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
