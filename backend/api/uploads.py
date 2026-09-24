from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from backend.config import MAX_UPLOAD_BYTES, UPLOADS_DIR
from backend.services.attachments import READABLE_EXTENSIONS, extract_text

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
UPLOAD_DIR = UPLOADS_DIR
ALLOWED_EXTENSIONS = {'.txt', '.md', '.csv', '.json', '.html', '.pdf', '.doc', '.docx'}
CREATABLE_EXTENSIONS = {".txt", ".pdf", ".docx"}
CHUNK_SIZE = 1024 * 1024
PREVIEW_CHARS = 12000


class CreateFileRequest(BaseModel):
    filename: str = Field(min_length=1)
    content: str = ""


def _safe_name(filename: str) -> str:
    """Reduce a client-supplied filename to a safe basename.

    `Path(...).name` strips any directory component (including `..`), and the
    regex removes everything that is not a conservative filename character.
    """
    base = Path(filename or "").name
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", base).strip("._")
    return cleaned or "upload"


def _unique_destination(safe_name: str) -> Path:
    """Return a destination path that does not overwrite an existing file.

    Uploading `script.txt` twice used to silently replace the first file, which
    meant an attachment referenced by an earlier request changed underneath it.
    """
    destination = UPLOAD_DIR / safe_name
    if not destination.exists():
        return destination
    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    for index in range(2, 1000):
        candidate = UPLOAD_DIR / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=409, detail="Too many files with that name")


async def _write_limited(file: UploadFile, destination: Path) -> int:
    """Stream an upload to disk, aborting if it exceeds the size limit."""
    total = 0
    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "File is too large. The maximum upload size is "
                            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
                        ),
                    )
                handle.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as error:  # noqa: BLE001 - surface a clean 500 instead of a traceback
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not store the file: {error}") from error
    return total


@router.post("/upload")
async def upload_knowledge_file(file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{extension or 'unknown'}'. "
                f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
            ),
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination(_safe_name(file.filename or "upload"))
    size = await _write_limited(file, destination)
    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    return {
        "status": "ok",
        "filename": destination.name,
        "size": size,
        "extension": extension,
        "readable": extension in READABLE_EXTENSIONS,
    }


@router.get("/uploads")
async def list_uploaded_files():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return [
        {
            "filename": path.name,
            "size": path.stat().st_size,
            "extension": path.suffix.lower(),
            "readable": path.suffix.lower() in READABLE_EXTENSIONS,
        }
        for path in sorted(UPLOAD_DIR.iterdir())
        if path.is_file()
    ]


@router.get("/uploads/{filename}/preview")
async def preview_uploaded_file(filename: str):
    safe_name = Path(filename).name
    source = UPLOAD_DIR / safe_name
    if not source.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        preview = extract_text(source)[:PREVIEW_CHARS]
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"filename": safe_name, "extension": source.suffix.lower(), "preview": preview}


@router.post("/create")
async def create_knowledge_file(payload: CreateFileRequest):
    extension = Path(payload.filename).suffix.lower()
    if extension not in CREATABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only TXT, PDF, and DOCX files can be created")
    safe_name = _safe_name(payload.filename)
    if Path(safe_name).suffix.lower() not in CREATABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Filename must end in .txt, .pdf, or .docx")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = _unique_destination(safe_name)
    if extension == ".txt":
        destination.write_text(payload.content, encoding="utf-8")
    elif extension == ".docx":
        document = Document()
        for paragraph in payload.content.splitlines() or [""]:
            document.add_paragraph(paragraph)
        document.save(destination)
    else:
        pdf = canvas.Canvas(str(destination), pagesize=LETTER)
        text = pdf.beginText(54, 750)
        text.setFont("Helvetica", 10)
        for line in payload.content.splitlines() or [""]:
            if text.getY() < 54:
                pdf.drawText(text)
                pdf.showPage()
                text = pdf.beginText(54, 750)
                text.setFont("Helvetica", 10)
            text.textLine(line[:120])
        pdf.drawText(text)
        pdf.save()
    return {
        "status": "ok",
        "filename": destination.name,
        "size": destination.stat().st_size,
        "extension": extension,
        "readable": True,
    }


@router.delete("/uploads/{filename}")
async def delete_uploaded_file(filename: str):
    safe_name = Path(filename).name
    destination = UPLOAD_DIR / safe_name
    if not destination.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    destination.unlink()
    return {"status": "ok", "filename": safe_name}