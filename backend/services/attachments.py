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


def _resolve(filename: str) -> Path:
    safe_name = Path(filename).name
    path = UPLOADS_DIR / safe_name
    if not path.is_file():
        raise AttachmentError(
            f"Attached file not found: {safe_name}",
            stage="attachments",
            details={"filename": safe_name, "available": list_attachment_names()},
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
    extension = path.suffix.lower()

    try:
        if extension in TEXT_EXTENSIONS:
            text = path.read_text(encoding="utf-8", errors="replace")
        elif extension == ".docx":
            from docx import Document

            document = Document(path)
            text = "\n".join(
                paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()
            )
        elif extension == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            raise AttachmentError(
                f"Unsupported attachment type: {extension or 'unknown'}",
                stage="attachments",
                details={"filename": path.name, "extension": extension},
            )
    except AttachmentError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AttachmentError(
            f"Could not read attachment {path.name}: {exc}",
            stage="attachments",
            details={"filename": path.name},
        ) from exc

    text = text.strip()
    if not text:
        raise AttachmentError(
            f"Attachment {path.name} contains no readable text.",
            stage="attachments",
            details={"filename": path.name},
        )

    if len(text) > MAX_ATTACHMENT_CHARS:
        text = text[:MAX_ATTACHMENT_CHARS] + "\n\n[... truncated ...]"
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
