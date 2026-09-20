"""The orchestrator: runs the full chain of command for one request.

Flow for every request:

    manager.triage            -> which department(s) own this?
    manager.rewrite           -> a precise brief per department
    head.plan                 -> subtasks + which specialist owns each
    specialist.run            -> the actual deliverable (with backtesting if required)
    head.verify               -> does the deliverable answer the subtask?
    head.combine              -> one department answer
    manager.finalize          -> one user-facing answer (+ downloadable artifact)

Every stage can fail with a typed `PipelineError`. The orchestrator catches those
and returns an honest, explanatory response instead of a degraded answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.agents import manager as manager_agent
from backend.agents.departments import head as head_agent
from backend.agents.registry import get_department, get_specialist
from backend.agents.specialists import runner as specialist_runner
from backend.errors import (
    AttachmentError,
    ComplianceError,
    PipelineError,
    StageTrace,
)
from backend.evaluations.metrics import run_backtest
from backend.knowledge.ingestion import ingest_knowledge
from backend.knowledge.retrieval import render_context, retrieve_for_categories
from backend.services.artifacts import create_artifact, should_attach_artifact
from backend.services.attachments import build_attachment_context, summarize_attachments
from backend.services.compliance import check_compliance

# A subtask may be rejected for a compliance violation, a failed backtest, or a
# failed head verification. Each rejection buys one more revision attempt.
MAX_REVISIONS_PER_SUBTASK = 3


@dataclass
class PipelineResult:
    """The complete outcome of a request, including the audit trail."""

    status: str
    message: str
    body: str = ""
    departments: list[str] = field(default_factory=list)
    trace: list[StageTrace] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    backtests: list[dict[str, Any]] = field(default_factory=list)
    compliance: dict[str, Any] = field(default_factory=dict)
    knowledge_used: int = 0
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "output": self.body,
            "departments": self.departments,
            "trace": [step.to_dict() for step in self.trace],
            "artifacts": self.artifacts,
            "backtests": self.backtests,
            "compliance": self.compliance,
            "knowledge_used": self.knowledge_used,
            "error": self.error,
        }


class Orchestrator:
    """Runs the chain of command for a single user request."""

    def __init__(self, project_id: str = "demo-project") -> None:
        self.project_id = project_id
        self._chunks: list[dict[str, Any]] | None = None

    @property
    def chunks(self) -> list[dict[str, Any]]:
        if self._chunks is None:
            from backend.config import KNOWLEDGE_DIR

            self._chunks = ingest_knowledge(KNOWLEDGE_DIR)
        return self._chunks

    # ------------------------------------------------------------------ public

    def run(self, user_request: str, attachment_ids: list[str] | None = None) -> PipelineResult:
        """Run the full pipeline, converting failures into honest messages."""
        trace: list[StageTrace] = []
        attachment_context = ""
        attachment_summary = ""

        try:
            attachment_context, attachment_summary = self._load_attachments(attachment_ids or [])
        except PipelineError as exc:
            trace.append(
                StageTrace(
                    stage="attachments",
                    agent="manager",
                    status="error",
                    summary=exc.message,
                )
            )
            return self._error_result(exc, trace)

        try:
            return self._execute(user_request, attachment_context, attachment_summary, trace)
        except PipelineError as exc:
            trace.append(
                StageTrace(
                    stage=exc.stage,
                    agent=self._agent_for_stage(exc.stage),
                    status="error",
                    summary=exc.message,
                    details=exc.details,
                )
            )
            return self._error_result(exc, trace)
        except Exception as exc:  # noqa: BLE001 - last-resort guard for unexpected faults
            trace.append(
                StageTrace(
                    stage="unexpected",
                    agent="manager",
                    status="error",
                    summary=f"Unexpected failure: {exc}",
                )
            )
            return PipelineResult(
                status="error",
                message="The request failed unexpectedly.",
                body=str(exc),
                trace=trace,
                error={
                    "code": "unexpected_error",
                    "title": "The request failed unexpectedly.",
                    "message": str(exc),
                    "hint": "Retry the request. If it keeps failing, check the backend logs.",
                    "stage": "unexpected",
                    "details": {},
                },
            )

    # --------------------------------------------------------------- internals

    def _execute(
        self,
        user_request: str,
        attachment_context: str,
        attachment_summary: str,
        trace: list[StageTrace],
    ) -> PipelineResult:
        # 1. Manager triage -----------------------------------------------------
        triage = manager_agent.triage(user_request, attachment_summary=attachment_summary)
        trace.append(
            StageTrace(
                stage="triage",
                agent="manager",
                status="ok",
                summary=(
                    f"Assigned to {', '.join(triage.departments)} "
                    f"(confidence {triage.confidence:.2f})."
                ),
                details=triage.to_dict(),
            )
        )

        department_answers: list[dict[str, Any]] = []
        backtests: list[dict[str, Any]] = []
        knowledge_used = 0

        # 2. One pass per department -------------------------------------------
        for department_name in triage.departments:
            department = get_department(department_name)

            brief = manager_agent.rewrite_for_department(
                user_request,
                department_name,
                attachment_summary=attachment_summary,
                extra_context=attachment_context[:4000] if attachment_context else "",
            )
            brief_block = brief.as_prompt_block()
            trace.append(
                StageTrace(
                    stage="rewrite",
                    agent=f"{department_name}_head",
                    status="ok",
                    summary=brief.objective,
                    details=brief.to_dict(),
                )
            )

            business_context = self._business_context(user_request)
            plan = head_agent.plan(
                department,
                brief_block,
                business_context=business_context,
            )
            trace.append(
                StageTrace(
                    stage="plan",
                    agent=f"{department_name}_head",
                    status="ok",
                    summary=(
                        f"{len(plan.subtasks)} subtask(s): "
                        + ", ".join(subtask.specialist for subtask in plan.subtasks)
                    ),
                    details=plan.to_dict(),
                )
            )

            results: list[dict[str, Any]] = []

            for subtask in plan.subtasks:
                specialist = head_agent.get_specialist_or_raise(department, subtask.specialist)
                retrieved = retrieve_for_categories(
                    f"{subtask.instruction} {brief.objective}",
                    self.chunks,
                    specialist.knowledge_categories,
                )
                knowledge_used += len(retrieved)
                retrieved_text = render_context(retrieved)

                deliverable = None
                revision_notes = ""
                failure_reason = ""

                for attempt in range(1, MAX_REVISIONS_PER_SUBTASK + 2):
                    try:
                        deliverable = specialist_runner.run(
                            specialist,
                            subtask.instruction,
                            brief_block=brief_block,
                            shared_context=plan.shared_context,
                            business_context=business_context,
                            retrieved_knowledge=retrieved_text,
                            attachment_context=attachment_context,
                            revision_notes=revision_notes,
                        )
                    except PipelineError as exc:
                        failure_reason = exc.message
                        trace.append(
                            StageTrace(
                                stage="specialist",
                                agent=specialist.name,
                                status="error",
                                summary=f"Attempt {attempt} failed: {exc.message}",
                                details=exc.details,
                            )
                        )
                        revision_notes = f"The previous attempt failed: {exc.message}"
                        continue

                    # The specialist produced a deliverable. Log it before the
                    # checks that follow so the trace reads chronologically.
                    trace.append(
                        StageTrace(
                            stage="specialist",
                            agent=specialist.name,
                            status="ok",
                            summary=(
                                f"Attempt {attempt}: produced "
                                f"{len(deliverable.content)} characters."
                            ),
                            details=deliverable.metrics,
                        )
                    )

                    # Quality gate: sales scripts must clear a measured backtest.
                    if specialist.requires_backtest:
                        backtest = run_backtest(
                            specialist.name,
                            deliverable.content,
                            call_context=f"{brief.objective}\n{plan.shared_context}",
                        )
                        backtests.append(backtest.to_dict())
                        trace.append(
                            StageTrace(
                                stage="backtest",
                                agent=specialist.name,
                                status="ok" if backtest.passed else "error",
                                summary=backtest.summary(),
                                details=backtest.to_dict(),
                            )
                        )
                        if not backtest.passed:
                            failure_reason = backtest.summary()
                            revision_notes = (
                                "Your script did not reach the conversion target. "
                                "Fix these specific gaps and return the full revised script:\n"
                                f"{backtest.revision_notes}"
                            )
                            deliverable = None
                            continue

                    # Compliance gate. A violation is a fixable defect, not a
                    # dead end, so the specialist gets a revision attempt.
                    compliance = check_compliance(deliverable.content)
                    if compliance["status"] == "blocked":
                        blocked_reasons = "; ".join(
                            f"{issue['reason']} (found \"{issue['match']}\")"
                            for issue in compliance["issues"][:4]
                        )
                        trace.append(
                            StageTrace(
                                stage="compliance",
                                agent=specialist.name,
                                status="error",
                                summary=f"Attempt {attempt} blocked: {blocked_reasons[:120]}",
                                details=compliance,
                            )
                        )
                        failure_reason = f"Blocked by compliance rules: {blocked_reasons}"
                        revision_notes = (
                            "Your deliverable violated mandatory compliance rules and was "
                            "rejected. Rewrite the affected lines and return the full revised "
                            "deliverable.\n\nViolations:\n"
                            + "\n".join(f"- {issue['reason']}" for issue in compliance["issues"][:6])
                            + "\n\nApply these fixes:\n"
                            + "\n".join(f"- {note}" for note in compliance.get("remediation", []))
                        )
                        deliverable = None
                        continue

                    verification = head_agent.verify_subtask(
                        department,
                        subtask,
                        deliverable.content,
                        brief_block=brief_block,
                    )
                    trace.append(
                        StageTrace(
                            stage="verify",
                            agent=f"{department_name}_head",
                            status="ok" if verification["passed"] else "error",
                            summary=verification["reason"]
                            or ("Deliverable accepted." if verification["passed"] else "Deliverable rejected."),
                            details=verification,
                        )
                    )

                    if verification["passed"]:
                        break

                    failure_reason = verification["reason"] or "The head rejected the deliverable."
                    revision_notes = verification["fix_instruction"] or "\n".join(
                        f"- {issue}" for issue in verification["issues"]
                    )
                    deliverable = None

                if deliverable is None:
                    results.append(
                        {
                            "specialist": specialist.name,
                            "status": "error",
                            "content": "",
                            "message": failure_reason or "The specialist could not complete the subtask.",
                        }
                    )
                    continue

                results.append(
                    {
                        "specialist": specialist.name,
                        "status": "ok",
                        "content": deliverable.content,
                        "message": "",
                        "metrics": deliverable.metrics,
                    }
                )

            verified = [result for result in results if result["status"] == "ok"]
            if not verified:
                department_answers.append(
                    {
                        "department": department_name,
                        "status": "error",
                        "content": "",
                        "message": "; ".join(
                            result["message"] for result in results if result.get("message")
                        )
                        or "No specialist produced a usable deliverable.",
                        "subtask_results": results,
                    }
                )
                continue

            answer = head_agent.combine(department, brief_block, verified)
            trace.append(
                StageTrace(
                    stage="combine",
                    agent=f"{department_name}_head",
                    status="ok",
                    summary=answer.message,
                    details={"subtasks": len(verified)},
                )
            )
            department_answers.append(answer.to_dict())

        # 3. Manager finalize ---------------------------------------------------
        final = manager_agent.finalize(user_request, department_answers)
        trace.append(
            StageTrace(
                stage="finalize",
                agent="manager",
                status="ok" if final.status == "ok" else "error",
                summary=final.message,
            )
        )

        if final.status != "ok":
            return PipelineResult(
                status="error",
                message=final.message,
                body=final.body,
                departments=triage.departments,
                trace=trace,
                backtests=backtests,
                knowledge_used=knowledge_used,
                error={
                    "code": "no_verified_answer",
                    "title": final.message,
                    "message": final.body,
                    "hint": "Add more detail about the exact deliverable you need.",
                    "stage": "finalize",
                    "details": {"departments": triage.departments},
                },
            )

        overall_compliance = check_compliance(final.body)
        if overall_compliance["status"] == "blocked":
            trace.append(
                StageTrace(
                    stage="compliance",
                    agent="manager",
                    status="error",
                    summary="Final answer blocked by compliance rules.",
                    details=overall_compliance,
                )
            )
            exc = ComplianceError(
                "The final answer violated mandatory compliance rules.",
                stage="compliance",
                details=overall_compliance,
            )
            return self._error_result(exc, trace, departments=triage.departments)

        # 4. Manager packages the deliverable as a downloadable file ------------
        artifacts = self._package_artifacts(
            user_request, final.body, triage.departments, department_answers, trace
        )

        return PipelineResult(
            status="ok",
            message=final.message,
            body=final.body,
            departments=triage.departments,
            trace=trace,
            artifacts=artifacts,
            backtests=backtests,
            compliance=overall_compliance,
            knowledge_used=knowledge_used,
        )

    def _package_artifacts(
        self,
        user_request: str,
        body: str,
        departments: list[str],
        department_answers: list[dict[str, Any]],
        trace: list[StageTrace],
    ) -> list[dict[str, Any]]:
        """Create downloadable files for substantial deliverables.

        Only verified, non-empty answers become artifacts, and a failure here never
        invalidates the answer text that the user already has.
        """
        if not should_attach_artifact(body):
            return []

        extension = self._artifact_extension(departments, department_answers)
        title = self._artifact_title(user_request, departments)

        try:
            artifact = create_artifact(body, title=title, extension=extension)
        except PipelineError as exc:
            trace.append(
                StageTrace(
                    stage="artifact",
                    agent="manager",
                    status="error",
                    summary=f"Deliverable file was not created: {exc.message}",
                )
            )
            return []

        trace.append(
            StageTrace(
                stage="artifact",
                agent="manager",
                status="ok",
                summary=f"Attached downloadable file `{artifact.filename}`.",
                details=artifact.to_dict(),
            )
        )
        return [artifact.to_dict()]

    def _artifact_extension(
        self, departments: list[str], department_answers: list[dict[str, Any]]
    ) -> str:
        for answer in department_answers:
            for result in answer.get("subtask_results", []):
                specialist_name = result.get("specialist")
                if not specialist_name or result.get("status") != "ok":
                    continue
                try:
                    return get_specialist(specialist_name).deliverable_extension
                except PipelineError:
                    continue
        return "txt"

    def _artifact_title(self, user_request: str, departments: list[str]) -> str:
        cleaned = " ".join(user_request.split())
        words = [word for word in cleaned.split(" ") if word]
        title = " ".join(words[:8])
        if departments:
            return f"{'-'.join(departments)}-{title}" if title else "-".join(departments)
        return title or "deliverable"

    def _load_attachments(self, attachment_ids: list[str]) -> tuple[str, str]:
        if not attachment_ids:
            return "", ""
        try:
            return (
                build_attachment_context(attachment_ids),
                summarize_attachments(attachment_ids),
            )
        except PipelineError:
            raise
        except Exception as exc:  # noqa: BLE001 - wrap unexpected reader faults
            raise AttachmentError(
                f"Could not read the attached files: {exc}",
                stage="attachments",
                details={"attachment_ids": attachment_ids},
            ) from exc

    def _business_context(self, query: str) -> str:
        """Always give every agent the same grounding in the business files."""
        chunks = retrieve_for_categories(
            query,
            self.chunks,
            ("business",),
            per_category=3,
            total_limit=4,
        )
        return render_context(chunks, max_chars=4000)

    def _agent_for_stage(self, stage: str) -> str:
        if stage in {"triage", "rewrite", "finalize", "attachments"}:
            return "manager"
        if stage in {"planning", "combine"}:
            return "department_head"
        if stage == "backtest":
            return "lead_simulator"
        if stage == "compliance":
            return "compliance"
        return "specialist"

    def _error_result(
        self,
        exc: PipelineError,
        trace: list[StageTrace],
        *,
        departments: list[str] | None = None,
    ) -> PipelineResult:
        return PipelineResult(
            status="error",
            message=exc.user_title,
            body=exc.message,
            departments=departments or [],
            trace=trace,
            error=exc.to_payload(),
        )


def run_pipeline(
    user_request: str,
    *,
    project_id: str = "demo-project",
    attachment_ids: list[str] | None = None,
) -> PipelineResult:
    """Convenience entry point used by the API and services layers."""
    return Orchestrator(project_id).run(user_request, attachment_ids)
