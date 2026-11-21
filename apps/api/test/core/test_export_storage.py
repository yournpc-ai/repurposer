from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Response

from app.providers import storage


@pytest.mark.parametrize("prefix", ["exports/", "public-test-exports/"])
def test_export_location_pins_public_bucket_and_output(monkeypatch, prefix):
    monkeypatch.setattr(storage.settings, "s3_bucket_name", "cuts")
    monkeypatch.setattr(storage.settings, "s3_public_url", "https://cuts.example")
    owner, project, output = uuid4(), uuid4(), uuid4()
    path = f"{prefix}{owner}/{project}/{output}.mp4"
    location = f"tos://cuts/{path}"
    assert storage._bucket(location) == "cuts"
    assert storage._normalize_key(location) == path
    assert storage.public_url(location) == f"https://cuts.example/{path}"
    assert storage.matches_export_location(location, owner, project, output)
    for identity in [(uuid4(), project, output), (owner, uuid4(), output), (owner, project, uuid4())]:
        assert not storage.matches_export_location(location, *identity)
    for other in [location.replace("tos://cuts/", "tos://other/"), location.replace(prefix, "other/")]:
        assert storage.public_url(other) is None
        with pytest.raises(ValueError):
            storage._bucket(other)


@pytest.mark.asyncio
async def test_output_plays_from_public_url_and_download_keeps_filename(monkeypatch):
    outputs = import_module("app.pipeline.routes.outputs")
    owner, project, oid = uuid4(), uuid4(), uuid4()
    location = f"{storage.export_root()}{owner}/{project}/{oid}.mp4"
    output = SimpleNamespace(id=oid, project_id=project, files={"video": location})
    monkeypatch.setattr(outputs, "get_output_for_user", AsyncMock(return_value=output))
    sign = AsyncMock(return_value="attachment-url")
    monkeypatch.setattr(outputs, "presign_download", sign)
    args = dict(output_id=oid, current_user=SimpleNamespace(id=owner), db=None, response=Response())
    assert await outputs.playback(**args) == {"url": storage.public_url(location), "expires_in": None}
    sign.assert_not_awaited()
    assert (await outputs.playback(**args, download=True))["url"] == "attachment-url"
    sign.assert_awaited_once_with(location, ttl=300, filename=f"{oid}.mp4")
