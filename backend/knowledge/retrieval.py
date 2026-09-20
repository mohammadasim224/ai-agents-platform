from __future__ import annotations

import re
from typing import Any


def _score_chunk(query: str, chunk: dict[str, Any]) -> float:
    text = (chunk.get("content") or "").lower()
    query_lower = query.lower()
    if not text:
        return 0.0

    score = 0.0
    query_terms = re.findall(r"[a-z0-9]+", query_lower)
    for term in query_terms:
        if term in text:
            score += 1.5
        if len(term) > 3 and term in text:
            score += 1.0

    metadata = chunk.get("metadata") or {}
    category = metadata.get("category")
    if category and category in query_lower:
        score += 2.0

    document = metadata.get("document", "")
    if document and document.lower() in query_lower:
        score += 2.0

    if "free solar" in text and "free solar" in query_lower:
        score += 5.0

    if "bann" in text.lower() and "free" in query_lower and "solar" in query_lower:
        score += 6.0

    return score


def retrieve_knowledge(query: str, chunks: list[dict[str, Any]], category: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    scored = []
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        if category and metadata.get("category") and metadata["category"] != category:
            continue
        score = _score_chunk(query, chunk)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]
