from __future__ import annotations

from fastapi import APIRouter

from backend.orchestrator import run_pipeline

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/team-campaign")
async def team_campaign(payload: dict):
    """Run a request through the full chain of command.

    Returns the manager's final answer plus the stage-by-stage trace so the caller
    can see how the work moved through the organization. On failure the response
    carries an `error` payload rather than a substituted answer.
    """
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        return {
            "workflow": "team-campaign",
            "status": "error",
            "results": [],
            "error": {
                "code": "empty_prompt",
                "title": "No request was provided.",
                "message": "This workflow needs a prompt describing the campaign.",
                "hint": "Send `prompt` with the campaign request.",
                "stage": "request",
                "details": {},
            },
        }

    attachment_ids = payload.get("attachment_ids") or []
    project_id = payload.get("project_id", "demo-project")
    result = run_pipeline(prompt, project_id=project_id, attachment_ids=attachment_ids)
    return {
        "workflow": "team-campaign",
        **result.to_dict(),
    }
