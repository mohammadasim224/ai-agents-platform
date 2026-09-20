from __future__ import annotations

from pathlib import Path

from backend.agents.manager import decide_agent
from backend.agents.marketing.copy import write_ad_copy
from backend.knowledge.ingestion import ingest_knowledge
from backend.knowledge.retrieval import retrieve_knowledge
from backend.services.compliance import check_compliance


def generate_for_prompt(prompt: str, project_id: str = "demo-project") -> dict:
    decision = decide_agent(prompt)

    knowledge_root = Path(__file__).resolve().parents[2] / "knowledge"
    chunks = ingest_knowledge(knowledge_root)

    business_context = retrieve_knowledge(prompt, chunks, category="business", limit=3)
    marketing_context = retrieve_knowledge(prompt, chunks, category="marketing", limit=3)
    all_context = business_context + marketing_context

    context_text = "\n\n".join(chunk["content"] for chunk in all_context[:5])
    output = write_ad_copy(f"{prompt}\n\nRelevant knowledge:\n{context_text}")
    compliance = check_compliance(output)

    return {
        "decision": decision,
        "output": output,
        "project_id": project_id,
        "knowledge_used": len(all_context),
        "compliance": compliance,
    }
