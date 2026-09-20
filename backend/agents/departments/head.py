"""Department heads.

A department head receives a brief from the manager and owns everything that
happens inside its department:

1. Split the brief into concrete subtasks.
2. Decide which specialist agent owns each subtask.
3. Hand each specialist the brief, the business context, and its knowledge files.
4. Verify the returned work actually answers the subtask.
5. Combine the verified answers into a single department answer.
6. Send the combined answer up to the manager.

A head never passes on unverified work. If verification fails and retries do not
fix it, the head reports an error upward instead of forwarding a bad answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.agents.registry import Department, Specialist, specialist_catalog
from backend.errors import (
    PlanningError,
    SpecialistError,
    ValidationError,
)
from backend.llm.router import extract_json, route_prompt
from backend.prompts.loader import compose_system_prompt


@dataclass
class Subtask:
    """One unit of work assigned to a single specialist."""

    id: str
    specialist: str
    instruction: str
    expected_output: str
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "specialist": self.specialist,
            "instruction": self.instruction,
            "expected_output": self.expected_output,
            "depends_on": self.depends_on,
        }


@dataclass
class DepartmentPlan:
    """The head's plan for fulfilling the manager's brief."""

    department: str
    summary: str
    subtasks: list[Subtask]
    shared_context: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "department": self.department,
            "summary": self.summary,
            "subtasks": [subtask.to_dict() for subtask in self.subtasks],
            "shared_context": self.shared_context,
        }


@dataclass
class DepartmentAnswer:
    """The head's combined answer sent back up to the manager."""

    department: str
    status: str
    content: str
    message: str = ""
    subtask_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "department": self.department,
            "status": self.status,
            "content": self.content,
            "message": self.message,
            "subtask_results": self.subtask_results,
        }


def plan(
    department: Department,
    brief_block: str,
    *,
    business_context: str = "",
    max_subtasks: int = 3,
) -> DepartmentPlan:
    """Break the manager's brief into specialist-owned subtasks."""
    system_prompt = compose_system_prompt(
        department.prompt,
        knowledge_categories=department.knowledge_categories,
        output="json",
        extra_rules=(
            "You are performing the PLAN step for your department.\n\n"
            "## Specialists In Your Department\n\n"
            f"{specialist_catalog(department.name)}\n\n"
            "## Rules\n"
            "- Split the brief into the minimum number of subtasks that fully cover it.\n"
            f"- Use at most {max_subtasks} subtasks. Prefer one subtask when one is enough.\n"
            "- Assign each subtask to a specialist that appears in the list above.\n"
            "- Each subtask must be independently verifiable.\n"
            "- Put shared business facts, offer details, and audience notes in `shared_context`\n"
            "  so every specialist receives the same grounding.\n"
            "- Do not create subtasks for work no specialist in your department can do.\n"
            "- Never invent business facts, pricing, guarantees, or customer proof.\n\n"
            "## Required JSON\n"
            "{\n"
            '  "summary": "<one sentence describing the plan>",\n'
            '  "shared_context": "<facts every specialist must know>",\n'
            '  "subtasks": [\n'
            "    {\n"
            '      "id": "subtask-1",\n'
            '      "specialist": "<specialist name>",\n'
            '      "instruction": "<exactly what to produce, in detail>",\n'
            '      "expected_output": "<what a correct deliverable looks like>",\n'
            '      "depends_on": []\n'
            "    }\n"
            "  ]\n"
            "}"
        ),
    )

    user_prompt = f"## Brief From The Manager\n{brief_block}"
    if business_context.strip():
        user_prompt += f"\n\n## Business Context\n{business_context.strip()}"

    result = route_prompt(department.name, user_prompt, system_prompt=system_prompt, temperature=0.2)
    payload = extract_json(result["content"])

    raw_subtasks = payload.get("subtasks")
    if not isinstance(raw_subtasks, list) or not raw_subtasks:
        raise PlanningError(
            f"The {department.title} did not produce any subtasks.",
            stage="planning",
            details={"department": department.name},
        )

    valid_specialists = {spec.name for spec in department.specialist_definitions()}
    subtasks: list[Subtask] = []
    rejected: list[str] = []

    for index, raw in enumerate(raw_subtasks[:max_subtasks], start=1):
        if not isinstance(raw, dict):
            continue
        specialist = str(raw.get("specialist", "")).strip().lower()
        instruction = str(raw.get("instruction", "")).strip()
        if specialist not in valid_specialists or not instruction:
            rejected.append(specialist or "(missing specialist)")
            continue
        subtasks.append(
            Subtask(
                id=str(raw.get("id") or f"subtask-{index}"),
                specialist=specialist,
                instruction=instruction,
                expected_output=str(raw.get("expected_output", "")).strip()
                or "A complete, ready-to-use deliverable.",
                depends_on=[
                    str(item)
                    for item in (raw.get("depends_on") or [])
                    if isinstance(item, (str, int))
                ],
            )
        )

    if not subtasks:
        raise PlanningError(
            f"The {department.title} could not assign work to any specialist in the department.",
            stage="planning",
            details={
                "department": department.name,
                "rejected_specialists": rejected,
                "available_specialists": sorted(valid_specialists),
            },
        )

    return DepartmentPlan(
        department=department.name,
        summary=str(payload.get("summary", "")).strip() or "Department plan.",
        subtasks=subtasks,
        shared_context=str(payload.get("shared_context", "")).strip(),
    )


