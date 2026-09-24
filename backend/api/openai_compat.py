"""OpenAI-compatible surface (`/v1/...`).

Editors, IDE assistants, and SDK clients speak the OpenAI wire format and probe
`/v1/models` (and often `/v1/chat/completions`) on startup. Without these routes
they see a 404 from this server.

This module is a thin adapter, not a second implementation. It exists so such
clients can talk to the platform, and everything it does is delegated to the
real chain of command:

- `GET  /v1/models`            -> the provider's model catalog, or the models
                                  this platform is configured to run.
- `POST /v1/chat/completions`  -> `run_pipeline`, returned in OpenAI shape.

Honesty rule: a pipeline failure is reported as an OpenAI-style error envelope
with a real status code, never as an empty or degraded completion.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from backend.config import DEFAULT_MODEL, PROJECT_NAME
from backend.errors import PipelineError
from backend.llm import router as llm_router
from backend.orchestrator import run_pipeline

# The OpenAI wire format is versioned in the path, so the prefix lives here.
router = APIRouter(prefix="/v1", tags=["openai-compatible"])

# We do not emit incremental deltas: the pipeline produces one verified answer,
# not a token stream. `stream: true` is rejected honestly instead of being
# silently ignored.
SUPPORTED_ROLES = {"system", "user"}

# Non-standard, additive metadata. OpenAI clients ignore unknown fields, while
# anything built for this platform can read the audit trail directly.
META_KEY = "x_voltaik"


def _error(
    message: str,
    *,
    status_code: int,
    code: str = "invalid_request_error",
    param: str | None = None,
    hint: str | None = None,
) -> JSONResponse:
    """Return an OpenAI-shaped error envelope."""
    error: dict[str, Any] = {
        "message": message,
        "type": code,
        "code": code,
        "param": param,
    }
    if hint:
        error["hint"] = hint
    return JSONResponse(status_code=status_code, content={"error": error})


def _extract_messages(messages: Any) -> tuple[str | None, str, str | None]:
    """Validate a chat payload and split it into (system, user, error).

    Only `system` and `user` turns are supported. Assistant/tool turns are
    rejected rather than silently dropped, because dropping them would change
    the meaning of the request.
    """
    if not isinstance(messages, list) or not messages:
        return None, "", "`messages` must be a non-empty array."

    systems: list[str] = []
    last_user: str | None = None

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            return None, "", f"`messages[{index}]` must be an object."
        role = message.get("role")
        if role not in SUPPORTED_ROLES:
            return (
                None,
                "",
                f"`messages[{index}].role` is '{role}'. This endpoint supports "
                "only 'system' and 'user' turns.",
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return None, "", f"`messages[{index}].content` must be a non-empty string."
        if role == "system":
            systems.append(content.strip())
        else:
            last_user = content.strip()

    if not last_user:
        return None, "", "`messages` must contain at least one 'user' turn."

    return ("\n\n".join(systems) or None), last_user, None


@router.get("/models")
async def list_models_route():
    """List models in the OpenAI `{"object": "list", "data": [...]}` shape.

    The provider's catalog is preferred. When the provider cannot be listed the
    endpoint falls back to the models this platform is configured to run, so an
    editor can still start up; `x_voltaik.source` says which was used.
    """
    source = "provider"
    try:
        models = llm_router.list_models()
    except PipelineError as exc:
        source = "configured"
        models = [
            {
                "id": model,
                "name": model,
                "context_length": None,
                "owned_by": model.split("/")[0] or "openrouter",
            }
            for model in llm_router.configured_models()
        ]
        configured_meta: dict[str, Any] = {"reason": exc.message}
    else:
        configured_meta = {}

    data = [
        {
            "id": model["id"],
            "object": "model",
            "created": 0,
            "owned_by": model.get("owned_by") or "openrouter",
            **({"name": model["name"]} if model.get("name") else {}),
            **(
                {"context_length": model["context_length"]}
                if model.get("context_length")
                else {}
            ),
            **({"pricing": model["pricing"]} if model.get("pricing") else {}),
        }
        for model in models
    ]

    return {
        "object": "list",
        "data": data,
        META_KEY: {
            "platform": PROJECT_NAME,
            "source": source,
            "default_model": DEFAULT_MODEL,
            **configured_meta,
        },
    }


@router.post("/chat/completions")
async def chat_completions_route(payload: dict):
    """Run the chain of command and return an OpenAI-shaped completion.

    The request is routed through the same pipeline as the UI, so responses are
    verified work with an audit trail attached under `x_voltaik`.
    """
    if not isinstance(payload, dict):
        return _error("The request body must be a JSON object.", status_code=400)

    if payload.get("stream"):
        return _error(
            "Streaming is not supported by this endpoint.",
            status_code=400,
            code="unsupported_parameter",
            param="stream",
            hint="Omit `stream` or set it to false; the platform returns one verified answer.",
        )

    system_prompt, prompt, problem = _extract_messages(payload.get("messages"))
    if problem:
        return _error(problem, status_code=400, param="messages")

    tools = payload.get("tools")
    if tools:
        return _error(
            "Tool/function calling is not supported by this endpoint.",
            status_code=400,
            code="unsupported_parameter",
            param="tools",
            hint="Send a plain user message; routing to departments is automatic.",
        )

    model = payload.get("model") or DEFAULT_MODEL
    project_id = payload.get("project_id") or "demo-project"

    request_text = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"

    try:
        result = await run_in_threadpool(
            run_pipeline,
            request_text,
            project_id=str(project_id),
        )
    except PipelineError as exc:
        payload_error = exc.to_payload()
        return _error(
            payload_error["message"],
            status_code=502,
            code=payload_error["code"],
            hint=payload_error.get("hint"),
        )

    body = result.to_dict()

    if body.get("status") != "ok":
        error_info = body.get("error") or {}
        return _error(
            error_info.get("message") or body.get("message") or "The request failed.",
            status_code=502,
            code=error_info.get("code") or "pipeline_error",
            hint=error_info.get("hint"),
        )

    content = body.get("output") or body.get("message") or ""

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        # Token accounting is not reported by the pipeline, so zeroes are used
        # rather than an invented count.
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        META_KEY: {
            "platform": PROJECT_NAME,
            "message": body.get("message"),
            "departments": body.get("departments", []),
            "knowledge_used": body.get("knowledge_used", 0),
            "artifacts": body.get("artifacts", []),
            "backtests": body.get("backtests", []),
            "compliance": body.get("compliance", {}),
            "trace": body.get("trace", []),
        },
    }
