"""File streaming endpoint (Range-capable).

Serves stored uploads with HTTP Range support so the browser can play/seek
source videos in the editor. This is the *local* implementation behind
``storage.stream_url()``; swapping to object storage means returning presigned
URLs from that seam, leaving this endpoint and all callers unchanged
(see docs/VIDEO_EDITOR.md §5).

Starlette's :class:`FileResponse` handles ``Range`` requests natively (206
partial content), which is what video scrubbing needs.
"""

from fastapi import APIRouter, HTTPException, status
from starlette.responses import FileResponse

from app.services.storage import resolve_safe

router = APIRouter()


@router.get("/{file_path:path}")
async def stream_file(file_path: str) -> FileResponse:
    """Stream a stored file by its relative path, with Range support."""
    path = resolve_safe(file_path)
    if path is None or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return FileResponse(path)
