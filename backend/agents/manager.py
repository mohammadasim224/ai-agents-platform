"""The Manager: top of the chain of command and the only user-facing agent.

The manager owns four responsibilities:

1. `triage`   — decide which department(s) the request belongs to.
2. `rewrite`  — turn the raw user prompt into a precise brief per department.
3. `plan`     — (delegated) department heads break the brief into subtasks.
4. `finalize` — validate the combined department answer and produce the final
                user-facing message.

Hard rule: the manager never defaults to a department. If routing is ambiguous,
it raises `RoutingError` so the user receives an honest explanation instead of
off-target work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.agents.registry import department_catalog, department_names
from backend.errors import PipelineError, RoutingError
from backend.llm.router import extract_json, route_prompt
from backend.prompts.loader import compose_system_prompt


@dataclass
class TriageDecision:
    """The manager's routing decision."""

    departments: list[str]
    reasoning: str
    confidence: float
    needs_clarification: bool = False
    clarification: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "departments": self.departments,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "clarification": self.clarification,
        }


@dataclass
class DepartmentBrief:
    """A rewritten, department-specific task brief."""

    department: str
    objective: str
    deliverable: str
    requirements: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "department": self.department,
            "objective": self.objective,
            "deliverable": self.deliverable,
            "requirements": self.requirements,
            "constraints": self.constraints,
            "success_criteria": self.success_criteria,
        }

    def as_prompt_block(self) -> str:
        lines = [
            f"### Objective\n{self.objective}",
            f"### Required Deliverable\n{self.deliverable}",
        ]
        if self.requirements:
            lines.append("### Requirements\n" + "\n".join(f"- {item}" for item in self.requirements))
        if self.constraints:
            lines.append("### Constraints\n" + "\n".join(f"- {item}" for item in self.constraints))
        if self.success_criteria:
            lines.append(
                "### Success Criteria\n" + "\n".join(f"- {item}" for item in self.success_criteria)
            )
        return "\n\n".join(lines)


