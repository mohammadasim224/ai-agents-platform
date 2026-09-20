from pathlib import Path

from backend.knowledge.ingestion import ingest_knowledge
from backend.knowledge.retrieval import retrieve_knowledge


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_ROOT = ROOT / "knowledge"


def test_ingestion_creates_chunks_for_markdown_docs():
    chunks = ingest_knowledge(KNOWLEDGE_ROOT)

    assert chunks
    assert any(chunk["metadata"].get("document") for chunk in chunks)
    assert all("content" in chunk for chunk in chunks)


def test_retrieval_prefers_business_context_for_company_questions():
    chunks = ingest_knowledge(KNOWLEDGE_ROOT)
    results = retrieve_knowledge("What is the company name?", chunks, category="business")

    assert results
    assert any("SunPeak Solar" in chunk["content"] for chunk in results)


def test_retrieval_prefers_banned_claims_for_prohibited_claims():
    chunks = ingest_knowledge(KNOWLEDGE_ROOT)
    results = retrieve_knowledge("Write an ad saying solar is free and guaranteed", chunks, category="marketing")

    assert results
    assert any("BANNED" in chunk["content"] or "free solar" in chunk["content"].lower() for chunk in results)
