from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from backend.database.database import create_project, get_project, list_projects
from backend.services.jwt_auth import verify_token

router = APIRouter(prefix="/projects", tags=["projects"])


def authenticated_user(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    try:
        return verify_token(authorization.removeprefix("Bearer ").strip())["sub"]
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.get("")
async def list_projects_route(authorization: str | None = Header(default=None, alias="Authorization")):
    user_id = authenticated_user(authorization) if authorization else None
    return list_projects(user_id)


@router.post("")
async def create_project_route(payload: dict, authorization: str | None = Header(default=None, alias="Authorization")):
    user_id = authenticated_user(authorization)
    return create_project(payload.get("name", "Demo Project"), payload.get("description", ""), user_id)


@router.get("/{project_id}")
async def get_project_route(project_id: str, authorization: str | None = Header(default=None, alias="Authorization")):
    project = get_project(project_id, authenticated_user(authorization))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
