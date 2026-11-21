import json
from uuid import uuid4

import pytest

from app.chat.readiness import (
    brief_with_user_constraints,
    compute_source_readiness,
)
from app.models import tables as _tables  # noqa: F401 — register metadata for the disposable DB
from app.models.schemas import (
    BrandProfile,
    BrandSourceRef,
    Brief,
    BriefSlot,
    BriefSlotSource,
    CreativeState,
)

URL = "https://www.legitevi.com/en"


def website_question_arguments():
    return {
        "question": "宣传片制作偏好",
        "items": [
            {"slot": "production_direction", "question": "这支片子打算在哪里播、怎么讲？",
             "options": [{"label": "官网推广 · 用真实案例演示产品", "value": "官网推广 · 用真实案例演示产品"},
                         {"label": "发布会开场 · 用品牌使命串起故事", "value": "发布会开场 · 用品牌使命串起故事"}]},
            {"slot": "target_seconds", "question": "希望片长是多少秒？",
             "options": [{"label": "30 秒", "value": 30}, {"label": "60 秒", "value": 60}]},
            {"slot": "narration_language", "question": "旁白用哪种语言？",
             "options": [{"label": "英文", "value": "en"}, {"label": "中文", "value": "zh"}]},
            {"slot": "subtitle_languages", "question": "字幕需要哪些语言？",
             "options": [{"label": "英文", "value": ["en"]}, {"label": "中文", "value": ["zh"]}]},
            {"slot": "aspect", "question": "画面比例选哪种？", "options": [{"label": "16:9", "value": "16:9"}, {"label": "9:16", "value": "9:16"}]},
        ],
        "default_path": "按推荐设置制作",
    }


def asset(status="pending", *, shots=True):
    return {
        "kind": "asset",
        "type": "web_page",
        "asset_id": "asset-1",
        "status": status,
        "url": URL,
        "text_snapshot_id": "snapshot-1",
        "captured_view_count": 1 if shots else 0,
        "meta": {
            "capture_url": URL,
            "research": {"body": ["Citations should be as universal as hashtags."]}
            if status == "completed"
            else None,
            "shots": [{"key": "sources/hero.png"}] if shots else [],
        },
    }


def snapshot(*, views=True):
    return {
        "snapshot_id": "snapshot-1",
        "kind": "web",
        "digest": "a" * 64,
        "canonical_url": URL,
        "citable_lines": [
            {"line_id": "line_0000", "text": "Citations should be as universal as hashtags."}
        ],
        "views": [
            {
                "view_id": "hero",
                "storage_key": "sources/hero.png",
                "digest": "b" * 64,
                "width": 1440,
                "height": 900,
                "artifact_role": "view",
            }
        ]
        if views
        else [],
    }


def complete_brief():
    values = {
        "purpose": "website",
        "target_seconds": 60,
        "narrative_mode": "mission_tech",
        "narration_language": "en",
        "subtitle_languages": ["en"],
        "aspect": "16:9",
    }
    return Brief(
        **{
            slot: BriefSlot(value=value, source=BriefSlotSource.USER_STATED)
            for slot, value in values.items()
        }
    )


def profile():
    from app.chat.readiness import WEBSITE_BRAND_EXTRACTOR_VERSION

    return BrandProfile(
        extractor_version=WEBSITE_BRAND_EXTRACTOR_VERSION,
        source_refs=[BrandSourceRef(snapshot_id="snapshot-1", digest="a" * 64)],
        content_digest="c" * 64,
    )


def test_new_url_is_pending_until_real_text_and_png_exist():
    readiness = compute_source_readiness(
        user_text=f"给 {URL} 做一只宣传片",
        assets=[asset()],
    )
    assert readiness.task_kind == "website_promo"
    assert readiness.capture_pending
    assert not readiness.capture_ready
    assert not readiness.text_ready
    assert not readiness.required_views_ready


def test_completed_capture_requires_readable_png_not_only_shots():
    readiness = compute_source_readiness(
        user_text=f"给 {URL} 做一只宣传片",
        assets=[asset("completed")],
        snapshots=[snapshot(views=False)],
    )
    assert readiness.capture_ready
    assert readiness.text_ready
    assert not readiness.required_views_ready


