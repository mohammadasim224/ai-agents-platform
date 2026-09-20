from __future__ import annotations

from fastapi import APIRouter

from backend.services.tasks import enqueue_task, get_task_status, list_project_tasks

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("")
async def create_task(payload: dict):
    project_id = payload.get("project_id", "demo-project")
    prompt = payload.get("input") or payload.get("prompt") or "Write a marketing ad."
    return enqueue_task(project_id, prompt, payload.get("agent"))


@router.get("")
async def tasks_list():
    return list_project_tasks("demo-project")


@router.get("/{task_id}")
async def get_task(task_id: str):
    return get_task_status(task_id)
