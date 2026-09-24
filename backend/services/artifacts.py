"""Deliverable artifact storage.

When the manager produces a final answer that is a document (a script, a
sequence, ad copy), the manager attaches a downloadable file so the user gets
both the content inline and a file they can save.

Artifacts are written under `data/artifacts` and served by `backend.api.artifacts`.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from backend.config import ARTIFACTS_DIR
from backend.errors import ArtifactError

SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass
class Artifact:
    """A stored deliverable file."""

    filename: str
    path: Path
    size: int
    extension: str
    download_url: str

    def to_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "size": self.size,
            "extension": self.extension,
            "download_url": self.download_url,
        }


def _slugify(value: str, fallback: str = "deliverable") -> str:
    slug = SAFE_NAME.sub("-", value.strip().lower()).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:60] or fallback


def create_artifact(
    content: str,
    *,
    title: str,
    extension: str = "txt",
) -> Artifact:
    """Write deliverable content to a downloadable file."""
    if not content.strip():
        raise ArtifactError("Cannot create an artifact from empty content.", stage="artifact")

    extension = extension.lstrip(".").lower() or "txt"
    if extension not in {"txt", "md"}:
        extension = "txt"

    filename = f"{_slugify(title)}-{uuid.uuid4().hex[:8]}.{extension}"
    destination = ARTIFACTS_DIR / filename

    try:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ArtifactError(
            f"Could not write the deliverable file: {exc}",
            stage="artifact",
            details={"filename": filename},
        ) from exc

    return Artifact(
        filename=filename,
        path=destination,
        size=destination.stat().st_size,
        extension=f".{extension}",
        download_url=f"/artifacts/{filename}",
    )


def resolve_artifact(filename: str) -> Path:
    """Resolve an artifact filename to a path inside the artifacts directory."""
    safe_name = Path(filename).name
    path = ARTIFACTS_DIR / safe_name
    if not path.is_file():
        raise ArtifactError(
            f"Deliverable file not found: {safe_name}",
            stage="artifact",
            details={"filename": safe_name},
        )
    return path


def should_attach_artifact(answer_body: str) -> bool:
    """Decide whether a final answer is substantial enough to warrant a file."""
    return len(answer_body.strip()) >= 400
