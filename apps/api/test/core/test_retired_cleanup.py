from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.tables import Asset, Output, SourceSnapshot
from scripts.cleanup_retired_products import scrub, select_targets, shared_storage_keys


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(self, *, outputs=(), snapshots=(), assets=()):
        self.outputs = outputs
        self.snapshots = snapshots
        self.assets = assets

    async def execute(self, query):
        entity = query.column_descriptions[0]["entity"]
        if entity is Output:
            return Result(self.outputs)
        if entity is SourceSnapshot:
            if query.column_descriptions[0]["name"] == "storage_key":
                return Result([row.storage_key for row in self.snapshots])
            return Result(self.snapshots)
        if entity is Asset:
            return Result([row.file_url for row in self.assets])
        raise AssertionError(f"unexpected cleanup query: {query}")


def output(kind, *, parents=(), composition=False, video_key=None):
    return Output(
        id=uuid4(),
        type=kind,
        source_ref={"parents": [str(item) for item in parents]},
        composition_version_id=uuid4() if composition else None,
        files={"video": video_key} if video_key else {},
    )


@pytest.mark.asyncio
async def test_cleanup_preserves_composition_lineage_and_only_targets_unrelated_clips(monkeypatch):
    quote = output("quote")
    shared_clip = output("clip", parents=[quote.id])
    composition_video = output("video", parents=[shared_clip.id], composition=True)
    unrelated_clip = output("clip")
    db = FakeDB(outputs=[quote, shared_clip, composition_video, unrelated_clip])

    async def no_used_snapshots(_db):
        return set()

    monkeypatch.setattr("scripts.cleanup_retired_products.used_snapshot_ids", no_used_snapshots)
    doomed, preserved = await select_targets(db, include_clips=True)

    assert doomed == [unrelated_clip]
    assert {item.id for item in preserved} == {quote.id, shared_clip.id}
    assert composition_video.id not in {item.id for item in doomed + preserved}


@pytest.mark.asyncio
async def test_cleanup_preserves_storage_shared_by_retained_outputs_and_sources():
    unrelated_clip = output("clip", video_key="retired/unique.mp4")
    shared_clip = output("clip", video_key="shared/clip.mp4")
    new_video = output("video", composition=True, video_key="shared/clip.mp4")
    snapshot = SourceSnapshot(storage_key="snapshots/source.mp4")
    asset = Asset(file_url="uploads/source.mp4")
    db = FakeDB(
        outputs=[unrelated_clip, shared_clip, new_video],
        snapshots=[snapshot],
        assets=[asset],
    )
    db.outputs = [item for item in db.outputs if item.id != unrelated_clip.id]

    shared = await shared_storage_keys(db, {str(unrelated_clip.id)})
    assert shared == {
        "shared/clip.mp4",
        "snapshots/source.mp4",
        "uploads/source.mp4",
    }


def test_reference_scrub_keeps_user_text_and_new_video_references():
    new_id = str(uuid4())
    retired_id = str(uuid4())
    value = {
        "content": "Keep my original wording",
        "output_refs": [new_id, retired_id],
        "mentions": [
            {"type": "output", "id": retired_id},
            {"type": "output", "id": new_id},
            {"type": "asset", "id": retired_id},
        ],
        "focus_output": {"id": retired_id},
        "tasks": [
            {"tool": "write_post"},
            {"tool": "select_clips"},
            {"tool": "produce_video"},
        ],
    }
    cleaned = scrub(value, {retired_id})
    assert cleaned == {
        "content": "Keep my original wording",
        "output_refs": [new_id],
        "mentions": [
            {"type": "output", "id": new_id},
            {"type": "asset", "id": retired_id},
        ],
        "focus_output": None,
        "tasks": [{"tool": "produce_video"}],
    }
