"""Generation service.

Thin adapter between the API layer and the orchestrator. The orchestrator owns
the chain of command; this module only handles persistence of the result.
"""

from __future__ import annotations

from typing import Any

from backend.database.database import create_generation, create_task
from backend.orchestrator import PipelineResult, run_pipeline


def generate_for_prompt(
    prompt: str,
    project_id: str = "demo-project",
    *,
    attachment_ids: list[str] | None = None,
) -> PipelineResult:
    """Run the full chain of command for a prompt.

    Returns a `PipelineResult`. Failures are represented as a result with
    `status == "error"` and an explanatory `error` payload, never as a fabricated
    answer.
    """
    return run_pipeline(prompt, project_id=project_id, attachment_ids=attachment_ids)


def generate_and_record(
    prompt: str,
    project_id: str = "demo-project",
    *,
    attachment_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run the pipeline and persist the task plus generation record."""
    result = run_pipeline(prompt, project_id=project_id, attachment_ids=attachment_ids)

    department = result.departments[0] if result.departments else "unassigned"
    task = create_task(project_id=project_id, agent=department, input_text=prompt)

    generation = create_generation(
        task_id=task["id"],
        model="chain-of-command",
        prompt_version="v2",
        output=result.body,
        input_tokens=0,
        output_tokens=0,
        latency=0,
    )

    return {
        "task": task,
        "generation": generation,
        **result.to_dict(),
    }
