from __future__ import annotations

from backend.agents.manager import decide_agent
from backend.database.database import create_generation, create_task, get_task, list_tasks
from backend.services.generation import generate_for_prompt


def enqueue_task(project_id: str, prompt: str, agent: str | None = None) -> dict:
    decision = decide_agent(prompt)
    selected_agent = agent or decision.get("agent", "ad_copywriting")
    task = create_task(project_id=project_id, agent=selected_agent, input_text=prompt)
    result = generate_for_prompt(prompt, project_id)
    generation = create_generation(
        task_id=task["id"],
        model="openrouter/free",
        prompt_version="v1",
        output=result["output"],
        input_tokens=0,
        output_tokens=0,
        latency=0,
    )
    return {
        "task": task,
        "decision": decision,
        "generation": generation,
        "output": result["output"],
    }


def get_task_status(task_id: str) -> dict:
    task = get_task(task_id)
    if not task:
        return {"status": "not_found"}
    return task


def list_project_tasks(project_id: str) -> list[dict]:
    return list_tasks(project_id)
