"""Knowledge base builder.

Turns a completed business profile form into a structured knowledge base under
`knowledge/business/`. The builder works in two modes:

1. **Template mode** (always available): fills the existing knowledge skeleton
   with the profile answers. Deterministic, fast, and works without a provider.
2. **AI mode** (when a provider key is configured): asks the model to expand the
   profile into richer, ready-to-use knowledge documents, then falls back to the
   template output if the model call fails so the user always gets a usable base.

The generated files follow the same frontmatter + markdown conventions as the
rest of the knowledge library, so ingestion and retrieval work unchanged.
"""

from __future__ import annotations

from typing import Any

from backend.config import KNOWLEDGE_DIR
from backend.errors import PipelineError

BUSINESS_DIR = KNOWLEDGE_DIR / "business"

# Files the builder owns. Existing hand-written files with the same names are
# backed up to `knowledge/business/.backup/` before being replaced.
OWNED_FILES = ("company.md", "target_customer.md", "services_and_offers.md")


def _section(title: str, body: str) -> str:
    body = (body or "").strip()
    if not body:
        return ""
    return f"## {title}\n\n{body}\n"


def _frontmatter(**fields: Any) -> str:
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def build_company_md(profile: dict[str, Any]) -> str:
    name = profile.get("name") or "Untitled business"
    business_type = profile.get("business_type") or ""
    industry = profile.get("industry") or ""
    description = profile.get("description") or ""
    voice = profile.get("brand_voice") or ""
    geography = profile.get("geographic_focus") or ""
    compliance = profile.get("compliance_notes") or ""

    sections = [
        _section("Business Type", business_type),
        _section("Industry", industry),
        _section("Description", description),
        _section("Geographic Focus", geography),
        _section("Brand Voice", voice),
        _section("Compliance Notes", compliance),
    ]

    body = "\n".join(section for section in sections if section)
    return (
        f"{_frontmatter(type='source_of_truth', priority=100, version=1, status='active')}\n"
        f"# {name}\n\n"
        f"{body or 'No company details provided yet.'}\n"
    )


def build_target_customer_md(profile: dict[str, Any]) -> str:
    target = profile.get("target_customer") or ""
    sections = [
        _section("Target Customer", target),
        _section("Geographic Profile", profile.get("geographic_focus") or ""),
    ]
    body = "\n".join(section for section in sections if section)
    return (
        f"{_frontmatter(type='source_of_truth', priority=90, version=1, status='active')}\n"
        f"# Target Customer\n\n"
        f"{body or 'No target customer details provided yet.'}\n"
    )


def build_services_md(profile: dict[str, Any]) -> str:
    services = profile.get("services") or ""
    offers = profile.get("offers") or ""
    pricing = profile.get("pricing") or ""
    sales_process = profile.get("sales_process") or ""
    automation = profile.get("automation_needs") or ""

    sections = [
        _section("Services", services),
        _section("Offers", offers),
        _section("Pricing & Financing", pricing),
        _section("Sales Process", sales_process),
        _section("Automation Needs", automation),
    ]
    body = "\n".join(section for section in sections if section)
    return (
        f"{_frontmatter(type='source_of_truth', priority=95, version=1, status='active')}\n"
        f"# Services & Offers\n\n"
        f"{body or 'No services or offers provided yet.'}\n"
    )


def build_marketing_strategy_md(profile: dict[str, Any]) -> str:
    channels = profile.get("marketing_channels") or ""
    voice = profile.get("brand_voice") or ""
    compliance = profile.get("compliance_notes") or ""
    target = profile.get("target_customer") or ""

    sections = [
        _section("Marketing Channels", channels),
        _section("Brand Voice", voice),
        _section("Target Customer", target),
        _section("Compliance Notes", compliance),
    ]
    body = "\n".join(section for section in sections if section)
    return (
        f"{_frontmatter(type='strategy', priority=70, version=1, status='active')}\n"
        f"# Marketing Strategy\n\n"
        f"{body or 'No marketing strategy details provided yet.'}\n"
    )


def build_sales_training_md(profile: dict[str, Any]) -> str:
    sales_process = profile.get("sales_process") or ""
    target = profile.get("target_customer") or ""
    sections = [
        _section("Sales Process", sales_process),
        _section("Target Customer", target),
    ]
    body = "\n".join(section for section in sections if section)
    return (
        f"{_frontmatter(type='strategy', priority=70, version=1, status='active')}\n"
        f"# Sales Training\n\n"
        f"{body or 'No sales process details provided yet.'}\n"
    )


