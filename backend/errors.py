"""Typed failure modes for the chain-of-command pipeline.

Design rule: the system must prefer returning an honest, well-formed message or
error over returning a low-quality answer. Every stage raises a typed error when
it cannot produce a verified result, and the orchestrator turns those errors into
a user-facing message that explains what failed and what to do next.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PipelineError(Exception):
    """Base class for every recoverable pipeline failure."""

    code = "pipeline_error"
    user_title = "The request could not be completed."
    user_hint = "Retry the request, or add more detail so the team has what it needs."

    def __init__(
        self,
        message: str,
        *,
        stage: str = "unknown",
        details: dict[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.details = details or {}
        if hint:
            self.user_hint = hint

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.user_title,
            "message": self.message,
            "hint": self.user_hint,
            "stage": self.stage,
            "details": self.details,
        }


class ProviderError(PipelineError):
    """The model provider failed (network, auth, rate limit, bad response)."""

    code = "provider_error"
    user_title = "The language model provider is unavailable."
    user_hint = "Check that OPENROUTER_API_KEY is set in .env and retry."


class RoutingError(PipelineError):
    """The manager could not confidently assign the request to a department.

    This is deliberately fatal. The system must never default to a department,
    because doing so produces off-target work instead of an honest answer.
    """

    code = "routing_error"
    user_title = "No department was assigned to this request."
    user_hint = (
        "Restate the request so its outcome is clear (for example: write an ad, "
        "build a setter script, create a nurture sequence)."
    )


class PlanningError(PipelineError):
    """A department head could not break the task into assignable subtasks."""

    code = "planning_error"
    user_title = "The department could not plan this task."
    user_hint = "Add specifics such as channel, audience, format, and desired outcome."


class SpecialistError(PipelineError):
    """A specialist agent failed to produce a usable deliverable."""

    code = "specialist_error"
    user_title = "A specialist could not complete its assignment."
    user_hint = "Retry, or narrow the request to a single deliverable."


class ValidationError(PipelineError):
    """A head or the manager rejected the work as not answering the request."""

    code = "validation_error"
    user_title = "The produced work did not pass verification."
    user_hint = "Add detail about the exact deliverable and format you expect."


class QualityGateError(PipelineError):
    """A measurable quality bar was not reached (for example a backtest target)."""

    code = "quality_gate_error"
    user_title = "The work did not reach the required quality bar."
    user_hint = "Relax the target, widen the scope, or provide more source material."


class ComplianceError(PipelineError):
    """Output violated a mandatory compliance rule (for example banned claims)."""

    code = "compliance_error"
    user_title = "The work was blocked by compliance rules."
    user_hint = "Review knowledge/marketing/banned_claims.md and adjust the request."


class AttachmentError(PipelineError):
    """A referenced attachment could not be read."""

    code = "attachment_error"
    user_title = "An attached file could not be read."
    user_hint = "Re-upload the file as .txt, .md, .docx, or .pdf."


class JobCancelledError(PipelineError):
    """The user asked for the job to stop and the pipeline honoured it.

    This is not a failure: it is the requested outcome. It is raised at the
    pipeline's checkpoints so the work stops promptly instead of running to
    completion and being discarded.
    """

    code = "cancelled"
    user_title = "The request was cancelled."
    user_hint = "Send the request again whenever you are ready."


class ArtifactError(PipelineError):
    """A downloadable artifact could not be produced."""

    code = "artifact_error"
    user_title = "The deliverable file could not be created."
    user_hint = "Retry the request; the answer text is still available above."


@dataclass
class StageTrace:
    """A single step of the pipeline, surfaced to the user for transparency."""

    stage: str
    agent: str
    status: str
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "agent": self.agent,
            "status": self.status,
            "summary": self.summary,
            "details": self.details,
        }
