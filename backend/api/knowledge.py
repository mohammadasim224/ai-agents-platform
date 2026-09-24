from __future__ import annotations

from fastapi import APIRouter

from backend.config import KNOWLEDGE_DIR
from backend.knowledge.ingestion import ingest_knowledge
from backend.prompts.loader import knowledge_catalog

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("")
async def list_knowledge():
    """List the distinct knowledge documents available to the agents.

    Returns one entry per document, not one per chunk, so the library view shows
    every source file rather than repeating the first file many times.
    """
    return [
        {
            "document": source.path[: -len(".md")],
            "category": source.category,
            "title": source.title,
        }
        for source in knowledge_catalog()
    ]


@router.post("/reindex")
async def reindex_knowledge():
    chunks = ingest_knowledge(KNOWLEDGE_DIR)
    documents = {chunk["metadata"]["document"] for chunk in chunks}
    return {
        "status": "ok",
        "documents_indexed": len(documents),
        "chunks_indexed": len(chunks),
    }
