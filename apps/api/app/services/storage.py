"""Storage service for uploads and outputs.

All files are stored under ``assets/``:

- User-scoped: ``assets/{user_id}/uploads/projects/{project_id}/{file}``,
  ``assets/{user_id}/speakers/{speaker_id}/{file}``,
  ``assets/{user_id}/outputs/projects/{project_id}/{file}``.
- Demo: ``assets/demo/uploads/projects/{project_id}/{file}`` and
  ``assets/demo/outputs/projects/{project_id}/{file}``.

Public URLs remain ``/api/v1/files/{relative_path}`` and
``/api/v1/outputs/{relative_path}``; the path itself now embeds the owning
user/demo prefix so the file endpoint can enforce ownership.
"""

import base64
import mimetypes
import shutil
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from app.config import settings

# The seeded default user shares the "demo" storage prefix so MVP assets live
# under the short, readable `assets/demo/` tree instead of a long UUID path.
_DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"
_DEMO_PROJECT_ID = "11111111-1111-1111-1111-111111111111"


def _storage_prefix(user_id: UUID | str) -> str:
    """Return the top-level directory name for a user's assets."""
    if str(user_id) == _DEFAULT_USER_ID:
        return "demo"
    return str(user_id)


def _is_demo_project(project_id: UUID | str) -> bool:
    return str(project_id) == _DEMO_PROJECT_ID


def _sanitize_filename(filename: str) -> str:
    """Sanitize upload filename to prevent path traversal.

    Strips directory components and replaces path separators.
    Falls back to 'unnamed' if the result is empty.
    """
    name = Path(filename).name
    name = name.replace("/", "_").replace("\\", "_")
    return name or "unnamed"


def _unique_path(directory: Path, filename: str) -> Path:
    """Return a unique path inside directory, appending a counter if needed."""
    base = directory / _sanitize_filename(filename)
    if not base.exists():
        return base

    stem = base.stem
    suffix = base.suffix
    counter = 1
    while True:
        candidate = directory / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _relative_path(path: Path) -> str:
    """Return path relative to asset_dir as a POSIX string."""
    try:
        return path.relative_to(settings.asset_dir).as_posix()
    except ValueError:
        return path.as_posix()


def get_project_upload_dir(project_id: UUID, user_id: UUID | str) -> Path:
    """Get upload directory for a project.

    Demo project uses a flat ``uploads/`` directory without a ``projects/``
    subfolder, matching cloud-storage conventions where source uploads are
    independent objects rather than nested under a project.
    """
    prefix = _storage_prefix(user_id)
    if _is_demo_project(project_id):
        return settings.asset_dir / prefix / "uploads"
    return settings.asset_dir / prefix / "uploads" / "projects" / str(project_id)


def get_speaker_upload_dir(speaker_id: UUID, user_id: UUID | str) -> Path:
    """Get upload directory for a speaker."""
    return settings.asset_dir / _storage_prefix(user_id) / "speakers" / str(speaker_id)


def get_project_output_dir(project_id: UUID, user_id: UUID | str) -> Path:
    """Get output directory for a project.

    Demo project uses a flat ``outputs/`` directory without a ``projects/``
    subfolder so rendered clips and derivatives sit directly under
    ``assets/demo/outputs/``.
    """
    prefix = _storage_prefix(user_id)
    if _is_demo_project(project_id):
        return settings.asset_dir / prefix / "outputs"
    return settings.asset_dir / prefix / "outputs" / "projects" / str(project_id)


def get_upload_path(project_id: UUID, user_id: UUID | str, filename: str) -> Path:
    """Get upload file path for a project."""
    directory = get_project_upload_dir(project_id, user_id)
    directory.mkdir(parents=True, exist_ok=True)
    return _unique_path(directory, filename)


def get_speaker_upload_path(speaker_id: UUID, user_id: UUID | str, filename: str) -> Path:
    """Get upload file path for a speaker."""
    directory = get_speaker_upload_dir(speaker_id, user_id)
    directory.mkdir(parents=True, exist_ok=True)
    return _unique_path(directory, filename)


def get_output_path(project_id: UUID, user_id: UUID | str, filename: str) -> Path:
    """Get output file path for a project."""
    directory = get_project_output_dir(project_id, user_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / _sanitize_filename(filename)


async def save_upload(
    file_obj: BinaryIO,
    project_id: UUID,
    user_id: UUID | str,
    filename: str,
) -> str:
    """Save uploaded file to project storage and return relative path string."""
    destination = get_upload_path(project_id, user_id, filename)
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file_obj, buffer)
    return _relative_path(destination)


