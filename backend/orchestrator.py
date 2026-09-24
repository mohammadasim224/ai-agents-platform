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

import contextvars
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.agents import manager as manager_agent
from backend.agents.departments import head as head_agent
from backend.agents.registry import get_department, get_specialist
from backend.agents.specialists import runner as specialist_runner
from backend.config import PIPELINE_DEADLINE_SECONDS, PIPELINE_MAX_WORKERS
from backend.errors import (
    AttachmentError,
    ComplianceError,
    JobCancelledError,
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

# Human-readable label and rough percent-complete for each pipeline stage. The
# percentages are estimates used to show a progress bar, not measurements: the
# pipeline makes a variable number of provider calls per request, so the bar is
# deliberately monotonic and never claims to be exact.
STAGE_PROGRESS: dict[str, tuple[str, float]] = {
    "attachments": ("Reading the attached files", 4),
    "triage": ("Manager is routing your request", 10),
    "rewrite": ("Writing the department briefs", 16),
    "plan": ("Department heads are planning the work", 24),
    "specialist": ("Specialists are producing the deliverable", 50),
    "backtest": ("Backtesting the script against simulated calls", 66),
    "compliance": ("Running the compliance check", 74),
    "verify": ("Department heads are verifying the work", 82),
    "combine": ("Combining the department answers", 90),
    "finalize": ("Manager is finalizing your answer", 96),
    "artifact": ("Packaging the downloadable file", 99),
}

ProgressCallback = Callable[..., None]
# Receives a human-readable line describing what the pipeline is doing right
# now, plus optional structured fields. This is the live commentary channel: it
# is what lets the UI show the actual work (which agent, what it produced, what
# a check found) instead of only a percentage.
ActivityCallback = Callable[..., None]
# Returns True when the user has asked the running job to stop. Checked at stage
# boundaries so a cancelled job stops promptly instead of finishing work that
# will be thrown away.
CancelCheck = Callable[[], bool]


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

    def __init__(
        self,
        project_id: str = "demo-project",
        progress: ProgressCallback | None = None,
        *,
        deadline_seconds: float | None = None,
        cancel_check: CancelCheck | None = None,
        activity: ActivityCallback | None = None,
    ) -> None:
        self.project_id = project_id
        self._progress = progress
        self._activity = activity
        self._cancel_check = cancel_check
        self._percent = 0.0
        self._chunks: list[dict[str, Any]] | None = None
        # A hard wall-clock budget keeps a job from running for tens of minutes.
        # When it is exhausted the pipeline stops starting new work and reports
        # the best verified result it has.
        budget = PIPELINE_DEADLINE_SECONDS if deadline_seconds is None else deadline_seconds
        self._deadline = time.monotonic() + max(1.0, budget)
        # Progress is emitted from worker threads, so the monotonic percent and
        # the callback itself must be guarded.
        self._lock = threading.Lock()

    def _expired(self) -> bool:
        return time.monotonic() >= self._deadline

    def _cancelled(self) -> bool:
        """Whether the user has asked this job to stop.

        A broken cancel check must never fail the job, so a fault is treated as
        "not cancelled" and the pipeline keeps its normal behaviour.
        """
        if self._cancel_check is None:
            return False
        try:
            return bool(self._cancel_check())
        except Exception:  # noqa: BLE001 - a broken check must not break the job
            return False

    def _checkpoint(self) -> None:
        """Stop the pipeline when the user cancelled it.

        Called at stage boundaries, which is where the work is between provider
        calls. A provider call already in flight is allowed to finish: aborting
        it mid-request would leave the queue's bookkeeping inconsistent, and the
        next checkpoint discards its result anyway.
        """
        if self._cancelled():
            raise JobCancelledError(
                "The user cancelled this request.",
                stage="cancelled",
            )

    def _remaining_seconds(self) -> float:
        """Seconds left in the job's wall-clock budget (never negative)."""
        return max(1.0, self._deadline - time.monotonic())

    @staticmethod
    def _submit(pool: ThreadPoolExecutor, task: Callable[[], Any]) -> Any:
        """Submit a no-argument task, propagating the caller's contextvars.

        `ThreadPoolExecutor` does NOT copy the calling thread's contextvars into
        its workers, so a job's progress/activity context (which the queue stores
        in a contextvar) would be invisible inside a department or subtask
        thread. That silently dropped every progress and activity update emitted
        from concurrent work. Copying the context per submission restores it, so
        live updates from worker threads reach the job they belong to.
        """
        context = contextvars.copy_context()
        return pool.submit(context.run, task)

    def _run_parallel(
        self,
        label: str,
        tasks: dict[Any, Callable[[], Any]],
        on_error: Callable[[Any, Exception], Any],
    ) -> list[Any]:
        """Run one task per key, concurrently when there is more than one, and
        return the outcomes in the dict's order.

        Both the department fan-out and the subtask fan-out need the same shape:
        bounded concurrency, keep one failure from sinking the rest, and preserve
        the original order. `on_error(key, exc)` supplies the fallback outcome for
        a task that raised.
        """
        if len(tasks) <= 1:
            futures = None
        else:
            workers = max(1, min(PIPELINE_MAX_WORKERS, len(tasks)))
            pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=label)
            futures = {key: self._submit(pool, task) for key, task in tasks.items()}

        outcomes = []
        try:
            for key, task in tasks.items():
                try:
                    outcomes.append(futures[key].result() if futures else task())
                except Exception as exc:  # noqa: BLE001 - one task must not sink the rest
                    outcomes.append(on_error(key, exc))
        finally:
            if futures:
                pool.shutdown()
        return outcomes

    def _emit(self, stage: str, *, detail: str = "", percent: float | None = None) -> None:
        """Report pipeline progress, never moving the bar backwards.

        Progress reporting is best-effort: a failure here must not fail the
        request, so every exception is swallowed. Safe to call from worker
        threads.
        """
        if self._progress is None:
            return
        label, base = STAGE_PROGRESS.get(stage, (stage, self._percent))
        target = base if percent is None else percent
        with self._lock:
            self._percent = max(self._percent, target)
            current = self._percent
        try:
            self._progress(stage, label, current, detail=detail)
        except Exception:  # noqa: BLE001 - progress must never break the pipeline
            pass

    def _note(
        self,
        message: str,
        *,
        stage: str = "",
        agent: str = "",
        kind: str = "info",
        preview: str | None = None,
    ) -> None:
        """Publish one live activity line, never failing the pipeline.

        This is the streaming channel: it records what is actually happening
        (which agent is working, what it generated, what a check found) so the
        UI can show the work as it happens. Like progress, it is best-effort and
        safe to call from worker threads.
        """
        if self._activity is None:
            return
        try:
            self._activity(message, stage=stage, agent=agent, kind=kind, preview=preview)
        except Exception:  # noqa: BLE001 - activity must never break the pipeline
            pass

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

        if attachment_ids:
            self._emit(
                "attachments",
                detail=f"{len(attachment_ids)} file(s) attached",
            )

        try:
            return self._execute(user_request, attachment_context, attachment_summary, trace)
        except JobCancelledError:
            # Cancellation is the requested outcome, not a failure. It is
            # re-raised so the queue can mark the job `cancelled` instead of
            # recording it as an error the user has to read.
            raise
        except PipelineError as exc:
            # Make the failure visible in the live feed, not only in the final
            # result: while debugging, the reason a stage stopped is the single
            # most useful thing to see as it happens.
            self._note(
                f"{exc.user_title} {exc.message}",
                stage=exc.stage,
                agent=self._agent_for_stage(exc.stage),
                kind="error",
            )
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
        self._checkpoint()
        self._emit("triage")
        self._note("Manager is reading the request and deciding which department owns it.", stage="triage", agent="manager")
        triage = manager_agent.triage(user_request, attachment_summary=attachment_summary)
        self._note(
            f"Routed to {', '.join(triage.departments)} (confidence {triage.confidence:.2f}).",
            stage="triage",
            agent="manager",
            kind="ok",
        )
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

        # Load the knowledge index once on this thread before any worker starts,
        # so concurrent subtasks never race to build it.
        _ = self.chunks

        # 2. One pass per department, run concurrently -------------------------
        # Departments are independent, so they run in a bounded thread pool. A
        # request that spans several departments costs roughly one department of
        # wall-clock time instead of one department per department.
        department_names = list(triage.departments)

        def _department_failed(name: str, exc: Exception) -> tuple[Any, ...]:
            # Surface the failure in the live feed: a department that dies
            # mid-pipeline is exactly what the user needs to see while debugging,
            # not just a stalled progress bar.
            self._note(
                f"The {name} department failed: {exc}",
                stage="department",
                agent=f"{name}_head",
                kind="error",
            )
            return (
                {
                    "department": name,
                    "status": "error",
                    "content": "",
                    "message": f"The {name} department failed: {exc}",
                    "subtask_results": [],
                },
                [],
                [],
                0,
            )

        outcomes = self._run_parallel(
            "department",
            {
                name: lambda name=name: self._run_department(
                    name, user_request, attachment_context, attachment_summary
                )
                for name in department_names
            },
            _department_failed,
        )
        for answer, department_trace, department_backtests, used in outcomes:
            department_answers.append(answer)
            trace.extend(department_trace)
            backtests.extend(department_backtests)
            knowledge_used += used

        # 3. Manager finalize ---------------------------------------------------
        self._checkpoint()
        self._emit("finalize")
        self._note("Manager is assembling the final answer from the department work.", stage="finalize", agent="manager")
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
        self._checkpoint()
        self._emit("artifact")
        self._note("Packaging the deliverable as a downloadable file.", stage="artifact", agent="manager")
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

    # ------------------------------------------------------- department runner

    def _run_department(
        self,
        department_name: str,
        user_request: str,
        attachment_context: str,
        attachment_summary: str,
    ) -> tuple[dict[str, Any], list[StageTrace], list[dict[str, Any]], int]:
        """Run one department end to end.

        Returns the department answer, its trace entries, its backtest records,
        and how many knowledge excerpts it used. Safe to run in a worker thread:
        it only reads shared state and appends to its own local lists.
        """
        department = get_department(department_name)
        trace: list[StageTrace] = []
        backtests: list[dict[str, Any]] = []
        knowledge_used = 0

        # Do not start new department work once the job's budget is spent or the
        # user has cancelled it.
        if self._expired() or self._cancelled():
            return (
                {
                    "department": department_name,
                    "status": "error",
                    "content": "",
                    "message": "The job reached its time budget before this department started.",
                    "subtask_results": [],
                },
                trace,
                backtests,
                knowledge_used,
            )

        self._checkpoint()
        self._emit("rewrite", detail=f"Department: {department_name}")
        self._note(
            f"Writing the brief for the {department_name} department.",
            stage="rewrite",
            agent=f"{department_name}_head",
        )
        brief = manager_agent.rewrite_for_department(
            user_request,
            department_name,
            attachment_summary=attachment_summary,
            extra_context=attachment_context[:4000] if attachment_context else "",
        )
        brief_block = brief.as_prompt_block()
        self._note(
            f"{department_name} brief ready: {brief.objective}",
            stage="rewrite",
            agent=f"{department_name}_head",
            kind="ok",
        )
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
        self._emit("plan", detail=f"Department: {department_name}")
        self._note(
            f"{department_name} head is planning the subtasks.",
            stage="plan",
            agent=f"{department_name}_head",
        )
        plan = head_agent.plan(
            department,
            brief_block,
            business_context=business_context,
        )
        self._note(
            f"{department_name} plan: {len(plan.subtasks)} subtask(s) — "
            + ", ".join(subtask.specialist for subtask in plan.subtasks),
            stage="plan",
            agent=f"{department_name}_head",
            kind="ok",
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

        # Subtasks within a department are independent, so they run concurrently.
        subtasks = list(plan.subtasks)

        def _subtask_failed(subtask: Any, exc: Exception) -> tuple[Any, ...]:
            self._note(
                f"{subtask.specialist} failed: {exc}",
                stage="specialist",
                agent=subtask.specialist,
                kind="error",
            )
            return (
                {
                    "specialist": subtask.specialist,
                    "status": "error",
                    "content": "",
                    "message": str(exc),
                },
                [],
                [],
                0,
            )

        results: list[dict[str, Any]] = []
        outcomes = self._run_parallel(
            "subtask",
            {
                subtask.id: lambda subtask=subtask: self._run_subtask(
                    department,
                    subtask,
                    brief_block,
                    plan.shared_context,
                    business_context,
                    attachment_context,
                )
                for subtask in subtasks
            },
            _subtask_failed,
        )
        for result, subtask_trace, subtask_backtests, used in outcomes:
            results.append(result)
            trace.extend(subtask_trace)
            backtests.extend(subtask_backtests)
            knowledge_used += used

        verified = [result for result in results if result["status"] == "ok"]
        if not verified:
            return (
                {
                    "department": department_name,
                    "status": "error",
                    "content": "",
                    "message": "; ".join(
                        result["message"] for result in results if result.get("message")
                    )
                    or "No specialist produced a usable deliverable.",
                    "subtask_results": results,
                },
                trace,
                backtests,
                knowledge_used,
            )

        answer = head_agent.combine(department, brief_block, verified)
        self._emit("combine", detail=f"Department: {department_name}")
        trace.append(
            StageTrace(
                stage="combine",
                agent=f"{department_name}_head",
                status="ok",
                summary=answer.message,
                details={"subtasks": len(verified)},
            )
        )
        return answer.to_dict(), trace, backtests, knowledge_used

    def _run_subtask(
        self,
        department: Any,
        subtask: Any,
        brief_block: str,
        shared_context: str,
        business_context: str,
        attachment_context: str,
    ) -> tuple[dict[str, Any], list[StageTrace], list[dict[str, Any]], int]:
        """Produce and verify one subtask, revising until it passes or runs out.

        Returns the subtask result, its trace entries, its backtest records, and
        how many knowledge excerpts it used.
        """
        specialist = head_agent.get_specialist_or_raise(department, subtask.specialist)
        self._emit("specialist", detail=f"{specialist.title} is working")
        self._note(
            f"{specialist.title} is working on: {subtask.instruction}",
            stage="specialist",
            agent=specialist.name,
        )
        retrieved = retrieve_for_categories(
            f"{subtask.instruction} {brief_block}",
            self.chunks,
            specialist.knowledge_categories,
        )
        retrieved_text = render_context(retrieved)
        if retrieved:
            self._note(
                f"{specialist.title} pulled {len(retrieved)} knowledge excerpt(s) for grounding.",
                stage="specialist",
                agent=specialist.name,
            )

        trace: list[StageTrace] = []
        backtests: list[dict[str, Any]] = []
        deliverable = None
        revision_notes = ""
        failure_reason = ""

        for attempt in range(1, MAX_REVISIONS_PER_SUBTASK + 2):
            # Stop revising once the job's wall-clock budget is spent or the user
            # cancelled it, so a job cannot run for tens of minutes chasing a
            # stubborn quality gate.
            if self._expired():
                failure_reason = (
                    failure_reason
                    or "The job reached its time budget before the work passed verification."
                )
                break
            self._checkpoint()

            if attempt > 1:
                self._note(
                    f"{specialist.title} is revising (attempt {attempt}).",
                    stage="specialist",
                    agent=specialist.name,
                )

            # Stream the deliverable as it is written. The callback receives the
            # text generated so far, so the UI can show the work appearing live
            # instead of a frozen spinner. It is throttled in the router.
            def _on_delta(text: str, _specialist=specialist) -> None:
                self._note(
                    f"{_specialist.title} is writing...",
                    stage="specialist",
                    agent=_specialist.name,
                    preview=text,
                )

            try:
                deliverable = specialist_runner.run(
                    specialist,
                    subtask.instruction,
                    brief_block=brief_block,
                    shared_context=shared_context,
                    business_context=business_context,
                    retrieved_knowledge=retrieved_text,
                    attachment_context=attachment_context,
                    revision_notes=revision_notes,
                    on_delta=_on_delta,
                )
            except PipelineError as exc:
                failure_reason = exc.message
                self._note(
                    f"{specialist.title} attempt {attempt} failed: {exc.message}",
                    stage="specialist",
                    agent=specialist.name,
                    kind="error",
                )
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

            # The specialist produced a deliverable. Log it before the checks
            # that follow so the trace reads chronologically.
            self._note(
                f"{specialist.title} produced {len(deliverable.content)} characters.",
                stage="specialist",
                agent=specialist.name,
                kind="ok",
            )
            trace.append(
                StageTrace(
                    stage="specialist",
                    agent=specialist.name,
                    status="ok",
                    summary=(
                        f"Attempt {attempt}: produced {len(deliverable.content)} characters."
                    ),
                    details=deliverable.metrics,
                )
            )

            # Quality gate: sales scripts must clear a measured backtest.
            if specialist.requires_backtest:
                self._emit("backtest", detail=f"{specialist.title}")
                self._note(
                    f"Backtesting {specialist.title}'s script against simulated calls.",
                    stage="backtest",
                    agent=specialist.name,
                )
                backtest = run_backtest(
                    specialist.name,
                    deliverable.content,
                    call_context=f"{brief_block}\n{shared_context}",
                    deadline_seconds=self._remaining_seconds(),
                )
                backtests.append(backtest.to_dict())
                self._note(
                    f"Backtest: {backtest.summary()}",
                    stage="backtest",
                    agent=specialist.name,
                    kind="ok" if backtest.passed else "error",
                )
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

            # Compliance gate. A violation is a fixable defect, not a dead end,
            # so the specialist gets a revision attempt.
            self._emit("compliance", detail=f"{specialist.title}")
            self._note(
                f"Running the compliance check on {specialist.title}'s deliverable.",
                stage="compliance",
                agent=specialist.name,
            )
            compliance = check_compliance(deliverable.content)
            if compliance["status"] == "blocked":
                blocked_reasons = "; ".join(
                    f"{issue['reason']} (found \"{issue['match']}\")"
                    for issue in compliance["issues"][:4]
                )
                self._note(
                    f"Compliance blocked attempt {attempt}: {blocked_reasons[:160]}",
                    stage="compliance",
                    agent=specialist.name,
                    kind="error",
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

            self._emit("verify", detail=f"{department.name} head is reviewing")
            self._note(
                f"{department.name} head is verifying {specialist.title}'s deliverable.",
                stage="verify",
                agent=f"{department.name}_head",
            )
            verification = head_agent.verify_subtask(
                department,
                subtask,
                deliverable.content,
                brief_block=brief_block,
            )
            self._note(
                verification["reason"]
                or ("Deliverable accepted." if verification["passed"] else "Deliverable rejected."),
                stage="verify",
                agent=f"{department.name}_head",
                kind="ok" if verification["passed"] else "error",
            )
            trace.append(
                StageTrace(
                    stage="verify",
                    agent=f"{department.name}_head",
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
            return (
                {
                    "specialist": specialist.name,
                    "status": "error",
                    "content": "",
                    "message": failure_reason
                    or "The specialist could not complete the subtask.",
                },
                trace,
                backtests,
                len(retrieved),
            )

        return (
            {
                "specialist": specialist.name,
                "status": "ok",
                "content": deliverable.content,
                "message": "",
                "metrics": deliverable.metrics,
            },
            trace,
            backtests,
            len(retrieved),
        )

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
    progress: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    activity: ActivityCallback | None = None,
) -> PipelineResult:
    """Convenience entry point used by the API and services layers."""
    return Orchestrator(
        project_id,
        progress=progress,
        cancel_check=cancel_check,
        activity=activity,
    ).run(user_request, attachment_ids)