def test_full_literal_input_does_not_reask_existing_fields():
    text = (
        f"给 {URL} 做一只 60 秒、16:9、国际科技感与使命叙事、英文配音和英文字幕的品牌官网宣传片。"
    )
    brief = brief_with_user_constraints(text)
    assert brief.purpose.value == "website"
    assert brief.target_seconds.value == 60
    assert brief.narrative_mode.value == "mission_tech"
    assert "website" in brief.production_direction.value
    assert "mission_tech" in brief.production_direction.value
    assert brief.narration_language.value == "en"
    assert brief.subtitle_languages.value == ["en"]
    assert brief.aspect.value == "16:9"

def test_brand_analysis_cannot_choose_the_release_setting_for_the_user():
    from app.models.schemas import AnalyzeBrandArgs

    args = AnalyzeBrandArgs(brief=Brief(
        production_direction=BriefSlot(value="Promote it on the homepage", source=BriefSlotSource.INFERRED),
        purpose=BriefSlot(value="website", source=BriefSlotSource.DEFAULT),
        narrative_mode=BriefSlot(value="Customer story", source=BriefSlotSource.USER_STATED),
        target_seconds=BriefSlot(value=30, source=BriefSlotSource.DEFAULT),
        narration_language=BriefSlot(value="zh", source=BriefSlotSource.INFERRED),
    ))
    assert args.brief.production_direction.value is None
    assert args.brief.target_seconds.value is None and args.brief.narration_language.value is None
    assert args.brief.purpose.value is None
    assert args.brief.narrative_mode.value == "Customer story"


def test_failed_capture_never_becomes_brand_ready():
    readiness = compute_source_readiness(
        user_text=f"给 {URL} 做一只宣传片",
        assets=[asset("failed")],
        creative_state=CreativeState(brand_profile=profile()),
    )
    assert readiness.capture_failed
    assert not readiness.brand_profile_ready


def test_non_website_promo_does_not_inherit_website_gate():
    readiness = compute_source_readiness(
        user_text="把这段采访剪成 60 秒高光",
        creative_state=CreativeState(brief=complete_brief(), brand_profile=profile()),
    )
    assert readiness.task_kind == "generic"


def test_old_rows_tolerate_null_optional_brief_fields():
    brief = Brief.model_validate(
        {
            "topic": {"value": "Existing", "source": "user-stated"},
            "purpose": None,
            "subtitle_languages": None,
        }
    )
    assert brief.topic.value == "Existing"
    assert brief.purpose.value is None
    assert brief.subtitle_languages.value is None


def round_assembly(text, *, assets, snapshots=(), state=None, pending=None, material_pending=False):
    from app.agents.tool_loop import ContextSnapshot
    from app.chat.prompts import assemble_video_round
    from app.chat.editor import EDITOR_TOOLS
    from app.chat.turn_tools import PLAN_TOOLS, _video_material_tools

    resources = tuple(
        [("asset:1", item) for item in assets] + [("snapshot:1", item) for item in snapshots]
    )
    return assemble_video_round(
        {
            "tools": [*PLAN_TOOLS, *_video_material_tools(), *EDITOR_TOOLS],
            "drafts": (),
            "snapshot": ContextSnapshot(
                "evidence", frozenset(key for key, _ in resources), resources=resources
            ),
            "mode": "plan",
            "user_text": text,
            "creative_state": state,
            "pending_question": pending,
            "material_pending": material_pending,
        }
    )


def test_website_creation_requires_real_source_and_leaves_method_to_agent():
    text = f"给 {URL} 做一只宣传片"
    waiting = round_assembly(text, assets=[asset()])
    names = {tool.name for tool in waiting.tools}
    assert {"ask_user", "capture_web", "prepare_video_materials"} <= names
    assert "create_video" not in names
    captured = {**asset("completed"), "text_snapshot_id": "snapshot-1"}
    source = {**snapshot(), "canonical_url": None}
    ready = round_assembly(text, assets=[captured], snapshots=[source], material_pending=True)
    assert json.loads(ready.context)["available_sources"][0]["snapshot_id"] == "snapshot-1"
    assert {"create_video", "ask_user", "analyze_brand"} <= {tool.name for tool in ready.tools}
    assert "required_next_action" not in ready.context and "bound_skill_method" not in ready.context


