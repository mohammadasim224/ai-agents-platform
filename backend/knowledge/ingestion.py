from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text

    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text

    frontmatter = text[4:end]
    body = text[end + 5 :]
    metadata: dict[str, Any] = {}

    for line in frontmatter.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()

    return metadata, body.strip()


def _chunk_text(text: str, chunk_size: int = 600) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        if paragraph_len > chunk_size and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0

        if current_len + paragraph_len > chunk_size and current:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0

        current.append(paragraph)
        current_len += paragraph_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks if chunks else [text]


def ingest_knowledge(root: str | Path) -> list[dict[str, Any]]:
    knowledge_root = Path(root)
    all_chunks: list[dict[str, Any]] = []

    for path in sorted(knowledge_root.rglob("*.md")):
        relative = path.relative_to(knowledge_root)
        text = path.read_text(encoding="utf-8")
        metadata, body = _parse_frontmatter(text)

        doc_metadata = {
            "document": str(relative.with_suffix("")),
            "category": relative.parts[0] if len(relative.parts) > 1 else "general",
            "path": str(relative),
            "type": metadata.get("type", "source_of_truth"),
            "priority": int(metadata.get("priority", 50)),
            "version": int(metadata.get("version", 1)),
            "status": metadata.get("status", "active"),
        }

        heading = ""
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                heading = stripped.lstrip("#").strip()
                break

        for idx, chunk in enumerate(_chunk_text(body)):
            all_chunks.append(
                {
                    "content": chunk,
                    "metadata": {
                        **doc_metadata,
                        "heading": heading,
                        "chunk_index": idx,
                        "source": str(path),
                    },
                }
            )

    return all_chunks
