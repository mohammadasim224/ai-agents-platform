"""Attachment reading for requests that reference uploaded files.

The frontend uploads files to `/knowledge/upload`, which stores them in
`data/uploads`. When a prompt references one of those files (for example
"take my appointment setter script and optimize it" with `script.txt` attached),
the manager passes the file contents down the chain so specialists work from the
real source material instead of guessing.
"""

from __future__ import annotations

from pathlib import Path

from backend.config import UPLOADS_DIR
from backend.errors import AttachmentError

MAX_ATTACHMENT_CHARS = 20000
MAX_TOTAL_ATTACHMENT_CHARS = 60000

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".html"}
# Extensions this module can turn into text. Anything else is rejected up front
# with a clear message instead of failing deep inside the pipeline.
READABLE_EXTENSIONS = TEXT_EXTENSIONS | {".docx", ".pdf"}

# The specialist runner rejects deliverables containing placeholder markers such
# as "[insert" or "todo:". A truncation notice must not look like one of those,
# or a long attachment would make every deliverable fail validation.
TRUNCATION_NOTICE = "\n\n[Attachment truncated: only the first portion was provided.]"


def extract_text(path: Path) -> str:
    """Extract the plain text of a readable document.

    The single place that knows how to read each supported file type, shared by
    attachments (which pass content to the agents) and the upload preview
    endpoint. Raises `ValueError` for an unsupported extension.
    """
    extension = path.suffix.lower()
    try:
        if extension in TEXT_EXTENSIONS:
            return path.read_text(encoding="utf-8", errors="replace")
        if extension == ".docx":
            from docx import Document

            document = Document(path)
            return "\n".join(
                paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()
            )
        if extension == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # noqa: BLE001 - surfaced by the caller as a typed error
        raise ValueError(f"Could not read {path.name}: {exc}") from exc

    raise ValueError(f"Unsupported attachment type: {extension or 'unknown'}")


def _resolve(filename: str) -> Path:
    safe_name = Path(filename).name
    path = UPLOADS_DIR / safe_name
    if not path.is_file():
        raise AttachmentError(
            f"Attached file not found: {safe_name}",
            stage="attachments",
            details={"filename": safe_name, "available": list_attachment_names()},
        )
    if path.suffix.lower() not in READABLE_EXTENSIONS:
        raise AttachmentError(
            f"Attached file type cannot be read: {path.suffix.lower() or 'unknown'}",
            stage="attachments",
            details={
                "filename": safe_name,
                "extension": path.suffix.lower(),
                "readable": sorted(READABLE_EXTENSIONS),
            },
        )
    return path


def list_attachment_names() -> list[str]:
    """List the filenames currently available as attachments."""
    if not UPLOADS_DIR.is_dir():
        return []
    return sorted(path.name for path in UPLOADS_DIR.iterdir() if path.is_file())


def read_attachment(filename: str) -> str:
    """Read one attachment into plain text."""
    path = _resolve(filename)

    try:
        text = extract_text(path)
    except ValueError as exc:
        raise AttachmentError(str(exc), stage="attachments", details={"filename": path.name}) from exc

    text = text.strip()
    if not text:
        raise AttachmentError(
            f"Attachment {path.name} contains no readable text.",
            stage="attachments",
            details={"filename": path.name},
        )

    if len(text) > MAX_ATTACHMENT_CHARS:
        text = text[:MAX_ATTACHMENT_CHARS] + TRUNCATION_NOTICE
    return text


def build_attachment_context(filenames: list[str]) -> str:
    """Build the source-material block handed to specialists."""
    if not filenames:
        return ""

    blocks: list[str] = []
    used = 0
    for filename in filenames:
        content = read_attachment(filename)
        block = f"### Attached file: {Path(filename).name}\n```\n{content}\n```"
        if used + len(block) > MAX_TOTAL_ATTACHMENT_CHARS:
            blocks.append(
                f"### Attached file: {Path(filename).name}\n"
                "(omitted: total attachment size limit reached)"
            )
            break
        blocks.append(block)
        used += len(block)

    return "\n\n".join(blocks)


def summarize_attachments(filenames: list[str]) -> str:
    """Produce a short description of attachments for routing and briefs."""
    if not filenames:
        return ""

    lines = []
    for filename in filenames:
        path = _resolve(filename)
        size_kb = max(0.1, path.stat().st_size / 1024)
        lines.append(f"- `{path.name}` ({path.suffix.lower() or 'file'}, {size_kb:.1f} KB)")
    return "\n".join(lines)
