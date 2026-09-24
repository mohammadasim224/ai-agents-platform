from __future__ import annotations

from contextlib import asynccontextmanager

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
from backend.services.queue import shutdown as shutdown_queue, start_worker

# Importing jobs registers the queue handlers (generate, build-knowledge).
from backend.services import jobs  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background queue worker with the server.

    Jobs left `queued` by a restart are picked up as soon as the server starts,
    rather than waiting for someone to submit a new job. The worker is stopped on
    shutdown so the process exits cleanly.
    """
    start_worker()
    try:
        yield
    finally:
        shutdown_queue()


app = FastAPI(title=PROJECT_NAME, lifespan=lifespan)
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
def generate(req: GenerateRequest):
    """Run the chain of command and return the manager's final answer.

    The response always includes a `status` of `"ok"` or `"error"`. An `"error"`
    response carries an `error` payload explaining what failed, so the client can
    show an honest message instead of a degraded answer.

    Declared `def` (not `async def`) on purpose: the pipeline is slow, blocking
    work, so FastAPI runs it in its threadpool. An `async def` route would run it
    on the event loop and freeze every other request (including `/health`) for the
    whole duration of the job.
    """
    result = run_pipeline(
        req.prompt,
        project_id=req.project_id,
        attachment_ids=req.attachment_ids,
    )
    return result.to_dict()
