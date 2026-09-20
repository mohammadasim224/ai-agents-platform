from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentDefinition:
    name: str
    department: str
    prompt: str
    allowed_knowledge: list[str]
    model: str
    output_schema: dict


AGENT_REGISTRY: dict[str, AgentDefinition] = {
    "ad_copywriting": AgentDefinition(
        name="ad_copywriting",
        department="marketing",
        prompt="Write ad copy grounded in approved business facts.",
        allowed_knowledge=["business", "marketing"],
        model="openrouter/free",
        output_schema={"headline": "str", "body": "str", "cta": "str"},
    ),
    "ad_scripting": AgentDefinition(
        name="ad_scripting",
        department="marketing",
        prompt="Write an educational script grounded in approved business facts.",
        allowed_knowledge=["business", "marketing"],
        model="openrouter/free",
        output_schema={"hook": "str", "script": "str", "cta": "str"},
    ),
    "appointment_setting": AgentDefinition(
        name="appointment_setting",
        department="sales",
        prompt="Prepare a qualified appointment-setting script.",
        allowed_knowledge=["business", "sales"],
        model="openrouter/free",
        output_schema={"opening": "str", "questions": "list", "booking": "str"},
    ),
    "closing": AgentDefinition(
        name="closing",
        department="sales",
        prompt="Write a compliant closing script grounded in approved business facts.",
        allowed_knowledge=["business", "sales"],
        model="openrouter/free",
        output_schema={"discovery": "str", "close": "str"},
    ),
    "lead_nurturing": AgentDefinition(
        name="lead_nurturing",
        department="automation",
        prompt="Create a compliant lead nurture sequence.",
        allowed_knowledge=["business", "automation"],
        model="openrouter/free",
        output_schema={"sequence": "list"},
    ),
    "lead_reminding": AgentDefinition(
        name="lead_reminding",
        department="automation",
        prompt="Create reminder messages grounded in business facts.",
        allowed_knowledge=["business", "automation"],
        model="openrouter/free",
        output_schema={"messages": "list"},
    ),
}


def get_agent_definition(agent_name: str) -> AgentDefinition | None:
    return AGENT_REGISTRY.get(agent_name)
