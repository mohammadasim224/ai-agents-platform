"""Keyword-based knowledge retrieval.

The knowledge base is small and curated, so retrieval is intentionally simple and
deterministic: term overlap, document-title overlap, and category relevance.
Determinism matters here because agents must be able to rely on the same excerpts
being selected for the same request.
"""

from __future__ import annotations

import re
from typing import Any

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "you",
    "are", "was", "were", "have", "has", "had", "but", "not", "our", "their",
    "they", "them", "what", "when", "which", "who", "how", "why", "can", "will",
    "would", "should", "could", "about", "there", "here", "then", "than", "also",
    "just", "like", "make", "made", "use", "used", "using", "get", "got", "one",
    "two", "all", "any", "some", "more", "most", "much", "very", "out", "over",
}


def _terms(text: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[a-z0-9$]+", (text or "").lower())
        if len(term) > 2 and term not in STOPWORDS
    ]


def _score_chunk(query: str, chunk: dict[str, Any]) -> float:
    text = (chunk.get("content") or "").lower()
    if not text:
        return 0.0

    query_lower = query.lower()
    query_terms = _terms(query)
    score = 0.0

    for term in query_terms:
        occurrences = text.count(term)
        if occurrences:
            # Reward breadth of overlap, with a small bonus for repetition.
            score += 1.5 + min(occurrences, 3) * 0.25

    metadata = chunk.get("metadata") or {}
    category = str(metadata.get("category", "")).lower()
    if category and category in query_lower:
        score += 3.0

    document = str(metadata.get("document", "")).lower()
    if document:
        document_terms = set(_terms(document.replace("/", " ")))
        overlap = document_terms & set(query_terms)
        score += len(overlap) * 2.5

    heading = str(metadata.get("heading", "")).lower()
    if heading:
        heading_terms = set(_terms(heading))
        score += len(heading_terms & set(query_terms)) * 2.0

    return score


def retrieve_knowledge(
    query: str,
    chunks: list[dict[str, Any]],
    category: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the most relevant chunks for a query, optionally scoped to a category."""
    scored: list[tuple[float, dict[str, Any]]] = []

    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        chunk_category = metadata.get("category")
        if category and chunk_category and chunk_category != category:
            continue
        score = _score_chunk(query, chunk)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored[:limit]]


def retrieve_for_categories(
    query: str,
    chunks: list[dict[str, Any]],
    categories: tuple[str, ...] | list[str],
    *,
    per_category: int = 2,
    total_limit: int = 6,
) -> list[dict[str, Any]]:
    """Retrieve the best excerpts across several categories.

    Guarantees at least one slot per category when that category has any match, so
    a specialist never loses access to its core method documents just because the
    request wording leaned toward another category.
    """
    collected: list[dict[str, Any]] = []
    seen: set[int] = set()

    for category in categories:
        for chunk in retrieve_knowledge(query, chunks, category=category, limit=per_category):
            key = id(chunk)
            if key in seen:
                continue
            seen.add(key)
            collected.append(chunk)
            if len(collected) >= total_limit:
                return collected

    if len(collected) < total_limit:
        for chunk in retrieve_knowledge(query, chunks, limit=total_limit):
            key = id(chunk)
            if key in seen:
                continue
            seen.add(key)
            collected.append(chunk)
            if len(collected) >= total_limit:
                break

    return collected


def render_context(chunks: list[dict[str, Any]], *, max_chars: int = 9000) -> str:
    """Render retrieved chunks into a labelled block for a prompt."""
    if not chunks:
        return ""

    blocks: list[str] = []
    used = 0
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        document = metadata.get("document", "unknown")
        heading = metadata.get("heading", "")
        label = f"### knowledge/{document}.md"
        if heading:
            label += f" — {heading}"
        body = (chunk.get("content") or "").strip()
        block = f"{label}\n{body}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)

    return "\n\n".join(blocks)
