"""Build and locally edit the two Phase-A sample Compositions.

The JSON fixtures are portable: symbolic ``$source`` references are resolved to
owner-scoped Assets and immutable SourceSnapshots at runtime. Composition and
CompositionVersion rows are created ONLY through ``apply_composition_edits``.
No Run, Output, queue row, LLM/TTS call, billing, or production Chat entry is
involved. Deterministic request IDs make an interrupted rerun replay safely.

    uv run python scripts/video_project_samples.py \
      --owner-id <uuid> --origin-project-id <uuid> \
      --out-dir /tmp/repurposer-video-project-a2

The command exports base/edited content, renderer-neutral specs, and absolute-
URL render specs. Render those with apps/render/scripts/render-video-local.ts.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.editing.edits import Op  # noqa: E402
from app.editing.schemas import CompositionContent, TextObject  # noqa: E402
from app.tools.video.preparation import (  # noqa: E402
    ensure_font_resources,
    snapshot_audio_asset,
    snapshot_web_asset,
    store_source_bytes,
)
from app.editing.store import apply_composition_edits, content_of, snapshot_facts  # noqa: E402
from app.editing.video_spec import compile_video_spec  # noqa: E402
from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import AssetStatus, AssetType, canonical_json_hash  # noqa: E402
from app.models.tables import Asset, Project, SourceSnapshot  # noqa: E402
from app.pipeline.rendering import _absolutize_video  # noqa: E402

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests/fixtures/video_project"
MEDIA_ROOT = FIXTURE_ROOT / "media"
SAMPLE_FILES = {"website": "website.json", "mg": "mg.json"}
OPS = TypeAdapter(list[Op])
_NAMESPACE = uuid5(UUID(int=0), "repurposer-video-project-phase-a-samples")


class FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WebViewFixture(FixtureModel):
    view_id: str = Field(min_length=1, max_length=64)
    file: str
    source_y: int = Field(ge=0)
    heading: str
    elements: list[dict[str, Any]]


class WebMaterial(FixtureModel):
    kind: Literal["web"]
    title: str
    canonical_url: str
    captured_at: datetime
    origin: dict[str, Any]
    views: list[WebViewFixture] = Field(min_length=1)


class AudioMaterial(FixtureModel):
    kind: Literal["audio"]
    title: str
    file: str
    origin: dict[str, Any]


Material = Annotated[WebMaterial | AudioMaterial, Field(discriminator="kind")]


class SampleFixture(FixtureModel):
    format_version: Literal[1]
    sample_id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    name: str
    sources: dict[str, Material]
    create_ops: list[dict[str, Any]]
    edit_ops: list[dict[str, Any]] = Field(min_length=1)
    edit_target: str


def load_sample_fixture(path: Path) -> SampleFixture:
    return SampleFixture.model_validate(json.loads(path.read_text()))


def _media_file(filename: str) -> Path:
    if Path(filename).name != filename:
        raise ValueError(f"fixture media must be a plain filename: {filename!r}")
    path = MEDIA_ROOT / filename
    if not path.is_file():
        raise ValueError(f"fixture media is missing: {path}")
    return path


def _file_digests(material: Material) -> dict[str, str]:
    filenames = (
        [view.file for view in material.views]
        if isinstance(material, WebMaterial)
        else [material.file]
    )
    return {
        filename: hashlib.sha256(_media_file(filename).read_bytes()).hexdigest()
        for filename in filenames
    }


def _asset_id(
    owner_id: UUID, project_id: UUID, sample: SampleFixture, ref: str, material: Material
) -> UUID:
    identity = canonical_json_hash(
        {
            "owner_id": str(owner_id),
            "project_id": str(project_id),
            "sample_id": sample.sample_id,
            "source_ref": ref,
            "material": material.model_dump(mode="json"),
            "file_digests": _file_digests(material),
        }
    )
    return uuid5(_NAMESPACE, f"asset:{identity}")


def _check_existing_asset(
    asset: Asset,
    *,
    asset_id: UUID,
    owner_id: UUID,
    project_id: UUID,
    kind: AssetType,
    file_url: str | None,
    title: str,
    meta: dict[str, Any],
) -> None:
    actual = (
        asset.user_id,
        asset.project_id,
        asset.type,
        asset.file_url,
        asset.title,
        asset.meta,
    )
    expected = (owner_id, project_id, kind, file_url, title, meta)
    if actual != expected:
        raise ValueError(f"deterministic fixture Asset {asset_id} does not match its source facts")


async def _prepare_source(
    db: AsyncSession,
    *,
    owner_id: UUID,
    project_id: UUID,
    sample: SampleFixture,
    ref: str,
    material: Material,
) -> SourceSnapshot:
    asset_id = _asset_id(owner_id, project_id, sample, ref, material)
    kind: AssetType
    if isinstance(material, WebMaterial):
        shots = []
        for view in material.views:
            key, _ = await store_source_bytes(
                _media_file(view.file).read_bytes(), ".png", "image/png"
            )
            shots.append(
                {
                    "view_id": view.view_id,
                    "key": key,
                    "y": view.source_y,
                    "heading": view.heading,
                    "elements": view.elements,
                }
            )
        kind = AssetType.WEB_PAGE
        file_url = None
        meta: dict[str, Any] = {
            "capture_url": material.canonical_url,
            "origin": material.origin,
            "shots": shots,
        }
        created_at = material.captured_at
    else:
        suffix = _media_file(material.file).suffix
        file_url, _ = await store_source_bytes(
            _media_file(material.file).read_bytes(), suffix, "audio/wav"
        )
        kind = AssetType.AUDIO
        meta = {"origin": material.origin}
        created_at = None

    asset = await db.get(Asset, asset_id)
    if asset is None:
        asset = Asset(
            id=asset_id,
            user_id=owner_id,
            project_id=project_id,
            type=kind,
            file_url=file_url,
            title=material.title,
            processing_status=AssetStatus.COMPLETED,
            processing_requested_at=None,
            meta=meta,
        )
        if created_at is not None:
            asset.created_at = created_at
        db.add(asset)
        await db.flush()
    else:
        _check_existing_asset(
            asset,
            asset_id=asset_id,
            owner_id=owner_id,
            project_id=project_id,
            kind=kind,
            file_url=file_url,
            title=material.title,
            meta=meta,
        )

    if isinstance(material, WebMaterial):
        return await snapshot_web_asset(db, asset, owner_id=owner_id)
    return await snapshot_audio_asset(db, asset, owner_id=owner_id)


def resolve_ops(raw_ops: list[dict[str, Any]], snapshots: dict[str, SourceSnapshot]) -> list[Op]:
    """Resolve only explicit source-reference slots; unknown refs are errors."""

    def resolve(value: Any, key: str | None = None) -> Any:
        if isinstance(value, dict):
            return {item_key: resolve(item, item_key) for item_key, item in value.items()}
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if key in {"snapshot_id", "snapshot_digest"} and isinstance(value, str):
            if not value.startswith("$"):
                raise ValueError(f"portable fixture {key} must use a $source reference")
            ref = value[1:].removesuffix(".digest")
            invalid = (
                ref not in snapshots
                or (key == "snapshot_id" and value.endswith(".digest"))
                or (key == "snapshot_digest" and not value.endswith(".digest"))
            )
            if invalid:
                raise ValueError(f"invalid source reference {value!r}")
            snapshot = snapshots[ref]
            return str(snapshot.id) if key == "snapshot_id" else snapshot.digest
        return value

    return OPS.validate_python(resolve(raw_ops))


def _clip_location(content: CompositionContent, clip_id: str) -> tuple[int, int, Any]:
    for track_index, track in enumerate(content.timeline.tracks):
        for clip_index, clip in enumerate(track.clips):
            if clip.clip_id == clip_id:
                return track_index, clip_index, clip
    raise ValueError(f"edit target {clip_id} does not exist")


def assert_local_text_edit(
    base: CompositionContent, edited: CompositionContent, clip_id: str
) -> dict[str, Any]:
    """Prove one text changed and every unrelated content fact stayed equal."""
    _, _, before = _clip_location(base, clip_id)
    after_track, after_index, after = _clip_location(edited, clip_id)
    if not isinstance(before.object, TextObject) or not isinstance(after.object, TextObject):
        raise ValueError("this sample's edit proof requires a TextObject target")
    if before.object.text == after.object.text:
        raise ValueError(f"edit target {clip_id} did not change")

    reverted_target = copy.deepcopy(after)
    reverted_target.object.text = before.object.text
    if reverted_target.model_dump(mode="json") != before.model_dump(mode="json"):
        raise ValueError(f"edit target {clip_id} changed more than object.text")

    reverted_content = copy.deepcopy(edited)
    reverted_content.timeline.tracks[after_track].clips[after_index] = copy.deepcopy(before)
    if reverted_content.model_dump(mode="json") != base.model_dump(mode="json"):
        raise ValueError("local edit changed content outside its target clip")
    return {
        "clip_id": clip_id,
        "field": "object.text",
        "before": before.object.text,
        "after": after.object.text,
        "unrelated_content_unchanged": True,
    }


def _assert_unrelated_spec_clips(base: dict, edited: dict, target: str) -> list[str]:
    def clips(spec: dict) -> dict[str, dict]:
        return {clip["clip_id"]: clip for track in spec["tracks"] for clip in track["clips"]}

    before = clips(base)
    after = clips(edited)
    if before.keys() != after.keys():
        raise ValueError("local edit changed the compiled clip set")
    unchanged = []
    for clip_id in sorted(before):
        if clip_id == target:
            continue
        if before[clip_id] != after[clip_id]:
            raise ValueError(f"unrelated compiled clip changed: {clip_id}")
        unchanged.append(clip_id)
    if base["fonts"] != edited["fonts"]:
        raise ValueError("local text edit changed the pinned font resources")
    return unchanged


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


async def _build_sample(
    fixture: SampleFixture,
    *,
    owner_id: UUID,
    project_id: UUID,
    out_dir: Path,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        if project is None or project.user_id != owner_id:
            raise PermissionError("origin project is unavailable to this owner")
        snapshots = {
            ref: await _prepare_source(
                db,
                owner_id=owner_id,
                project_id=project_id,
                sample=fixture,
                ref=ref,
                material=material,
            )
            for ref, material in fixture.sources.items()
        }
        await db.commit()

    fixture_digest = canonical_json_hash(fixture.model_dump(mode="json"))
    create_request = uuid5(_NAMESPACE, f"create:{owner_id}:{project_id}:{fixture_digest}").hex
    create_ops = resolve_ops(fixture.create_ops, snapshots)
    async with AsyncSessionLocal() as db:
        composition, base, create_replayed = await apply_composition_edits(
            db,
            owner_id=owner_id,
            origin_project_id=project_id,
            ops=create_ops,
            request_id=create_request,
            name=fixture.name,
        )

    edit_request = uuid5(_NAMESPACE, f"edit:{create_request}:{base.id}:{fixture_digest}").hex
    edit_ops = resolve_ops(fixture.edit_ops, snapshots)
    async with AsyncSessionLocal() as db:
        _, edited, edit_replayed = await apply_composition_edits(
            db,
            owner_id=owner_id,
            composition_id=composition.id,
            base_version_id=base.id,
            base_digest=base.content_digest,
            ops=edit_ops,
            request_id=edit_request,
        )

    base_content = content_of(base)
    edited_content = content_of(edited)
    edit_proof = assert_local_text_edit(base_content, edited_content, fixture.edit_target)

    async with AsyncSessionLocal() as db:
        facts = await snapshot_facts(db, set(snapshots[ref].id for ref in snapshots))
    base_spec = compile_video_spec(
        base_content,
        facts,
        composition_id=composition.id,
        version_id=base.id,
        content_digest=base.content_digest,
    )
    edited_spec = compile_video_spec(
        edited_content,
        facts,
        composition_id=composition.id,
        version_id=edited.id,
        content_digest=edited.content_digest,
    )
    edit_proof["unchanged_compiled_clip_ids"] = _assert_unrelated_spec_clips(
        base_spec, edited_spec, fixture.edit_target
    )

    sample_dir = out_dir / fixture.sample_id
    sample_dir.mkdir(parents=True, exist_ok=True)
    _write_json(sample_dir / "base.content.json", base_content.model_dump(mode="json"))
    _write_json(sample_dir / "edited.content.json", edited_content.model_dump(mode="json"))
    _write_json(sample_dir / "base.video-spec.json", base_spec)
    _write_json(sample_dir / "edited.video-spec.json", edited_spec)
    _write_json(sample_dir / "base.render-spec.json", _absolutize_video(copy.deepcopy(base_spec)))
    _write_json(
        sample_dir / "edited.render-spec.json", _absolutize_video(copy.deepcopy(edited_spec))
    )
    result = {
        "sample_id": fixture.sample_id,
        "fixture_digest": fixture_digest,
        "composition_id": str(composition.id),
        "base_version": {
            "id": str(base.id),
            "version": base.version,
            "content_digest": base.content_digest,
            "request_replayed": create_replayed,
        },
        "edited_version": {
            "id": str(edited.id),
            "version": edited.version,
            "base_version_id": str(edited.base_version_id),
            "content_digest": edited.content_digest,
            "request_replayed": edit_replayed,
        },
        "sources": {
            ref: {
                "snapshot_id": str(snapshot.id),
                "asset_id": str(snapshot.asset_id),
                "kind": snapshot.kind,
                "digest": snapshot.digest,
                "storage_key": snapshot.storage_key,
                "duration_ticks": snapshot.duration_ticks,
            }
            for ref, snapshot in snapshots.items()
        },
        "edit_proof": edit_proof,
        "directory": str(sample_dir),
    }
    _write_json(sample_dir / "result.json", result)
    return result


async def _main(args: argparse.Namespace) -> None:
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    await ensure_font_resources()
    results = []
    for sample_id in args.sample or list(SAMPLE_FILES):
        fixture = load_sample_fixture(FIXTURE_ROOT / SAMPLE_FILES[sample_id])
        results.append(
            await _build_sample(
                fixture,
                owner_id=args.owner_id,
                project_id=args.origin_project_id,
                out_dir=out_dir,
            )
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", type=UUID, required=True)
    parser.add_argument("--origin-project-id", type=UUID, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/repurposer-video-project-a2"))
    parser.add_argument("--sample", choices=sorted(SAMPLE_FILES), action="append")
    args = parser.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