def test_round_projection_preserves_user_constraints_and_brand_evidence():
    text = (
        f"给 {URL} 做一只 60 秒、16:9、国际科技感与使命叙事、英文配音和英文字幕的品牌官网宣传片。"
    )
    brief = brief_with_user_constraints(text)
    ready = round_assembly(
        text,
        assets=[asset("completed")],
        snapshots=[snapshot()],
        state=CreativeState(brief=brief, brand_profile=profile()),
    )
    facts = json.loads(ready.context)
    assert "create_video" in {tool.name for tool in ready.tools}
    assert facts["creative_state"]["brand_profile"]["extractor_version"] == "website-brand-v1"
    assert "AVAILABLE VIDEO ROUTES" not in ready.system
    assert "promo-video" not in ready.system


def test_open_website_question_stays_pending_across_a_new_round():
    from app.models.tables import Message

    question = Message(id=uuid4(), role="assistant", content="请选择制作要求。",
                       question={"kind": "question", "items": [{"slot": "aspect"}]})
    waiting = round_assembly(
        f"给 {URL} 做一只宣传片", assets=[asset("completed")], snapshots=[snapshot()],
        state=CreativeState(brand_profile=profile()), pending=question,
    )
    assert {tool.name for tool in waiting.tools} == {"answer"}
    assert "working_draft_recovery" not in waiting.context


def test_non_website_round_keeps_existing_path():
    ordinary = round_assembly("Make a video from the attached interview", assets=[])
    assert "create_video" in {tool.name for tool in ordinary.tools}
    assert "design_video" not in {tool.name for tool in ordinary.tools}