def build_automation_tone_md(profile: dict[str, Any]) -> str:
    voice = profile.get("brand_voice") or ""
    automation = profile.get("automation_needs") or ""
    sections = [
        _section("Brand Voice", voice),
        _section("Automation Needs", automation),
    ]
    body = "\n".join(section for section in sections if section)
    return (
        f"{_frontmatter(type='strategy', priority=70, version=1, status='active')}\n"
        f"# Automation Tone\n\n"
        f"{body or 'No automation details provided yet.'}\n"
    )


def _backup_existing() -> None:
    """Move existing owned files to a backup folder before regeneration."""
    backup_dir = BUSINESS_DIR / ".backup"
    for filename in OWNED_FILES:
        source = BUSINESS_DIR / filename
        if not source.is_file():
            continue
        backup_dir.mkdir(parents=True, exist_ok=True)
        destination = backup_dir / filename
        if not destination.exists():
            source.rename(destination)


def build_knowledge_base(profile: dict[str, Any]) -> dict[str, Any]:
    """Write the profile-derived knowledge files and return a summary."""
    if not profile:
        raise PipelineError(
            "A profile is required to build a knowledge base.",
            stage="knowledge_builder",
            hint="Create a business profile first.",
        )

    BUSINESS_DIR.mkdir(parents=True, exist_ok=True)
    _backup_existing()

    documents = {
        "company.md": build_company_md(profile),
        "target_customer.md": build_target_customer_md(profile),
        "services_and_offers.md": build_services_md(profile),
        "marketing_strategy.md": build_marketing_strategy_md(profile),
        "sales_training.md": build_sales_training_md(profile),
        "automation_tone.md": build_automation_tone_md(profile),
    }

    written: list[dict[str, Any]] = []
    for filename, content in documents.items():
        destination = BUSINESS_DIR / filename
        destination.write_text(content, encoding="utf-8")
        written.append({"filename": filename, "size": len(content)})

    return {
        "status": "ok",
        "profile_id": profile.get("id"),
        "documents": written,
        "mode": "template",
    }


def build_knowledge_base_ai(profile: dict[str, Any]) -> dict[str, Any]:
    """Build the knowledge base, upgrading to AI expansion when possible.

    The AI pass asks the model to enrich the profile into fuller documents. If
    the provider is unavailable or the model output is unusable, the template
    output is kept and the response reports `mode: "template"` so the caller can
    tell the user the base is usable but not AI-expanded.
    """
    result = build_knowledge_base(profile)
    if not profile:
        return result

    try:
        from backend.llm.router import call_openrouter, extract_json
        from backend.llm.models import get_model_for

        prompt = _ai_expansion_prompt(profile)
        response = call_openrouter(
            get_model_for("manager"),
            prompt,
            system_prompt=(
                "You convert a business profile into a structured knowledge base. "
                "Return only valid JSON. Never invent facts that are not present "
                "in the profile. Keep every claim conditional and honest."
            ),
            temperature=0.3,
            max_tokens=4000,
        )
        expanded = extract_json(response["content"])
        if not isinstance(expanded, dict):
            return result

        documents = {
            "company.md": build_company_md(profile),
            "target_customer.md": build_target_customer_md(profile),
            "services_and_offers.md": build_services_md(profile),
        }
        for key in ("company", "target_customer", "services_and_offers"):
            content = expanded.get(key)
            if isinstance(content, str) and len(content.strip()) > 40:
                documents[f"{key}.md"] = content.strip() + "\n"

        written: list[dict[str, Any]] = []
        for filename, content in documents.items():
            destination = BUSINESS_DIR / filename
            destination.write_text(content, encoding="utf-8")
            written.append({"filename": filename, "size": len(content)})

        return {"status": "ok", "profile_id": profile.get("id"), "documents": written, "mode": "ai"}
    except Exception:  # noqa: BLE001 - provider failure keeps the template base
        return result


def _ai_expansion_prompt(profile: dict[str, Any]) -> str:
    fields = "\n".join(
        f"- {key.replace('_', ' ').title()}: {value}"
        for key, value in profile.items()
        if key not in {"id", "created_at", "updated_at"} and value
    )
    return (
        "Here is a completed business profile:\n\n"
        f"{fields}\n\n"
        "Return a JSON object with exactly three keys: `company`, `target_customer`, "
        "and `services_and_offers`. Each value must be a complete markdown document "
        "with a `#` title and `##` sections, written for this specific business. "
        "Ground every statement in the profile. Do not invent prices, guarantees, "
        "customer stories, or facts that are not in the profile."
    )