from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from backend.knowledge.ingestion import ingest_knowledge

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("")
async def list_knowledge():
    root = Path(__file__).resolve().parents[2] / "knowledge"
    chunks = ingest_knowledge(root)
    return [{"document": chunk["metadata"]["document"], "category": chunk["metadata"]["category"]} for chunk in chunks[:10]]


@router.post("/reindex")
async def reindex_knowledge():
    root = Path(__file__).resolve().parents[2] / "knowledge"
    chunks = ingest_knowledge(root)
    return {"status": "ok", "chunks_indexed": len(chunks)}