@pytest.mark.asyncio
async def test_brand_agent_receives_real_png_and_server_preserves_evidence(monkeypatch):
    from uuid import uuid4

    from app.models.schemas import (
        BrandColor,
        BrandTagline,
        BrandTypography,
        MediaInput,
        MediaInputType,
    )
    from app.models.tables import SourceSnapshot
    from app.providers.llm.base import LLMError
    from app.tools.video.brand import analyze_brand
    from app.tools.video.brand_agent import BrandProfileExtraction, brand_profile_agent

    source = SourceSnapshot(
        id=uuid4(),
        owner_id=uuid4(),
        kind="web",
        digest="a" * 64,
        storage_key="sources/page.json",
        meta={
            "canonical_url": URL,
            "lines": [
                {"line_id": "line_0000", "text": "Citations should be as universal as hashtags."}
            ],
            "views": snapshot()["views"],
        },
    )
    extraction = BrandProfileExtraction(
        positioning="Universal citation infrastructure",
        taglines=[BrandTagline(text="A paraphrase that must not survive", line_ids=["line_0000"])],
        colors=[BrandColor(value="#DC0000", source="css", confidence="confirmed")],
        typography=[BrandTypography(candidate="Inter", source="css", confidence="confirmed")],
    )

    class FakeClient:
        def __init__(self):
            self.messages = None

        async def generate(self, *, messages, response_model, **kwargs):
            self.messages = messages
            return extraction

    fake = FakeClient()
    monkeypatch.setattr(brand_profile_agent, "client", fake)
    monkeypatch.setattr(
        "app.tools.video.brand._matching_web_snapshots", lambda **kwargs: _async_value([source])
    )

    async def no_images_needed(*args, **kwargs):
        raise AssertionError("media loader must be replaced for this fake-provider test")

    monkeypatch.setattr(
        "app.tools.video.design._view_media_inputs",
        lambda *args, **kwargs: _async_value(
            [
                MediaInput(
                    type=MediaInputType.IMAGE,
                    mime="image/png",
                    data_url="data:image/png;base64,iVBORw0KGgo=",
                )
            ]
        ),
    )
    result, facts = await analyze_brand(
        owner_id=source.owner_id,
        project_id=uuid4(),
        user_text=f"给 {URL} 做一只宣传片",
        brief=Brief(),
    )
    assert facts["media_files"] == 1
    assert [message["role"] for message in fake.messages] == ["system", "user"]
    parts = fake.messages[1]["content"]
    assert sum(part.get("type") == "image_url" for part in parts) == 1
    assert "Citations should be as universal as hashtags." in parts[-1]["text"]
    assert result.taglines[0].text == "Citations should be as universal as hashtags."
    assert result.typography[0].candidate == "接近 Inter"
    assert result.typography[0].confidence == "inferred"
    assert result.colors[0].value == "#DC0000"
    assert result.colors[0].confidence == "inferred"
    assert result.creative_direction.provenance == "inferred"
    assert result.source_refs[0].digest == source.digest

    class FailedClient:
        async def generate(self, **kwargs):
            raise LLMError("fake provider failure")

    monkeypatch.setattr(brand_profile_agent, "client", FailedClient())
    try:
        await analyze_brand(
            owner_id=source.owner_id,
            project_id=uuid4(),
            user_text=f"给 {URL} 做一只宣传片",
            brief=Brief(),
        )
    except LLMError:
        pass
    else:
        raise AssertionError("provider failure must not produce a BrandProfile")


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_analyze_brand_seat_commits_state_independently_without_mutating_snapshot(
    database, monkeypatch
):
    from copy import deepcopy
    from uuid import uuid4

    from app.chat.video_turn_seats import analyze_brand_seat
    from app.models.schemas import (
        AnalyzeBrandArgs,
        BrandColor,
        BrandTagline,
        BrandTypography,
        MediaInput,
        MediaInputType,
        ProjectBrief,
    )
    from app.models.tables import Project, SourceSnapshot, User
    from app.tools.video.brand_agent import BrandProfileExtraction, brand_profile_agent

    async with database() as db:
        user = User(id=uuid4(), email=f"{uuid4().hex}@example.com")
        db.add(user)
        await db.flush()
        project = Project(
            id=uuid4(),
            user_id=user.id,
            title="LegitEvi",
            pending_brief=ProjectBrief().model_dump(mode="json"),
        )
        db.add(project)
        await db.flush()
        source = SourceSnapshot(
            id=uuid4(),
            owner_id=user.id,
            origin_project_id=project.id,
            kind="web",
            digest="a" * 64,
            storage_key="sources/page.json",
            meta={
                "canonical_url": URL,
                "lines": [
                    {
                        "line_id": "line_0000",
                        "text": "Citations should be as universal as hashtags.",
                    }
                ],
                "views": snapshot()["views"],
            },
        )
        db.add(source)
        await db.commit()
        original_meta = deepcopy(source.meta)
        project_id, source_id, user_id = project.id, source.id, user.id

    extraction = BrandProfileExtraction(
        positioning="Universal citation infrastructure",
        taglines=[
            BrandTagline(
                text="Citations should be as universal as hashtags.", line_ids=["line_0000"]
            )
        ],
        colors=[BrandColor(value="#DC0000", source="visual", confidence="inferred")],
        typography=[BrandTypography(candidate="Inter", source="visual", confidence="inferred")],
    )

    class FakeClient:
        async def generate(self, *, messages, response_model, **kwargs):
            assert (
                sum(
                    part.get("type") == "image_url"
                    for message in messages
                    for part in (
                        message.get("content") if isinstance(message.get("content"), list) else []
                    )
                )
                == 1
            )
            return extraction

    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    monkeypatch.setattr("app.tools.video.brand.AsyncSessionLocal", database)
    monkeypatch.setattr(brand_profile_agent, "client", FakeClient())
    monkeypatch.setattr(
        "app.tools.video.design._view_media_inputs",
        lambda *args, **kwargs: _async_value(
            [
                MediaInput(
                    type=MediaInputType.IMAGE,
                    mime="image/png",
                    data_url="data:image/png;base64,iVBORw0KGgo=",
                )
            ]
        ),
    )
    text = (
        f"给 {URL} 做一只 60 秒、16:9、国际科技感与使命叙事、英文配音和英文字幕的品牌官网宣传片。"
    )
    async with database() as db:
        project = await db.get(Project, project_id)
        observation = await analyze_brand_seat(
            project=project, args=AnalyzeBrandArgs(), user_text=text
        )
        assert observation.ok
        assert observation.images == ()

    async with database() as db:
        stored = ProjectBrief.model_validate((await db.get(Project, project_id)).pending_brief)
        assert stored.creative_state is not None
        assert stored.creative_state.content_digest
        assert stored.creative_state.brief.target_seconds.value == 60
        assert stored.creative_state.brief.aspect.value == "16:9"
        assert stored.creative_state.brief.narrative_mode.value == "mission_tech"
        assert stored.creative_state.brief.narration_language.value == "en"
        assert stored.creative_state.brief.subtitle_languages.value == ["en"]
        assert stored.creative_state.brand_profile.source_refs[0].snapshot_id == str(source_id)
        assert (
            stored.creative_state.brand_profile.taglines[0].text
            == "Citations should be as universal as hashtags."
        )
        assert stored.creative_state.brand_profile.typography[0].candidate == "接近 Inter"
        unchanged = await db.get(SourceSnapshot, source_id)
        assert unchanged.meta == original_meta
        assert unchanged.digest == "a" * 64
        assert user_id == unchanged.owner_id


