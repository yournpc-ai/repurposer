"""Layer 0 pure contracts: external skill archive safety, progressive catalog reads, /text-animation & blueprint_summary."""

from __future__ import annotations
import pytest

import pytest


from app.skills.external import ExternalSkillError, build_skill_draft


_ROOT = b"""---
name: video-shotcraft
description: Shot-card methods and implementation references.
allowed-tools: [Read, Bash]
---
Read the selected shot card and its exact implementation. Use page captures,
word-by-word timing and beat sync where the current capability allows it.
"""


_SHOT = b"""---
name: blur-slide
---
The title uses opacity, translateY(64px), blur(18px) and letterSpacing.
The reference implementation is demos/typography/blur-slide/BlurSlide.tsx.
"""


_IMPLEMENTATION = b"""import { useCurrentFrame } from 'remotion';
const words = 'Exact user copy'.split(' ');
const progress = frame / 22;
const style = { opacity: progress, transform: `translateY(${64 - progress}px)` };
"""


_CURRENT = {
    "animation:opacity",
    "animation:transform.position",
    "text:word-parts",
    "capture:web",
}


def _files() -> dict[str, bytes]:
    return {
        "SKILL.md": _ROOT,
        "references/shots/typography/blur-slide.md": _SHOT,
        "demos/typography/blur-slide/BlurSlide.tsx": _IMPLEMENTATION,
        "assets/scripts/sfx-source.py": b"raise RuntimeError('must never execute')\n",
        "gallery/media/poster/blur-slide.png": b"not-a-decoded-image",
    }


def test_shotcraft_sources_become_reviewable_draft_with_evidence_gaps():
    draft = build_skill_draft(_files(), declared_capabilities=_CURRENT)

    assert draft.name == "video-shotcraft"
    assert "Read the selected shot card" in draft.instructions
    by_path = {source.path: source for source in draft.references}
    assert by_path["assets/scripts/sfx-source.py"].role == "script"
    assert by_path["demos/typography/blur-slide/BlurSlide.tsx"].role == "implementation"
    assert by_path["references/shots/typography/blur-slide.md"].role == "reference"
    assert by_path["assets/scripts/sfx-source.py"].text.startswith("raise RuntimeError")

    report = draft.capability_report
    assert report.supported == [
        "animation:opacity",
        "animation:transform.position",
        "capture:web",
        "text:word-parts",
    ]
    gaps = {gap.capability: gap.source_paths for gap in report.gaps}
    assert "runtime:remotion-source" in gaps
    assert "animation:blur" in gaps
    assert "animation:letter-spacing" in gaps
    assert gaps["animation:blur"] == ["references/shots/typography/blur-slide.md"]
    assert report.rejected_files == {
        "gallery/media/poster/blur-slide.png": "invalid_media_content"
    }


def test_scripts_and_allowed_tools_are_dependencies_not_permissions():
    draft = build_skill_draft(_files(), declared_capabilities=_CURRENT)

    dependencies = {
        (item.kind, item.name): item.source_paths
        for item in draft.capability_report.unauthorized_dependencies
    }
    assert dependencies == {
        ("allowed_tool", "Read"): ["SKILL.md"],
        ("allowed_tool", "Bash"): ["SKILL.md"],
        ("script", "assets/scripts/sfx-source.py"): ["assets/scripts/sfx-source.py"],
    }
    assert "script:external" not in {gap.capability for gap in draft.capability_report.gaps}


def test_source_hash_is_order_independent_and_exact_source_sensitive():
    files = _files()
    first = build_skill_draft(files, declared_capabilities=_CURRENT)
    second = build_skill_draft(dict(reversed(list(files.items()))), declared_capabilities=_CURRENT)
    assert first.source_hash == second.source_hash

    changed = {**files, "references/shots/typography/blur-slide.md": _SHOT + b"hold\n"}
    changed_draft = build_skill_draft(changed, declared_capabilities=_CURRENT)
    assert changed_draft.source_hash != first.source_hash

    pinned = build_skill_draft(
        files,
        declared_capabilities=_CURRENT,
        source_uri="https://github.com/Vincentwei1021/video-shotcraft",
        source_revision="1266a3ec4831289c4d893d42dd5102723658039a",
    )
    assert pinned.source_revision == "1266a3ec4831289c4d893d42dd5102723658039a"
    assert pinned.source_hash == first.source_hash