async def save_speaker_upload(
    file_obj: BinaryIO,
    speaker_id: UUID,
    user_id: UUID | str,
    filename: str,
) -> str:
    """Save uploaded file to speaker storage and return relative path string."""
    destination = get_speaker_upload_path(speaker_id, user_id, filename)
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file_obj, buffer)
    return _relative_path(destination)


async def save_output(
    project_id: UUID,
    user_id: UUID | str,
    filename: str,
    content: bytes,
) -> str:
    """Save output bytes to project storage and return relative path string."""
    destination = get_output_path(project_id, user_id, filename)
    destination.write_bytes(content)
    return _relative_path(destination)


def resolve_file_path(relative_path: str | None) -> Path | None:
    """Resolve a stored relative path to an absolute Path under asset_dir."""
    if not relative_path:
        return None
    return settings.asset_dir / relative_path


def file_to_data_url(path: Path) -> str | None:
    """Return a base64 data URL for a local file, or None if it cannot be read.

    Multimodal LLMs (MiniMax M3, GPT-4o, Gemini, etc.) typically accept media
    inputs as data URLs in OpenAI-compatible ``image_url`` / ``video_url`` /
    ``audio_url`` content parts. This helper keeps the pipeline self-contained
    when files are stored locally.
    """
    if not path or not path.is_file():
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def resolve_safe(relative_path: str | None) -> Path | None:
    """Resolve a relative path under asset_dir, refusing traversal escapes."""
    return _resolve_within(settings.asset_dir, relative_path)


def resolve_output_safe(relative_path: str | None) -> Path | None:
    """Resolve a relative output path under asset_dir, refusing traversal."""
    return _resolve_within(settings.asset_dir, relative_path)


# Audio extensions the built-in mood library may use, in resolution priority.
_MUSIC_EXTS = (".mp3", ".m4a", ".aac", ".ogg", ".wav")


def resolve_music_safe(name: str | None) -> Path | None:
    """Resolve a mood name (e.g. ``calm``) to its track file under music_dir.

    The track URL is extension-less (``/api/v1/music/calm``); this finds the
    first ``calm.<ext>`` present, so dropping in ``calm.mp3`` just works. Refuses
    traversal (the name must be a bare stem).
    """
    if not name or "/" in name or "\\" in name or "." in name:
        return None
    root = settings.music_dir.resolve()
    for ext in _MUSIC_EXTS:
        candidate = (root / f"{name}{ext}").resolve()
        if (root == candidate or root in candidate.parents) and candidate.is_file():
            return candidate
    return None


def _resolve_within(base: Path, relative_path: str | None) -> Path | None:
    """Resolve ``relative_path`` under ``base``, or None if empty/escaping."""
    if not relative_path:
        return None
    root = base.resolve()
    candidate = (root / relative_path).resolve()
    if root == candidate or root in candidate.parents:
        return candidate
    return None


def stream_url(relative_path: str | None) -> str | None:
    """Browser-playable URL for an uploaded file (storage seam; see VIDEO_EDITOR §5)."""
    if not relative_path:
        return None
    return f"/api/v1/files/{relative_path}"


def output_url(relative_path: str | None) -> str | None:
    """Browser-playable URL for a rendered output (MP4/SRT) under asset_dir."""
    if not relative_path:
        return None
    return f"/api/v1/outputs/{relative_path}"


def music_url(mood: str | None) -> str | None:
    """Storage-seam URL for a mood track (extension-less; resolver finds the file)."""
    if not mood:
        return None
    return f"/api/v1/music/{mood}"


def delete_file(relative_path: str | None) -> None:
    """Delete a file by its stored relative path."""
    path = resolve_file_path(relative_path)
    if path and path.exists():
        path.unlink()


def delete_project_files(project_id: UUID, user_id: UUID | str) -> None:
    """Delete all files for a project."""
    upload_dir = get_project_upload_dir(project_id, user_id)
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    output_dir = get_project_output_dir(project_id, user_id)
    if output_dir.exists():
        shutil.rmtree(output_dir)


def delete_speaker_files(speaker_id: UUID, user_id: UUID | str) -> None:
    """Delete all files for a speaker."""
    upload_dir = get_speaker_upload_dir(speaker_id, user_id)
    if upload_dir.exists():
        shutil.rmtree(upload_dir)


def owner_from_path(relative_path: str | None) -> str | None:
    """Extract the owning user id (or 'demo') from a stored relative path.

    Returns None for empty/malformed paths.
    """
    if not relative_path:
        return None
    first = relative_path.split("/", 1)[0]
    return first if first else None
