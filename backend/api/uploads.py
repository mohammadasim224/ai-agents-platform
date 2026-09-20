from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from pypdf import PdfReader
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "uploads"
ALLOWED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".html", ".pdf", ".doc", ".docx"}
CREATABLE_EXTENSIONS = {".txt", ".pdf", ".docx"}


class CreateFileRequest(BaseModel):
    filename: str = Field(min_length=1)
    content: str = ""


@router.post("/upload")
async def upload_knowledge_file(file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(file.filename or "upload").name)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / safe_name
    content = await file.read()
    destination.write_bytes(content)
    return {"status": "ok", "filename": safe_name, "size": len(content), "extension": extension}


@router.get("/uploads")
async def list_uploaded_files():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return [
        {"filename": path.name, "size": path.stat().st_size, "extension": path.suffix.lower()}
        for path in sorted(UPLOAD_DIR.iterdir())
        if path.is_file()
    ]


def extract_preview(path: Path) -> str:
    extension = path.suffix.lower()
    if extension in {".txt", ".md", ".csv", ".json", ".html"}:
        return path.read_text(encoding="utf-8", errors="replace")[:12000]
    if extension == ".docx":
        document = Document(path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())[:12000]
    if extension == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)[:12000]
    return "Preview is not available for this file type."


@router.get("/uploads/{filename}/preview")
async def preview_uploaded_file(filename: str):
    safe_name = Path(filename).name
    source = UPLOAD_DIR / safe_name
    if not source.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        preview = extract_preview(source)
    except Exception as error:
        raise HTTPException(status_code=422, detail=f"Could not read file: {error}") from error
    return {"filename": safe_name, "extension": source.suffix.lower(), "preview": preview}


@router.post("/create")
async def create_knowledge_file(payload: CreateFileRequest):
    extension = Path(payload.filename).suffix.lower()
    if extension not in CREATABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only TXT, PDF, and DOCX files can be created")
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(payload.filename).name)
    if Path(safe_name).suffix.lower() not in CREATABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Filename must end in .txt, .pdf, or .docx")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / safe_name
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
    return {"status": "ok", "filename": safe_name, "size": destination.stat().st_size, "extension": extension}


@router.delete("/uploads/{filename}")
async def delete_uploaded_file(filename: str):
    safe_name = Path(filename).name
    destination = UPLOAD_DIR / safe_name
    if not destination.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    destination.unlink()
    return {"status": "ok", "filename": safe_name}