@pytest.mark.parametrize(
    "path",
    ["../SKILL.md", "/SKILL.md", ".git/SKILL.md", "a/./b.md", "a//b.md", "a\\b.md"],
)
def test_unsafe_paths_fail_closed(path: str):
    with pytest.raises(ExternalSkillError, match="path"):
        build_skill_draft({path: _ROOT}, declared_capabilities=_CURRENT)


def test_invalid_text_and_missing_root_fail_closed():
    with pytest.raises(ExternalSkillError, match="UTF-8"):
        build_skill_draft(
            {"SKILL.md": _ROOT, "references/bad.md": b"\xff"},
            declared_capabilities=_CURRENT,
        )
    with pytest.raises(ExternalSkillError, match="root SKILL.md"):
        build_skill_draft(
            {"references/only.md": b"instructions"},
            declared_capabilities=_CURRENT,
        )


def test_frontmatter_cannot_silently_add_unknown_contract_fields():
    root = _ROOT.replace(b"allowed-tools: [Read, Bash]", b"permissions: [admin]")
    with pytest.raises(ExternalSkillError, match="frontmatter keys"):
        build_skill_draft({"SKILL.md": root}, declared_capabilities=_CURRENT)


# --- Skill catalog discovery & bounded reads ---

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
    text_option = get_builtin_skill_option("text-animation", version="1.0.0")
    assert text_option.reference.skill_id == "text-animation"
    assert text_option.reference.version == "1.0.0"
    with pytest.raises(SkillResolutionError, match="unavailable"):
        get_builtin_skill_option("unknown-skill", version="1.0.0")
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


# --- Built-in /text-animation & blueprint summary ---

import hashlib


import io


import json


import subprocess


from pathlib import Path


from types import SimpleNamespace


from uuid import UUID, uuid4


import httpx


import pytest


from httpx import ASGITransport, AsyncClient


from PIL import Image


from app.chat.activity_receipts import skill_saved_receipt


from app.dependencies import get_current_user_required, get_db


from app.editing.catalog import MOTION_BLOCK_CATALOG


from app.editing.styles import CompositionStyle, STYLE_PRESETS


from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks


from app.main import app


from app.models.tables import User


from app.skills import SKILL_REGISTRY


from app.skills.blueprint import (
    BLUEPRINT_CAPABILITY,
    BLUEPRINT_PATH,
    BlueprintAct,
    BlueprintAudioProfile,
    BlueprintOverlay,
    BlueprintSfxCue,
    BlueprintTransition,
    SkillBlueprintV1,
)


from app.skills.external import (
    SkillCapabilityReport,
    SkillDraft,
    SkillPolicy,
    SkillSource,
)


from app.skills.resolution import (
    _external_option,
    get_builtin_skill_option,
    list_available_skills,
)


from app.skills.slot_preview import (
    ALLOWED_FONT_FILENAMES,
    build_slot_preview_video_spec,
    compile_blueprint_slot_preview,
    count_blueprint_slots,
    format_slot_checklist,
)


from app.skills.store import import_external_skill


REPO_ROOT = Path(__file__).resolve().parents[4]


