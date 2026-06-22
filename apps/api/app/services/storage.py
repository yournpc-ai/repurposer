"""Storage service for uploads and outputs."""

import shutil
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from app.config import settings


def _sanitize_filename(filename: str) -> str:
    """Sanitize upload filename to prevent path traversal.

    Strips directory components and replaces path separators.
    Falls back to 'unnamed' if the result is empty.
    """
    name = Path(filename).name
    name = name.replace("/", "_").replace("\\", "_")
    return name or "unnamed"


def _relative_path(path: Path) -> str:
    """Return path relative to upload_dir as a POSIX string."""
    try:
        return path.relative_to(settings.upload_dir).as_posix()
    except ValueError:
        return path.as_posix()


def get_project_upload_dir(project_id: UUID) -> Path:
    """Get upload directory for a project."""
    return settings.upload_dir / "projects" / str(project_id)


def get_speaker_upload_dir(speaker_id: UUID) -> Path:
    """Get upload directory for a speaker."""
    return settings.upload_dir / "speakers" / str(speaker_id)


def get_upload_path(project_id: UUID, filename: str) -> Path:
    """Get upload file path for a project."""
    directory = get_project_upload_dir(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / _sanitize_filename(filename)


def get_speaker_upload_path(speaker_id: UUID, filename: str) -> Path:
    """Get upload file path for a speaker."""
    directory = get_speaker_upload_dir(speaker_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / _sanitize_filename(filename)


def get_output_path(project_id: UUID, filename: str) -> Path:
    """Get output file path."""
    directory = settings.output_dir / str(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / _sanitize_filename(filename)


def get_relative_url(path: Path) -> str:
    """Get relative URL for a stored file.

    Note: returns a URL relative to the upload root. For files nested in
    project/speaker directories, the name alone is not unique; callers should
    use file IDs instead of names for public URLs.
    """
    return f"/files/{path.name}"


async def save_upload(file_obj: BinaryIO, project_id: UUID, filename: str) -> str:
    """Save uploaded file to project storage and return relative path string."""
    destination = get_upload_path(project_id, filename)
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file_obj, buffer)
    return _relative_path(destination)


async def save_speaker_upload(file_obj: BinaryIO, speaker_id: UUID, filename: str) -> str:
    """Save uploaded file to speaker storage and return relative path string."""
    destination = get_speaker_upload_path(speaker_id, filename)
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file_obj, buffer)
    return _relative_path(destination)


def resolve_file_path(relative_path: str | None) -> Path | None:
    """Resolve a stored relative path to an absolute Path."""
    if not relative_path:
        return None
    return settings.upload_dir / relative_path


def delete_file(relative_path: str | None) -> None:
    """Delete a file by its stored relative path."""
    path = resolve_file_path(relative_path)
    if path and path.exists():
        path.unlink()


def delete_project_files(project_id: UUID) -> None:
    """Delete all files for a project."""
    upload_dir = get_project_upload_dir(project_id)
    if upload_dir.exists():
        shutil.rmtree(upload_dir)


def delete_speaker_files(speaker_id: UUID) -> None:
    """Delete all files for a speaker."""
    upload_dir = get_speaker_upload_dir(speaker_id)
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