def verify_subtask(
    department: Department,
    subtask: Subtask,
    deliverable: str,
    *,
    brief_block: str,
) -> dict[str, Any]:
    """Have the head check that a specialist deliverable actually answers the subtask."""
    system_prompt = compose_system_prompt(
        department.prompt,
        knowledge_categories=department.knowledge_categories,
        output="json",
        extra_rules=(
            "You are performing the VERIFY step for one subtask of your department.\n\n"
            "## Rules\n"
            "- Judge only whether the deliverable satisfies the subtask and the brief.\n"
            "- Reject placeholder text, meta-commentary, and answers that dodge the task.\n"
            "- Reject any invented business facts, pricing, guarantees, or customer proof.\n"
            "- Do not rewrite the deliverable here. Only judge it.\n\n"
            "## Required JSON\n"
            "{\n"
            '  "passed": <true|false>,\n'
            '  "reason": "<short justification>",\n'
            '  "issues": ["<specific problem>", ...],\n'
            '  "fix_instruction": "<what the specialist must change, or empty string>"\n'
            "}"
        ),
    )

    user_prompt = (
        f"## Brief\n{brief_block}\n\n"
        f"## Subtask\nID: {subtask.id}\n"
        f"Specialist: {subtask.specialist}\n"
        f"Instruction: {subtask.instruction}\n"
        f"Expected output: {subtask.expected_output}\n\n"
        f"## Specialist Deliverable\n{deliverable}"
    )

    result = route_prompt(department.name, user_prompt, system_prompt=system_prompt, temperature=0.1)
    payload = extract_json(result["content"])

    issues = payload.get("issues")
    return {
        "passed": bool(payload.get("passed", False)),
        "reason": str(payload.get("reason", "")).strip(),
        "issues": [str(item) for item in issues if str(item).strip()] if isinstance(issues, list) else [],
        "fix_instruction": str(payload.get("fix_instruction", "")).strip(),
    }


def combine(
    department: Department,
    brief_block: str,
    results: list[dict[str, Any]],
    *,
    verification_summary: str = "",
) -> DepartmentAnswer:
    """Combine verified specialist deliverables into one department answer."""
    if len(results) == 1:
        single = results[0]
        return DepartmentAnswer(
            department=department.name,
            status="ok",
            content=str(single.get("content", "")).strip(),
            message=f"{department.title} completed the task with {single.get('specialist', 'one specialist')}.",
            subtask_results=results,
        )

    system_prompt = compose_system_prompt(
        department.prompt,
        knowledge_categories=department.knowledge_categories,
        output="text",
        extra_rules=(
            "You are performing the COMBINE step for your department.\n\n"
            "## Rules\n"
            "- Merge the specialist deliverables into one coherent department answer.\n"
            "- Keep every concrete deliverable intact. Do not summarize away detail.\n"
            "- Remove duplicated framing and repeated instructions.\n"
            "- Use a clear section heading per specialist deliverable.\n"
            "- Do not add facts, numbers, or promises that are not in the deliverables.\n"
            "- Do not include meta-commentary about subtasks, IDs, or your process.\n"
        ),
    )

    sections = "\n\n".join(
        f"## {item.get('specialist', 'specialist')}\n{str(item.get('content', '')).strip()}"
        for item in results
    )
    user_prompt = (
        f"## Brief\n{brief_block}\n\n"
        f"## Verified Specialist Deliverables\n{sections}"
    )
    if verification_summary.strip():
        user_prompt += f"\n\n## Verification Notes\n{verification_summary.strip()}"

    result = route_prompt(department.name, user_prompt, system_prompt=system_prompt, temperature=0.3)
    content = str(result.get("content", "")).strip()

    if not content:
        raise ValidationError(
            f"The {department.title} could not combine its specialist deliverables.",
            stage="combine",
            details={"department": department.name},
        )

    return DepartmentAnswer(
        department=department.name,
        status="ok",
        content=content,
        message=f"{department.title} completed the task with {len(results)} specialists.",
        subtask_results=results,
    )


def get_specialist_or_raise(department: Department, specialist_name: str) -> Specialist:
    """Resolve a specialist inside a department, or raise."""
    for specialist in department.specialist_definitions():
        if specialist.name == specialist_name:
            return specialist
    raise SpecialistError(
        f"Specialist `{specialist_name}` does not belong to the {department.title}.",
        stage="assignment",
        details={"department": department.name, "specialist": specialist_name},
    )
