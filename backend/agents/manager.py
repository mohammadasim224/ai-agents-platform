from __future__ import annotations

import json

from backend.llm.router import route_prompt


def decide_agent(user_request: str) -> dict:
    system_prompt = """
You are an orchestration router for an AI business team.
Return valid JSON only.

Decide which department and agent should handle the task.
Available routes:
- marketing -> ad_copywriting, ad_scripting
- sales -> appointment_setting, closing, lead_simulation
- automation -> lead_nurturing, lead_reminding
- evaluation -> roleplay_evaluation

Use the user's request to select one route.
If uncertain, prefer the most likely department and mark needs_clarification as true.
"""
    try:
        result = route_prompt(
            "manager",
            f"User request: {user_request}\n\nReturn JSON with keys: department, agent, task_type, needs_clarification.",
            system_prompt=system_prompt,
        )
    except RuntimeError as exc:
        return {
            "department": "marketing",
            "agent": "ad_copywriting",
            "task_type": "general_request",
            "needs_clarification": True,
            "provider_status": str(exc),
        }
    content = result.get("content", "")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "department": "marketing",
            "agent": "ad_copywriting",
            "task_type": "general_request",
            "needs_clarification": True,
            "raw_response": content,
        }