def test_unrelated_single_snapshot_and_obsolete_extractor_never_ready():
    unrelated = compute_source_readiness(
        user_text="给 https://new.example/ 做一只宣传片",
        snapshots=[snapshot()],
        creative_state=CreativeState(
            brief=complete_brief(),
            brand_profile=profile(),
        ),
    )
    assert not unrelated.brand_profile_ready

    obsolete = profile().model_copy(update={"extractor_version": "obsolete-v0"})
    stale = compute_source_readiness(
        user_text=f"给 {URL} 做一只宣传片",
        snapshots=[snapshot()],
        creative_state=CreativeState(
            brief=complete_brief(),
            brand_profile=obsolete,
        ),
    )
    assert not stale.brand_profile_ready


def test_only_latest_snapshot_digest_satisfies_brand_readiness():
    older = snapshot()
    older["captured_at"] = "2026-01-01T00:00:00+00:00"
    latest = snapshot()
    latest["captured_at"] = "2026-02-01T00:00:00+00:00"
    latest["digest"] = "b" * 64

    stale_state = CreativeState(
        brief=complete_brief(),
        brand_profile=profile(),
    )
    stale = compute_source_readiness(
        user_text=f"给 {URL} 做一只宣传片",
        snapshots=[older, latest],
        creative_state=stale_state,
    )
    assert not stale.brand_profile_ready

    current_profile = profile().model_copy(update={
        "source_refs": [BrandSourceRef(snapshot_id="snapshot-1", digest="b" * 64)]
    })
    ready = compute_source_readiness(
        user_text=f"给 {URL} 做一只宣传片",
        snapshots=[older, latest],
        creative_state=CreativeState(
            brief=complete_brief(),
            brand_profile=current_profile,
        ),
    )
    assert ready.brand_profile_ready


def test_every_requested_page_needs_text_and_a_readable_view():
    other_url = "https://other.example/"
    missing_view = snapshot()
    missing_view["snapshot_id"] = "snapshot-2"
    missing_view["canonical_url"] = other_url
    missing_view["views"] = []
    readiness = compute_source_readiness(
        user_text=f"给 {URL} 和 {other_url} 做一只宣传片",
        snapshots=[snapshot(), missing_view],
        creative_state=CreativeState(
            brief=complete_brief(),
            brand_profile=profile(),
        ),
    )
    assert readiness.text_ready
    assert not readiness.required_views_ready
    assert not readiness.brand_profile_ready