def _make_all_13_blocks_blueprint() -> SkillBlueprintV1:
    acts = [
        BlueprintAct(
            act_id="act_1",
            block_id="statement_hook",
            role="opener",
            target_duration_s=4.0,
            min_duration_s=2.5,
            required_slots=["headline"],
            optional_slots=["subheadline"],
            transition_after=BlueprintTransition(kind="wipe_reveal", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_2",
            block_id="kinetic_title",
            role="title",
            target_duration_s=3.0,
            min_duration_s=2.0,
            required_slots=["headline"],
            optional_slots=["subheadline"],
        ),
        BlueprintAct(
            act_id="act_3",
            block_id="product_showcase",
            role="showcase",
            target_duration_s=6.0,
            min_duration_s=3.5,
            style_defaults={"camera_preset": "tilt_left", "chrome_mode": "browser"},
            required_slots=["image_resource"],
            optional_slots=["url_bar", "callout_steps"],
            callout_windows_s=[(1.0, 2.8), (3.1, 5.2)],
            cursor_click_at_s=2.0,
            overlays=[
                BlueprintOverlay(
                    overlay_id="act_3_overlay_1",
                    rel_start_s=0.6,
                    rel_end_s=3.4,
                    style_defaults={"surface_style": "pill_caption", "position": "bottom_left"},
                )
            ],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_4",
            block_id="device_mockup",
            role="showcase",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"layout": "dual", "reveal_at_s": 1.2},
            required_slots=["image_resource", "mobile_image_resource"],
            transition_after=BlueprintTransition(kind="whip_pan", duration_s=0.4),
        ),
        BlueprintAct(
            act_id="act_5",
            block_id="chat_demo",
            role="demo",
            target_duration_s=6.0,
            min_duration_s=3.5,
            required_slots=["messages", "preview_resource"],
            optional_slots=["work_steps", "result_card"],
            item_reveals_s=[0.4, 1.4, 2.6, 3.6],
            secondary_reveals_s=[1.8, 2.2],
            transition_after=BlueprintTransition(kind="zoom_through", duration_s=0.4),
        ),
        BlueprintAct(
            act_id="act_6",
            block_id="metric_grid",
            role="metrics",
            target_duration_s=5.0,
            min_duration_s=3.0,
            required_slots=["items"],
            metric_reveals_s=[0.5, 1.1, 1.7],
            transition_after=BlueprintTransition(kind="iris_focus", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_7",
            block_id="bento_features",
            role="features",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"highlight_index": 1},
            required_slots=["cards"],
            item_reveals_s=[0.4, 1.0, 1.6, 2.2],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_8",
            block_id="flow_diagram",
            role="workflow",
            target_duration_s=5.0,
            min_duration_s=3.0,
            required_slots=["nodes"],
            item_reveals_s=[0.4, 1.1, 1.8, 2.5],
            transition_after=BlueprintTransition(kind="wipe_reveal", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_9",
            block_id="step_timeline",
            role="roadmap",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"active_step": 2},
            required_slots=["steps"],
            item_reveals_s=[0.5, 1.3, 2.1],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_10",
            block_id="split_compare",
            role="compare",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"dim_left": True},
            required_slots=["left_heading", "left_items", "right_heading", "right_items"],
            item_reveals_s=[0.4, 1.0, 1.6],
            secondary_reveals_s=[0.8, 1.4, 2.0],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_11",
            block_id="data_chart",
            role="data",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"chart_type": "bar", "highlight_index": 3},
            required_slots=["title", "points"],
            item_reveals_s=[0.5, 1.0, 1.5, 2.0],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_12",
            block_id="quote_proof",
            role="proof",
            target_duration_s=4.5,
            min_duration_s=3.0,
            style_defaults={"highlight_at_s": 1.2},
            required_slots=["quote", "author"],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_13",
            block_id="closing_cta",
            role="closing",
            target_duration_s=4.5,
            min_duration_s=3.0,
            required_slots=["brand_name", "tagline"],
        ),
    ]
    sfx_cues = [
        BlueprintSfxCue(cue_id="sfx_1", recipe_id="sub_swell", act_index=0, anchor="act_start", offset_s=0.0, gain_db=-12.0),
        BlueprintSfxCue(cue_id="sfx_2", recipe_id="callout_ping", act_index=2, anchor="act_start", offset_s=1.0, gain_db=-11.0),
        BlueprintSfxCue(cue_id="sfx_3", recipe_id="swoosh_cut", act_index=5, anchor="cut_after", offset_s=-0.15, gain_db=-12.0),
        BlueprintSfxCue(cue_id="sfx_4", recipe_id="stinger", act_index=12, anchor="act_start", offset_s=0.2, gain_db=-11.0),
    ]
    return SkillBlueprintV1(
        canvas={"width": 1920, "height": 1080, "fps_num": 30, "fps_den": 1, "background": "#0A0F16"},
        style=CompositionStyle(preset_id="vox_editorial"),
        acts=acts,
        audio_profile=BlueprintAudioProfile(has_bgm=False),
        sfx_cues=sfx_cues,
    )


