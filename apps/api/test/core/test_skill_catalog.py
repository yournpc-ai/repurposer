"""SkillVersion loading, package safety, real media and bounded reads."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.skills.external import (
    SkillSource,
    build_skill_draft,
)
from app.skills.loading import load_skill_creative_context



@pytest.mark.asyncio
async def test_media_free_skill_can_discover_only_declared_generator():
    from app.models.schemas import canonical_json_hash
    from app.skills.external import skill_draft_payload
    from app.skills.package_reader import SkillPackageError, SkillPackageReader
    from app.skills.package_session import ListSkillShotsArgs, SkillPackageSession

    import json

    declaration = {
        "entry": "template/generators/entry.tsx",
        "composition_id": "Chart",
        "files": ["template/generators/entry.tsx", "template/cards/chart.tsx"],
        "output": {"width": 960, "height": 540, "duration_frames": 60, "background": "#ffffff"},
    }
    draft = build_skill_draft({
        "SKILL.md": b"---\nname: chart\ndescription: Chart animations.\n---\nUse a data card.\n",
        "template/generators/chart.json": json.dumps(declaration).encode(),
        "template/generators/entry.tsx": b"export {};",
        "template/cards/chart.tsx": b"export {};",
        "demos/reference-only.tsx": b"export {};",
    }, declared_capabilities={"runtime:remotion-source"})
    payload = skill_draft_payload(draft)
    owner_id, skill_id = uuid4(), uuid4()
    reader = SkillPackageReader(
        version=SimpleNamespace(
            **payload, id=uuid4(), owner_id=owner_id, skill_id=skill_id,
            media=[], version_digest=canonical_json_hash(payload),
        ),
        skill=SimpleNamespace(
            id=skill_id, owner_id=owner_id, name=draft.name, description=draft.description,
        ),
    )
    session = SkillPackageSession(reader, owner_id=owner_id, package_identity=uuid4())
    observed = await session.observe("list_skill_shots", ListSkillShotsArgs())
    assert observed.ok
    resources = json.loads(observed.text)["generator_resources"]
    parsed, digest = await session.generator_declaration("chart")
    assert parsed.entry == declaration["entry"]
    assert resources == [{
        "id": "chart", "composition_id": "Chart", "duration_seconds": 2.0, "digest": digest,
    }]
    with pytest.raises(SkillPackageError, match="missing"):
        await session.generator_declaration("reference-only")


def _source(path: str = "references/method.md", *, role: str = "reference") -> SkillSource:
    text = "Use a variable-width stroke after the title settles."
    return SkillSource(
        path=path,
        role=role,
        digest=hashlib.sha256(text.encode()).hexdigest(),
        text=text,
    )


def test_method_only_external_skill_is_selectable_without_runner_capabilities(monkeypatch):
    from app.config import settings
    from app.skills.resolution import _external_option

    monkeypatch.setattr(settings, "component_bake_enabled", False)
    skill = SimpleNamespace(id=uuid4(), name="chart", description="Chart direction")
    for declared in ([], ["runtime:remotion-source"]):
        version = SimpleNamespace(id=uuid4(), version=1, capability_report={"supported": declared})
        option = _external_option(skill, version)
        assert option.reference.skill_version_id == version.id
        assert option.capabilities == ["progressive_skill_package"]










@pytest.mark.asyncio
async def test_managed_promo_reads_upstream_gallery_and_pins_release(tmp_path, monkeypatch):
    import json

    from app.config import settings
    from app.skills.package_reader import open_builtin_skill_package
    from app.skills.resolution import SkillResolutionError, get_builtin_skill_option

    release = tmp_path / "promo-video" / "snapshot-a"
    card = release / "references/shots/opening/brand.md"
    card.parent.mkdir(parents=True)
    card.write_text("# Source card")
    (release / "SKILL.md").write_text(
        "---\nname: video-shotcraft\ndescription: Upstream method\n---\nUse the actual card."
    )
    gallery = release / "gallery/api/library.json"
    gallery.parent.mkdir(parents=True)
    gallery.write_text(json.dumps({"cards": [{
        "name": "brand",
        "source": "references/shots/opening/brand.md",
        "category": "opening",
        "styles": [{"key": "brand", "label": "Brand", "media": {"url": "./media/brand.mp4"}}],
    }]}))
    monkeypatch.setattr(settings, "managed_skill_root", tmp_path)
    monkeypatch.setattr(settings, "managed_skill_versions", {"promo-video": "snapshot-a"})

    option = get_builtin_skill_option("promo-video")
    assert option.name == "video-shotcraft"
    with pytest.raises(SkillResolutionError, match="unavailable"):
        get_builtin_skill_option("text-animation", version="1.0.0")
    with pytest.raises(SkillResolutionError, match="unavailable"):
        get_builtin_skill_option("promo-video", version="1.0.0")
    reader = open_builtin_skill_package("promo-video", option.reference.version)
    assert (await reader.read_text("SKILL.md")).text == (release / "SKILL.md").read_text()
    entry, = (await reader.library_index()).entries
    assert entry.id == "brand"
    assert entry.variants[0].id == "brand"
    assert not entry.previews
    assert (await reader.read_text(entry.path)).text == "# Source card"


@pytest.mark.asyncio
async def test_loader_bounds_progressive_reads_and_rejects_source_drift(monkeypatch):
    import json

    from app.skills.package_reader import SkillPackageError, SkillPackageReader
    from app.skills.package_session import ReadSkillReferenceArgs

    row = SimpleNamespace(
        id=uuid4(),
        skill_id=uuid4(),
        owner_id=uuid4(),
        references=[_source().model_dump(mode="json")],
        media=None,
        version_digest=None,
        declared_inputs=[],
        policy={},
        instructions="method",
    )
    skill = SimpleNamespace(id=row.skill_id, owner_id=row.owner_id)

    async def read(*_args, **_kwargs):
        return row

    async def open_package(*_args, **_kwargs):
        return SkillPackageReader(version=row, skill=skill)

    monkeypatch.setattr("app.skills.store.get_skill_version", read)
    monkeypatch.setattr("app.skills.loading.open_external_skill_package", open_package)
    loaded = await load_skill_creative_context(
        object(), owner_id=row.owner_id, skill_version_id=row.id
    )
    assert row.instructions in loaded.package.initial_content
    reference = await loaded.package.observe(
        "read_skill_reference", ReadSkillReferenceArgs(path=_source().path)
    )
    assert reference.ok
    assert json.loads(reference.text)["text"] == _source().text

    row.references = [
        _source("scripts/ignored.py", role="script").model_dump(mode="json")
    ]
    loaded = await load_skill_creative_context(
        object(), owner_id=row.owner_id, skill_version_id=row.id
    )
    script = await loaded.package.observe(
        "read_skill_reference", ReadSkillReferenceArgs(path="scripts/ignored.py")
    )
    assert not script.ok
    assert "outside readable package roots" in script.text

    drifted = _source().model_dump(mode="json")
    drifted["digest"] = "0" * 64
    row.references = [drifted]
    with pytest.raises(SkillPackageError, match="digest mismatch"):
        await load_skill_creative_context(
            object(), owner_id=row.owner_id, skill_version_id=row.id
        )


@pytest.mark.asyncio
async def test_shared_package_budget_survives_repairs_and_preflights_media():
    import time

    from app.skills.package_session import (
        SkillPackageBudgetError,
        SkillPackageSession,
        _MAX_CALLS,
        _MAX_GENERATIONS,
        _MAX_MEDIA_BYTES,
        _MAX_MEDIA_FILES,
        _MAX_TEXT_CHARS,
    )

    class Reader:
        def __init__(self):
            self.media_reads = 0

        async def read_text(self, path):
            return SimpleNamespace(text="bounded evidence", digest=hashlib.sha256(path.encode()).hexdigest())

        async def read_media(self, path):
            self.media_reads += 1
            return b"verified-image"

    owner_id = uuid4()
    version_id = uuid4()
    session = SkillPackageSession(Reader(), owner_id=owner_id, package_identity=version_id)
    await session.read_initial([f"references/item-{index}.md" for index in range(_MAX_CALLS)])
    with pytest.raises(SkillPackageBudgetError, match="call budget"):
        await session.read_initial(["references/one-more.md"])

    # Initial design, schema repair and grounding repair share this one counter.
    for _ in range(_MAX_GENERATIONS):
        session.charge_generation()
    with pytest.raises(SkillPackageBudgetError, match="generation budget"):
        session.charge_generation()

    media = SkillPackageSession(Reader(), owner_id=owner_id, package_identity=version_id)
    binding = {
        "path": "assets/poster.png",
        "snapshot_digest": hashlib.sha256(b"verified-image").hexdigest(),
        "content_type": "image/png",
        "byte_size": len(b"verified-image"),
    }
    assert await media.read_fixed_image(binding) == b"verified-image"
    assert await media.read_fixed_image(binding) == b"verified-image"
    assert media.reader.media_reads == 1
    assert media.media_files == 1
    oversized = {**binding, "path": "assets/large.png", "byte_size": _MAX_MEDIA_BYTES}
    with pytest.raises(SkillPackageBudgetError, match="byte budget"):
        await media.read_fixed_image(oversized)
    assert media.reader.media_reads == 1
    media.media_files = _MAX_MEDIA_FILES
    with pytest.raises(SkillPackageBudgetError, match="count budget"):
        await media.read_fixed_image({**binding, "path": "assets/count.png"})
    assert media.reader.media_reads == 1

    text = SkillPackageSession(Reader(), owner_id=owner_id, package_identity=version_id)
    text.text_chars = _MAX_TEXT_CHARS
    with pytest.raises(SkillPackageBudgetError, match="text budget"):
        await text.read_initial(["references/text-overflow.md"])


def test_original_scale_packages_do_not_need_reference_pruning_to_import():
    files = {"SKILL.md": b"---\nname: generic-pack\ndescription: Methods.\n---\nUse a method.\n"}
    files.update({f"references/item-{index}.md": b"reference" for index in range(300)})
    files["assets/large-video.mp4"] = b"0" * (1024 * 1024 + 1)
    draft = build_skill_draft(files, declared_capabilities=[])
    assert len(draft.references) == 300
    assert draft.capability_report.rejected_files == {
        "assets/large-video.mp4": "unsupported_source_type"
    }
    assert draft.name == "generic-pack"