def test_brand_extraction_normalizes_observed_provider_dialects():
    from app.tools.video.brand_agent import BrandProfileExtraction

    extraction = BrandProfileExtraction.model_validate({
        "positioning_and_claims": [{
            "claim": "Evidence-backed short-form media",
            "kind": "source_fact",
            "basis": {"text": "Building the Global Standard", "line_ids": ["line_0000"]},
        }],
        "typography_candidates": [{
            "candidate": "Inter",
            "weight": "700",
            "confidence": "high",
            "source": "visual",
        }],
        "logo_wordmark_icon_assets": [{"asset": "LegitEvi wordmark", "view_ids": ["view-0"]}],
        "taglines": ["Citations should be as universal as hashtags."],
        "colors": [{
            "hex": "#DC0000",
            "name": "brand red",
            "confidence": "high",
            "source": "visual",
        }],
        "creative_direction": "Restrained minimal technology",
        "unknowns": [{"item": "Exact font is not confirmed"}],
        "conflicts": [{"issue": "CSS is unavailable"}],
    })
    assert extraction.positioning == "Evidence-backed short-form media"
    assert extraction.claims[0].kind == "fact"
    assert extraction.claims[0].line_ids == ["line_0000"]
    assert extraction.typography[0].candidate == "Inter"
    assert extraction.typography[0].confidence == "inferred"
    assert extraction.brand_assets[0].kind == "wordmark"
    assert extraction.taglines[0].text == "Citations should be as universal as hashtags."
    assert extraction.colors[0].value == "#DC0000"
    assert extraction.colors[0].confidence == "inferred"
    assert extraction.creative_direction.summary == "Restrained minimal technology"
    assert extraction.creative_direction.provenance == "inferred"
    assert extraction.unknowns == ["Exact font is not confirmed"]
    assert extraction.conflicts == ["CSS is unavailable"]


def test_visual_color_snaps_to_measured_dominant_brand_red():
    import io
    from uuid import uuid4

    from PIL import Image

    from app.models.schemas import MediaInput, MediaInputType
    from app.models.tables import SourceSnapshot
    from app.tools.video.brand import (
        _dominant_color_evidence,
        build_brand_profile,
    )
    from app.tools.video.brand_agent import BrandProfileExtraction

    buffer = io.BytesIO()
    Image.new("RGB", (100, 100), "#DC0000").save(buffer, format="PNG")
    media = MediaInput(
        type=MediaInputType.IMAGE,
        mime="image/png",
        data_url="data:image/png;base64," + __import__("base64").b64encode(
            buffer.getvalue()
        ).decode("ascii"),
    )
    palette = _dominant_color_evidence([media])
    assert palette[0]["value"] == "#DC0000"
    assert palette[0]["pixel_share"] == 1.0

    source = SourceSnapshot(
        id=uuid4(),
        owner_id=uuid4(),
        kind="web",
        digest="a" * 64,
        storage_key="sources/page.json",
        meta={
            "canonical_url": URL,
            "lines": [{"line_id": "line_0000", "text": "Evidence"}],
            "views": snapshot()["views"],
        },
    )
    ref = BrandSourceRef(snapshot_id="snapshot-1", digest=source.digest)
    extraction = BrandProfileExtraction(
        colors=[{
            "value": "#E32636",
            "role": "primary",
            "source": "visual",
            "confidence": "inferred",
        }]
    )
    result = build_brand_profile(
        extraction,
        snapshots=[source],
        source_refs=[ref],
        color_evidence=palette,
    )
    assert result.colors[0].value == "#DC0000"
    assert result.colors[0].source == "visual"
    assert result.colors[0].confidence == "inferred"

    without_model_color = build_brand_profile(
        BrandProfileExtraction(),
        snapshots=[source],
        source_refs=[ref],
        color_evidence=palette,
    )
    assert without_model_color.colors[0].value == "#DC0000"
    assert without_model_color.colors[0].role == "accent"
    assert without_model_color.colors[0].confidence == "inferred"


