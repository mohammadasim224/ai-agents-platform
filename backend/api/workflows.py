from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.services.generation import generate_for_prompt

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/team-campaign")
async def team_campaign(payload: dict):
    prompt = payload.get("prompt", "Create a campaign")
    try:
        output = generate_for_prompt(prompt, "demo-project")
    except RuntimeError as exc:
        output = {
            "decision": {
                "department": "marketing",
                "agent": "ad_copywriting",
                "task_type": "team_campaign",
                "needs_clarification": False,
            },
            "output": "Campaign generation is temporarily unavailable. Please retry shortly.",
            "compliance": {"status": "pending", "reason": str(exc)},
        }
    return {
        "workflow": "team-campaign",
        "results": [
            {"agent": "manager", "output": output["decision"]},
            {"agent": "ad_copywriting", "output": output["output"]},
            {"agent": "compliance", "output": output.get("compliance", {"status": "pass"})},
        ],
    }
