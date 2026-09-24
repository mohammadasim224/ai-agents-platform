from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.database.database import (
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    update_profile,
)
from backend.services.knowledge_builder import build_knowledge_base_ai

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("")
async def list_profiles_route():
    return list_profiles()


@router.post("")
async def create_profile_route(payload: dict):
    return create_profile(payload)


@router.get("/{profile_id}")
async def get_profile_route(profile_id: str):
    profile = get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/{profile_id}")
async def update_profile_route(profile_id: str, payload: dict):
    profile = update_profile(profile_id, payload)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.delete("/{profile_id}")
async def delete_profile_route(profile_id: str):
    delete_profile(profile_id)
    return {"status": "ok"}


@router.post("/{profile_id}/build-knowledge")
async def build_knowledge_route(profile_id: str):
    """Convert a profile into a knowledge base.

    Runs the AI expansion when a provider is configured and falls back to the
    deterministic template output otherwise, so the user always gets a usable
    knowledge base.
    """
    profile = get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return build_knowledge_base_ai(profile)