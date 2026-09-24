"""Specialist agents: the workers that produce deliverables.

Every specialist runs the same way:

1. Build a system prompt from its own `/prompts` file, its assigned knowledge
   files, and retrieved knowledge excerpts relevant to the instruction.
2. Produce a deliverable.
3. Reject placeholder or empty output rather than passing it upward.
4. If the specialist owns a measurable quality gate (backtesting), run it before
   reporting success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from backend.agents.registry import Specialist
from backend.config import MIN_DELIVERABLE_CHARS
from backend.errors import SpecialistError
from backend.llm.router import route_prompt
from backend.prompts.loader import compose_system_prompt

ERROR_PREFIX = "ERROR:"

PLACEHOLDER_MARKERS = (
    "[insert",
    "[your ",
    "<insert",
    "lorem ipsum",
    "todo:",
    "tbd",
    "placeholder",
)


@dataclass
class Deliverable:
    """A specialist's finished work."""

    specialist: str
    department: str
    content: str
    status: str = "ok"
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "specialist": self.specialist,
            "department": self.department,
            "content": self.content,
            "status": self.status,
            "message": self.message,
            "metrics": self.metrics,
        }


def _validate_deliverable(specialist: Specialist, content: str) -> None:
    """Reject output that is empty, an explicit error, or obvious filler."""
    text = content.strip()

    if not text:
        raise SpecialistError(
            f"{specialist.title} returned an empty deliverable.",
            stage="specialist",
            details={"specialist": specialist.name},
        )

    if text.upper().startswith(ERROR_PREFIX):
        raise SpecialistError(
            text[len(ERROR_PREFIX) :].strip() or f"{specialist.title} could not complete the task.",
            stage="specialist",
            details={"specialist": specialist.name},
        )

    if len(text) < MIN_DELIVERABLE_CHARS:
        raise SpecialistError(
            f"{specialist.title} returned a deliverable that is too short to be usable "
            f"({len(text)} characters, minimum {MIN_DELIVERABLE_CHARS}).",
            stage="specialist",
            details={"specialist": specialist.name, "length": len(text)},
        )

    lowered = text.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker in lowered:
            raise SpecialistError(
                f"{specialist.title} returned placeholder text instead of finished work "
                f"(found `{marker}`).",
                stage="specialist",
                details={"specialist": specialist.name, "marker": marker},
            )


def run(
    specialist: Specialist,
    instruction: str,
    *,
    brief_block: str = "",
    shared_context: str = "",
    business_context: str = "",
    retrieved_knowledge: str = "",
    attachment_context: str = "",
    extra_rules: str = "",
    revision_notes: str = "",
    on_delta: Callable[[str], None] | None = None,
) -> Deliverable:
    """Run a specialist agent and return its verified deliverable.

    `on_delta` receives the deliverable text as it is generated, so the caller
    can stream the work live. It is optional: without it the call is a normal
    blocking request.
    """
    system_prompt = compose_system_prompt(
        specialist.prompt,
        knowledge_categories=specialist.knowledge_categories,
        output="text",
        knowledge_text=retrieved_knowledge,
        extra_rules=extra_rules,
    )

    sections: list[str] = []
    if brief_block.strip():
        sections.append(f"## Brief From Your Head Of Department\n{brief_block.strip()}")
    sections.append(f"## Your Assigned Subtask\n{instruction.strip()}")
    if shared_context.strip():
        sections.append(f"## Shared Department Context\n{shared_context.strip()}")
    if business_context.strip():
        sections.append(f"## Business Context\n{business_context.strip()}")
    if attachment_context.strip():
        sections.append(f"## Attached Source Material\n{attachment_context.strip()}")
    if revision_notes.strip():
        sections.append(
            "## Revision Required\n"
            "Your previous deliverable was rejected. Fix exactly these issues:\n"
            f"{revision_notes.strip()}"
        )

    prompt = "\n\n".join(sections)
    result = route_prompt(
        specialist.department,
        prompt,
        system_prompt=system_prompt,
        temperature=0.5,
        on_delta=on_delta,
    )
    content = str(result.get("content", "")).strip()
    _validate_deliverable(specialist, content)

    return Deliverable(
        specialist=specialist.name,
        department=specialist.department,
        content=content,
        metrics={
            "length": len(content),
            "model": result.get("model"),
            "latency_ms": result.get("latency_ms"),
            "attempts": result.get("attempts"),
        },
    )
