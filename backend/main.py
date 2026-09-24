from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.api.agents import router as agents_router
from backend.api.artifacts import router as artifacts_router
from backend.api.auth import router as auth_router
from backend.api.conversations import router as conversations_router
from backend.api.evaluations import router as evaluations_router
from backend.api.health import router as health_router
from backend.api.knowledge import router as knowledge_router
from backend.api.memory import router as memory_router
from backend.api.openai_compat import router as openai_compat_router
from backend.api.profiles import router as profiles_router
from backend.api.projects import router as projects_router
from backend.api.queue import router as queue_router
from backend.api.tasks import router as tasks_router
from backend.api.workflows import router as workflows_router
from backend.api.uploads import router as uploads_router
from backend.orchestrator import run_pipeline
from backend.config import FRONTEND_ORIGINS, PROJECT_NAME

# Importing jobs registers the queue handlers (generate, build-knowledge).
from backend.services import jobs  # noqa: F401

app = FastAPI(title=PROJECT_NAME)
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
app.include_router(profiles_router)
app.include_router(conversations_router)
app.include_router(memory_router)
app.include_router(queue_router)
app.include_router(agents_router)
app.include_router(tasks_router)
app.include_router(knowledge_router)
app.include_router(evaluations_router)
app.include_router(workflows_router)
app.include_router(uploads_router)
app.include_router(artifacts_router)
# OpenAI-compatible surface (`/v1/models`, `/v1/chat/completions`) for editor and
# SDK clients that probe the server with the OpenAI wire format.
app.include_router(openai_compat_router)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    project_id: str = "demo-project"
    attachment_ids: list[str] = Field(default_factory=list)


@app.post("/generate")
async def generate(req: GenerateRequest):
    """Run the chain of command and return the manager's final answer.

    The response always includes a `status` of `"ok"` or `"error"`. An `"error"`
    response carries an `error` payload explaining what failed, so the client can
    show an honest message instead of a degraded answer.
    """
    result = run_pipeline(
        req.prompt,
        project_id=req.project_id,
        attachment_ids=req.attachment_ids,
    )
    return result.to_dict()
