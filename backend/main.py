from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.api.agents import router as agents_router
from backend.api.auth import router as auth_router
from backend.api.evaluations import router as evaluations_router
from backend.api.health import router as health_router
from backend.api.knowledge import router as knowledge_router
from backend.api.projects import router as projects_router
from backend.api.tasks import router as tasks_router
from backend.api.workflows import router as workflows_router
from backend.services.generation import generate_for_prompt
from backend.config import FRONTEND_ORIGINS

app = FastAPI(title="AI Business Team")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(knowledge_router)
app.include_router(evaluations_router)
app.include_router(workflows_router)


@app.get("/agents")
async def list_agents():
    return [{"id": "manager", "name": "Manager"}, {"id": "marketing", "name": "Marketing"}]


class GenerateRequest(BaseModel):
    prompt: str
    project_id: str = "demo-project"


@app.post("/generate")
async def generate(req: GenerateRequest):
    result = generate_for_prompt(req.prompt, req.project_id)
    return result
