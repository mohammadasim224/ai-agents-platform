from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.errors import ArtifactError
from backend.services.artifacts import resolve_artifact

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{filename}")
async def download_artifact(filename: str):
    """Serve a deliverable file created by the manager."""
    try:
        path = resolve_artifact(filename)
    except ArtifactError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    media_type = "text/markdown" if path.suffix.lower() == ".md" else "text/plain"
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
    )
