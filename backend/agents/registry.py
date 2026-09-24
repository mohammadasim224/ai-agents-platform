"""The org chart.

The Manager sits at the top of the chain of command and is the only agent that
communicates with the user. Below the Manager sit department heads. Below each
head sit specialist agents that do the actual work.

This module is the single source of truth for that structure: who exists, which
prompt file defines them, which knowledge categories they may read, and what
output they must produce.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.errors import PipelineError


@dataclass(frozen=True)
class Specialist:
    """A worker agent that produces a single deliverable."""

    name: str
    department: str
    title: str
    prompt: str  # path under /prompts, without extension
    knowledge_categories: tuple[str, ...]
    produces: str
    # When true, the specialist must clear a measured quality gate (backtesting)
    # before its work is accepted by its head of department.
    requires_backtest: bool = False
    deliverable_extension: str = "txt"


@dataclass(frozen=True)
class Department:
    """A department head plus the specialists it may assign work to."""

    name: str
    title: str
    prompt: str
    knowledge_categories: tuple[str, ...]
    mission: str
    specialists: tuple[str, ...] = field(default_factory=tuple)

    def specialist_definitions(self) -> list[Specialist]:
        return [SPECIALISTS[name] for name in self.specialists if name in SPECIALISTS]


SPECIALISTS: dict[str, Specialist] = {
    "ad_copywriting": Specialist(
        name="ad_copywriting",
        department="marketing",
        title="Ad Copywriting Agent",
        prompt="marketing/ad_copywriting",
        knowledge_categories=("business", "marketing"),
        produces="Ad copy with headline, body, and CTA variations.",
        deliverable_extension="md",
    ),
    "ad_scripting": Specialist(
        name="ad_scripting",
        department="marketing",
        title="Ad Scripting Agent",
        prompt="marketing/ad_scripting",
        knowledge_categories=("business", "marketing"),
        produces="A video ad script with concept, hook, spoken script, and on-screen text.",
        deliverable_extension="md",
    ),
    "appointment_setting": Specialist(
        name="appointment_setting",
        department="sales",
        title="Appointment Setting Script Agent",
        prompt="sales/appointment_setting",
        knowledge_categories=("business", "sales", "automation"),
        produces="A complete appointment-setting script with branches and objection responses.",
        requires_backtest=True,
        deliverable_extension="txt",
    ),
    "closing": Specialist(
        name="closing",
        department="sales",
        title="Closing Script Agent",
        prompt="sales/closing",
        knowledge_categories=("business", "sales", "automation"),
        produces="A complete closing script with discovery, pitch, and objection handling.",
        requires_backtest=True,
        deliverable_extension="txt",
    ),
    "lead_nurturing": Specialist(
        name="lead_nurturing",
        department="automation",
        title="Lead Nurturing Writing Agent",
        prompt="automation/lead_nurturing",
        knowledge_categories=("business", "automation", "sales", "marketing"),
        produces="A nurture sequence with timing, message content, and branch logic.",
        deliverable_extension="txt",
    ),
    "lead_reminding": Specialist(
        name="lead_reminding",
        department="automation",
        title="Lead Reminder Writing Agent",
        prompt="automation/lead_reminding",
        knowledge_categories=("business", "automation"),
        produces="A reminder sequence covering confirmation, reminders, and no-show handling.",
        deliverable_extension="txt",
    ),
}


DEPARTMENTS: dict[str, Department] = {
    "marketing": Department(
        name="marketing",
        title="Marketing Department",
        prompt="departments/marketing_head",
        knowledge_categories=("business", "marketing"),
        mission="Create advertising copy, scripts, and campaign assets that comply with banned claims.",
        specialists=("ad_copywriting", "ad_scripting"),
    ),
    "sales": Department(
        name="sales",
        title="Sales Department",
        prompt="departments/sales_head",
        knowledge_categories=("business", "sales", "automation"),
        mission="Create sales scripts and assets grounded in the sales training methodology.",
        specialists=("appointment_setting", "closing"),
    ),
    "automation": Department(
        name="automation",
        title="Automation Department",
        prompt="departments/automation_head",
        knowledge_categories=("business", "automation"),
        mission="Create nurture, reminder, and follow-up sequences that respect tone and cadence rules.",
        specialists=("lead_nurturing", "lead_reminding"),
    ),
}


def department_names() -> list[str]:
    return list(DEPARTMENTS)


def get_department(name: str) -> Department:
    department = DEPARTMENTS.get(name)
    if department is None:
        raise PipelineError(
            f"Unknown department: {name}",
            stage="routing",
            details={"department": name, "available": department_names()},
        )
    return department


def get_specialist(name: str) -> Specialist:
    specialist = SPECIALISTS.get(name)
    if specialist is None:
        raise PipelineError(
            f"Unknown specialist agent: {name}",
            stage="assignment",
            details={"specialist": name, "available": list(SPECIALISTS)},
        )
    return specialist


def department_catalog() -> str:
    """Render the department list for the manager's routing prompt."""
    lines = []
    for department in DEPARTMENTS.values():
        specialists = ", ".join(spec.name for spec in department.specialist_definitions())
        lines.append(
            f"- `{department.name}` — {department.title}\n"
            f"  Mission: {department.mission}\n"
            f"  Specialists available: {specialists}"
        )
    return "\n".join(lines)


def specialist_catalog(department: str) -> str:
    """Render the specialist list for a department head's planning prompt."""
    lines = []
    for specialist in get_department(department).specialist_definitions():
        lines.append(
            f"- `{specialist.name}` — {specialist.title}\n"
            f"  Produces: {specialist.produces}"
        )
    return "\n".join(lines)