def test_saturated_accent_survives_antialiasing_and_frequency_cap():
    import io

    from PIL import Image

    from app.models.schemas import MediaInput, MediaInputType
    from app.tools.video.brand import _dominant_color_evidence, _measured_color

    image = Image.new("RGB", (100, 100), "#FFFFFF")
    for y in range(10):
        for x in range(10):
            image.putpixel((x, y), (220, 0, 0))
    for y in range(10, 15):
        for x in range(10):
            image.putpixel((x, y), (222, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    media = MediaInput(
        type=MediaInputType.IMAGE,
        mime="image/png",
        data_url="data:image/png;base64," + __import__("base64").b64encode(
            buffer.getvalue()
        ).decode("ascii"),
    )
    palette = _dominant_color_evidence([media])
    assert any(item["value"] == "#DC0000" for item in palette)
    assert _measured_color("#E32636", palette) == "#DC0000"


@pytest.mark.asyncio
async def test_analyze_brand_seat_recovers_source_and_brief_from_pending_prompt(
    database, monkeypatch
):
    from app.chat.video_turn_seats import analyze_brand_seat
    from app.models.schemas import AnalyzeBrandArgs, ProjectBrief
    from app.models.tables import Project, User

    prompt = (
        f"给 {URL} 做一只 60 秒、16:9、国际科技感与使命叙事、英文配音和英文字幕的品牌官网宣传片。"
    )
    async with database() as db:
        user = User(id=uuid4(), email=f"{uuid4().hex}@example.com")
        db.add(user)
        await db.flush()
        project = Project(
            id=uuid4(),
            user_id=user.id,
            title="Resume brand analysis",
            pending_brief=ProjectBrief(prompt=prompt).model_dump(mode="json"),
        )
        db.add(project)
        await db.commit()
        project_id = project.id

    captured = {}
    result_profile = profile()

    async def fake_analyze_brand(**kwargs):
        captured.update(kwargs)
        return result_profile, {"brand_profile": result_profile.model_dump(mode="json")}

    monkeypatch.setattr("app.tools.video.brand.analyze_brand", fake_analyze_brand)
    monkeypatch.setattr("app.models.database.AsyncSessionLocal", database)
    async with database() as db:
        project = await db.get(Project, project_id)
        observation = await analyze_brand_seat(
            project=project,
            args=AnalyzeBrandArgs(),
            user_text="继续",
        )
        assert observation.ok

    assert captured["user_text"] == prompt
    assert captured["brief"].target_seconds.value == 60
    assert captured["brief"].aspect.value == "16:9"
    assert captured["brief"].narrative_mode.value == "mission_tech"
    assert captured["brief"].narration_language.value == "en"
    assert captured["brief"].subtitle_languages.value == ["en"]
    async with database() as db:
        stored = ProjectBrief.model_validate((await db.get(Project, project_id)).pending_brief)
        assert stored.creative_state is not None
        assert stored.creative_state.brief.target_seconds.value == 60
        assert stored.creative_state.brand_profile == result_profile


def test_css_color_facts_do_not_confirm_font_without_font_family():
    from app.models.tables import SourceSnapshot
    from app.tools.video.brand import build_brand_profile
    from app.tools.video.brand_agent import BrandProfileExtraction

    source = SourceSnapshot(
        id=uuid4(),
        owner_id=uuid4(),
        kind="web",
        digest="a" * 64,
        storage_key="sources/page.json",
        meta={
            "css_facts": {"colors": ["#DC0000"]},
            "lines": [{"line_id": "line_0000", "text": "Evidence"}],
        },
    )
    extraction = BrandProfileExtraction.model_validate({
        "typography": [{"candidate": "Inter", "source": "css", "confidence": "confirmed"}]
    })
    ref = BrandSourceRef(snapshot_id=str(source.id), digest=source.digest)
    result = build_brand_profile(extraction, snapshots=[source], source_refs=[ref])
    assert result.typography[0].candidate == "接近 Inter"
    assert result.typography[0].source == "visual"
    assert result.typography[0].confidence == "inferred"

    source.meta = {"css_facts": {"font_family": "Inter"}}
    confirmed = build_brand_profile(extraction, snapshots=[source], source_refs=[ref])
    assert confirmed.typography[0].candidate == "Inter"
    assert confirmed.typography[0].source == "css"
    assert confirmed.typography[0].confidence == "confirmed"


def test_website_round_excludes_unrelated_project_resources():
    unrelated = asset()
    unrelated["url"] = "https://unrelated.example/"
    unrelated["meta"]["capture_url"] = unrelated["url"]
    assembly = round_assembly(
        f"给 {URL} 做一只宣传片",
        assets=[asset(), unrelated],
    )
    assert "unrelated.example" not in assembly.context
    assert not assembly.include_project_context
