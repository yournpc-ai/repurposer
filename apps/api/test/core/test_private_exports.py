from uuid import uuid4

import pytest

from app.providers import storage


def test_export_location_pins_bucket_and_never_forms_public_url(monkeypatch):
    monkeypatch.setattr(storage.settings, "s3_private_export_bucket", "private-cut")
    owner, project, output = uuid4(), uuid4(), uuid4()
    location = storage.private_export_key(owner, project, output)
    assert location == f"tos://private-cut/private-exports/{owner}/{project}/{output}.mp4"
    assert storage.public_url(location) is None
    assert storage._bucket(location) == "private-cut"
    assert storage._normalize_key(location) == f"private-exports/{owner}/{project}/{output}.mp4"
    assert storage._bucket("private-exports/legacy.mp4") == storage.settings.s3_bucket_name

    monkeypatch.setattr(storage.settings, "s3_private_export_bucket", "replacement")
    with pytest.raises(ValueError, match="Unknown private object location"):
        storage._bucket(location)


@pytest.mark.parametrize("private_bucket", ["", None])
def test_export_storage_fails_closed_without_private_bucket(monkeypatch, private_bucket):
    monkeypatch.setattr(storage.settings, "s3_private_export_bucket", private_bucket)
    with pytest.raises(ValueError, match="not configured"):
        storage.private_export_key(uuid4(), uuid4(), uuid4())
