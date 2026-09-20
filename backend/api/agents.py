from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
async def list_agents():
    return [
        {"id": "manager", "name": "Manager", "department": "orchestration"},
        {"id": "marketing", "name": "Marketing Agent", "department": "marketing"},
        {"id": "sales", "name": "Sales Agent", "department": "sales"},
    ]


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    return {"id": agent_id, "name": agent_id.title(), "department": "general"}
