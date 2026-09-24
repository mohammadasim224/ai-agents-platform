from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.services import memory

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
async def list_memory_route(profile_id: str | None = None):
    return memory.list_for_profile(profile_id)


@router.post("")
async def add_memory_route(payload: dict):
    try:
        return memory.add(
            payload.get("profile_id", "default"),
            payload.get("content", ""),
            payload.get("category", "general"),
            payload.get("source", "manual"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{memory_id}")
async def delete_memory_route(memory_id: str):
    memory.remove(memory_id)
    return {"status": "ok"}