@dataclass
class FinalAnswer:
    """The manager's final, user-facing response."""

    status: str
    message: str
    body: str = ""
    verification: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "body": self.body,
            "verification": self.verification,
        }


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def triage(user_request: str, *, attachment_summary: str = "") -> TriageDecision:
    """Decide which department(s) own this request.

    Raises `RoutingError` when no department can be confidently assigned.
    """
    system_prompt = compose_system_prompt(
        "manager/manager",
        knowledge_categories=("business",),
        output="json",
        extra_rules=(
            "You are performing the TRIAGE step only.\n\n"
            "## Departments You May Assign\n\n"
            f"{department_catalog()}\n\n"
            "## Rules\n"
            "- Assign one or more departments from the list above. Never invent a department.\n"
            "- Assign a department only when its mission genuinely covers the request.\n"
            "- Multiple departments are allowed when the request clearly spans them.\n"
            "- If no department clearly covers the request, set `departments` to an empty list.\n"
            "- Never default to a department to avoid returning nothing.\n\n"
            "## Required JSON\n"
            "{\n"
            '  "departments": ["<department name>", ...],\n'
            '  "reasoning": "<why these departments own this request>",\n'
            '  "confidence": <number between 0 and 1>,\n'
            '  "needs_clarification": <true|false>,\n'
            '  "clarification": "<question to ask the user, or empty string>"\n'
            "}"
        ),
    )

    user_prompt = f"## User Request\n{user_request.strip()}"
    if attachment_summary.strip():
        user_prompt += f"\n\n## Attached Files\n{attachment_summary.strip()}"

    result = route_prompt("manager", user_prompt, system_prompt=system_prompt, temperature=0.1)
    decision = extract_json(result["content"])

    raw_departments = decision.get("departments")
    if isinstance(raw_departments, str):
        raw_departments = [raw_departments]
    requested = [str(name).strip().lower() for name in (raw_departments or []) if str(name).strip()]

    valid = [name for name in requested if name in department_names()]
    invalid = [name for name in requested if name not in department_names()]

    confidence_raw = decision.get("confidence", 0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0

    if not valid:
        raise RoutingError(
            decision.get("reasoning")
            or "The manager could not match this request to any department.",
            stage="triage",
            details={
                "requested_departments": requested,
                "invalid_departments": invalid,
                "available_departments": department_names(),
            },
        )

    return TriageDecision(
        departments=valid,
        reasoning=str(decision.get("reasoning", "")).strip(),
        confidence=confidence,
        needs_clarification=bool(decision.get("needs_clarification", False)),
        clarification=str(decision.get("clarification", "")).strip(),
    )


def rewrite_for_department(
    user_request: str,
    department: str,
    *,
    attachment_summary: str = "",
    extra_context: str = "",
) -> DepartmentBrief:
    """Rewrite the raw prompt into a precise brief for one department head."""
    system_prompt = compose_system_prompt(
        "manager/manager",
        knowledge_categories=("business",),
        output="json",
        extra_rules=(
            "You are performing the REWRITE step only, for a single department.\n\n"
            f"Target department: `{department}`\n\n"
            "## Rules\n"
            "- Rewrite the user's request into a specific, unambiguous brief for this department.\n"
            "- Preserve the user's actual intent. Do not invent new goals.\n"
            "- Make the deliverable concrete and checkable.\n"
            "- Requirements and constraints must be actionable, not generic filler.\n"
            "- Success criteria must describe what a correct answer looks like.\n"
            "- Never invent business facts, pricing, or guarantees.\n\n"
            "## Required JSON\n"
            "{\n"
            '  "objective": "<what this department must accomplish>",\n'
            '  "deliverable": "<the exact artifact to produce>",\n'
            '  "requirements": ["<requirement>", ...],\n'
            '  "constraints": ["<constraint>", ...],\n'
            '  "success_criteria": ["<criterion>", ...]\n'
            "}"
        ),
    )

    user_prompt = (
        f"## Original User Request\n{user_request.strip()}\n\n"
        f"## Department Receiving This Brief\n{department}"
    )
    if attachment_summary.strip():
        user_prompt += f"\n\n## Attached Files\n{attachment_summary.strip()}"
    if extra_context.strip():
        user_prompt += f"\n\n## Additional Context\n{extra_context.strip()}"

    result = route_prompt("manager", user_prompt, system_prompt=system_prompt, temperature=0.2)
    payload = extract_json(result["content"])

    objective = str(payload.get("objective", "")).strip()
    deliverable = str(payload.get("deliverable", "")).strip()
    if not objective or not deliverable:
        raise PipelineError(
            "The manager could not produce a usable brief for this department.",
            stage="rewrite",
            details={"department": department},
        )

    return DepartmentBrief(
        department=department,
        objective=objective,
        deliverable=deliverable,
        requirements=_coerce_str_list(payload.get("requirements")),
        constraints=_coerce_str_list(payload.get("constraints")),
        success_criteria=_coerce_str_list(payload.get("success_criteria")),
    )


def finalize(
    user_request: str,
    department_answers: list[dict[str, Any]],
    *,
    verification: dict[str, Any] | None = None,
) -> FinalAnswer:
    """Validate department answers and produce the final user-facing message."""
    usable = [
        answer
        for answer in department_answers
        if answer.get("status") == "ok" and str(answer.get("content", "")).strip()
    ]

    if not usable:
        reasons = "; ".join(
            f"{answer.get('department', 'department')}: {answer.get('message', 'no answer')}"
            for answer in department_answers
        ) or "no department returned a usable answer"
        return FinalAnswer(
            status="error",
            message="The team could not produce a verified answer for this request.",
            body=reasons,
            verification=verification or {},
        )

    if len(usable) == 1:
        answer = usable[0]
        return FinalAnswer(
            status="ok",
            message=f"Completed by the {answer.get('department', 'assigned')} department.",
            body=str(answer.get("content", "")).strip(),
            verification=verification or {},
        )

    system_prompt = compose_system_prompt(
        "manager/manager",
        knowledge_categories=("business",),
        output="text",
        extra_rules=(
            "You are performing the FINALIZE step.\n\n"
            "## Rules\n"
            "- You are combining work from multiple departments into one answer.\n"
            "- Preserve each department's actual content. Do not paraphrase away specifics.\n"
            "- Remove duplicated framing, but keep every distinct deliverable intact.\n"
            "- Use clear section headings per department.\n"
            "- Do not add claims, numbers, or promises that are not in the supplied work.\n"
            "- Do not address the user with meta-commentary about departments or process.\n"
        ),
    )

    sections = "\n\n".join(
        f"## Department: {answer.get('department', 'unknown')}\n{str(answer.get('content', '')).strip()}"
        for answer in usable
    )
    user_prompt = (
        f"## Original User Request\n{user_request.strip()}\n\n"
        f"## Department Deliverables\n{sections}"
    )

    result = route_prompt("manager", user_prompt, system_prompt=system_prompt, temperature=0.3)
    body = str(result.get("content", "")).strip()

    if not body:
        return FinalAnswer(
            status="error",
            message="The manager could not combine the department answers.",
            body="Department answers were produced but could not be merged into a single response.",
            verification=verification or {},
        )

    return FinalAnswer(
        status="ok",
        message="Combined answer from multiple departments.",
        body=body,
        verification=verification or {},
    )
