from __future__ import annotations

from fastapi import APIRouter

from backend.agents.registry import DEPARTMENTS, SPECIALISTS

router = APIRouter(prefix="/agents", tags=["agents"])


def _agent_catalog() -> list[dict]:
    """Describe the chain of command.

    The manager is the only user-facing agent, so it is listed first with
    `user_facing: true`. Department heads and specialists are internal.
    """
    agents = [
        {
            "id": "manager",
            "name": "Manager",
            "department": "orchestration",
            "role": "manager",
            "user_facing": True,
            "description": (
                "Routes work to the right department, rewrites the request into a precise "
                "brief, verifies the combined answer, and is the only agent that speaks to you."
            ),
        }
    ]

    for department in DEPARTMENTS.values():
        agents.append(
            {
                "id": department.name,
                "name": department.title,
                "department": department.name,
                "role": "department_head",
                "user_facing": False,
                "description": department.mission,
                "specialists": list(department.specialists),
            }
        )

    for specialist in SPECIALISTS.values():
        agents.append(
            {
                "id": specialist.name,
                "name": specialist.title,
                "department": specialist.department,
                "role": "specialist",
                "user_facing": False,
                "description": specialist.produces,
                "requires_backtest": specialist.requires_backtest,
            }
        )

    return agents


@router.get("")
async def list_agents():
    return _agent_catalog()


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    for agent in _agent_catalog():
        if agent["id"] == agent_id:
            return agent
    return {"id": agent_id, "error": "Unknown agent."}
