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


def test_knowledge_endpoint_lists_distinct_documents():
    """The library view must show every source file, not repeat the first one."""
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    documents = client.get("/knowledge").json()

    names = [entry["document"] for entry in documents]
    assert len(names) == len(set(names)), "documents must not be duplicated per chunk"

    on_disk = {path.relative_to(KNOWLEDGE_ROOT).with_suffix("").as_posix() for path in KNOWLEDGE_ROOT.rglob("*.md")}
    assert set(names) == on_disk


def test_reindex_reports_documents_and_chunks():
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    body = client.post("/knowledge/reindex").json()

    assert body["status"] == "ok"
    assert body["documents_indexed"] > 1
    assert body["chunks_indexed"] >= body["documents_indexed"]


def test_retrieval_spreads_across_categories():
    """A multi-category specialist must receive excerpts from each category."""
    from backend.knowledge.retrieval import retrieve_for_categories

    chunks = ingest_knowledge(KNOWLEDGE_ROOT)
    results = retrieve_for_categories(
        "optimize an appointment setter script with objection handling",
        chunks,
        ("business", "sales", "automation"),
    )

    categories = {chunk["metadata"]["category"] for chunk in results}
    assert categories == {"business", "sales", "automation"}