def _make_6_act_blueprint() -> SkillBlueprintV1:
    full = _make_all_13_blocks_blueprint()
    picked_ids = {
        "product_showcase",
        "metric_grid",
        "bento_features",
        "data_chart",
        "quote_proof",
        "closing_cta",
    }
    acts = [a for a in full.acts if a.block_id in picked_ids]
    return SkillBlueprintV1(
        canvas=full.canvas,
        style=CompositionStyle(preset_id="vox_editorial"),
        acts=acts,
        audio_profile=BlueprintAudioProfile(),
        sfx_cues=[
            BlueprintSfxCue(cue_id="sfx_open", recipe_id="title_bloom", act_index=0, anchor="act_start", offset_s=0.0),
            BlueprintSfxCue(cue_id="sfx_cut", recipe_id="velvet_pass", act_index=1, anchor="cut_after", offset_s=-0.1),
            BlueprintSfxCue(cue_id="sfx_close", recipe_id="stinger", act_index=5, anchor="act_start", offset_s=0.2),
        ],
    )


def _skill_draft_for_blueprint(name: str, bp: SkillBlueprintV1) -> SkillDraft:
    bp_json = bp.model_dump_json(indent=2)
    bp_digest = hashlib.sha256(bp_json.encode("utf-8")).hexdigest()
    skill_md = f"---\nname: {name}\ndescription: Test blueprint\n---\nUse this template.\n"
    return SkillDraft(
        name=name,
        description="Test slot blueprint template",
        instructions=skill_md,
        references=[
            SkillSource(
                path=BLUEPRINT_PATH,
                role="reference",
                digest=bp_digest,
                text=bp_json,
            )
        ],
        media=[],
        declared_inputs=[],
        capability_report=SkillCapabilityReport(
            supported=[BLUEPRINT_CAPABILITY, "native_motion_graphics"]
        ),
        policy=SkillPolicy(),
        source_uri=f"composition://test-{name}@v1",
        source_revision="v1",
        source_hash=bp_digest,
    )


def test_text_animation_skill_loaded_and_registered():
    assert "text-animation" in SKILL_REGISTRY
    pack = SKILL_REGISTRY["text-animation"]
    assert pack.metadata.get("version") == "1.0.0"
    assert "Beat-Led" in pack.body or "节拍" in pack.body
    assert "generate_image" in pack.body

    opt = get_builtin_skill_option("text-animation")
    assert opt.reference.kind == "builtin"
    assert opt.reference.skill_id == "text-animation"
    assert opt.reference.version == "1.0.0"
    assert opt.capabilities == [
        "native_motion_graphics",
        "beat_led_typography",
        "text_style_presets",
    ]


def test_blueprint_summary_attached_and_fault_tolerant():
    bp = _make_6_act_blueprint()
    bp_json = bp.model_dump_json()
    skill = SimpleNamespace(id=uuid4(), name="saas-promo", description="SaaS promo")
    good_ver = SimpleNamespace(
        id=uuid4(),
        version=2,
        capability_report={"supported": [BLUEPRINT_CAPABILITY]},
        references=[{"path": BLUEPRINT_PATH, "text": bp_json}],
    )
    opt = _external_option(skill, good_ver)
    assert opt.blueprint_summary is not None
    assert opt.blueprint_summary.act_count == 6
    assert opt.blueprint_summary.slot_count == count_blueprint_slots(bp)
    assert opt.blueprint_summary.slot_count > 10
    assert opt.blueprint_summary.style_preset == "vox_editorial"
    assert opt.blueprint_summary.duration_s == pytest.approx(sum(a.target_duration_s for a in bp.acts))

    # Malformed JSON must never crash /chat/skills — gracefully yields None
    bad_ver = SimpleNamespace(
        id=uuid4(),
        version=1,
        capability_report={"supported": [BLUEPRINT_CAPABILITY]},
        references=[{"path": BLUEPRINT_PATH, "text": "{not valid json"}],
    )
    bad_opt = _external_option(skill, bad_ver)
    assert bad_opt.blueprint_summary is None

