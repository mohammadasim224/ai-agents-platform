from __future__ import annotations

from backend.database.database import get_task, list_tasks
from backend.services.generation import generate_and_record


def enqueue_task(
    project_id: str,
    prompt: str,
    agent: str | None = None,
    *,
    attachment_ids: list[str] | None = None,
) -> dict:
    """Run the chain of command and persist the outcome as a task.

    The `agent` argument is accepted for API compatibility but is ignored: routing
    is the manager's responsibility and is never overridden by a caller.
    """
    return generate_and_record(prompt, project_id, attachment_ids=attachment_ids)


def get_task_status(task_id: str) -> dict:
    task = get_task(task_id)
    if not task:
        return {"status": "not_found"}
    return task


def list_project_tasks(project_id: str) -> list[dict]:
    return list_tasks(project_id)
