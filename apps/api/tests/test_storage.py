"""Tests for storage path helpers."""

from uuid import UUID

import pytest

from app.config import settings
from app.services.storage import (
    get_output_path,
    get_project_output_dir,
    get_project_upload_dir,
    get_speaker_upload_dir,
    get_upload_path,
    owner_from_path,
    resolve_safe,
)


@pytest.fixture(autouse=True)
def tmp_asset_dir(tmp_path, monkeypatch):
    """Redirect asset_dir to a temporary path for each test."""
    monkeypatch.setattr(settings, "asset_dir", tmp_path / "assets")


USER_ID = UUID("00000000-0000-0000-0000-000000000001")
PROJECT_ID = UUID("11111111-1111-1111-1111-111111111111")
SPEAKER_ID = UUID("22222222-2222-2222-2222-222222222222")


def test_get_project_upload_dir():
    path = get_project_upload_dir(PROJECT_ID, USER_ID)
    assert path == settings.asset_dir / str(USER_ID) / "uploads" / "projects" / str(PROJECT_ID)


def test_get_speaker_upload_dir():
    path = get_speaker_upload_dir(SPEAKER_ID, USER_ID)
    assert path == settings.asset_dir / str(USER_ID) / "speakers" / str(SPEAKER_ID)


def test_get_project_output_dir():
    path = get_project_output_dir(PROJECT_ID, USER_ID)
    assert path == settings.asset_dir / str(USER_ID) / "outputs" / "projects" / str(PROJECT_ID)


def test_get_upload_path_creates_directory():
    path = get_upload_path(PROJECT_ID, USER_ID, "talk.mp4")
    assert path.parent.exists()
    assert path.name == "talk.mp4"


def test_get_output_path_creates_directory():
    path = get_output_path(PROJECT_ID, USER_ID, "clip.mp4")
    assert path.parent.exists()
    assert path.name == "clip.mp4"


def test_resolve_safe_allows_owned_path():
    owned = f"{USER_ID}/outputs/projects/{PROJECT_ID}/clip.mp4"
    path = resolve_safe(owned)
    assert path is not None
    assert path.name == "clip.mp4"


def test_resolve_safe_rejects_traversal():
    path = resolve_safe("../etc/passwd")
    assert path is None


def test_owner_from_path_extracts_user():
    assert owner_from_path(f"{USER_ID}/outputs/clip.mp4") == str(USER_ID)


def test_owner_from_path_returns_demo():
    assert owner_from_path("demo/outputs/clip.mp4") == "demo"


def test_owner_from_path_returns_none_for_empty():
    assert owner_from_path("") is None
    assert owner_from_path(None) is None
