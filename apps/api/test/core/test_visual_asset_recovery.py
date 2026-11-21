import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image

from app.agents.base import jinja_env
from app.chat.video_turn_seats import video_proposal_guard
from app.models.schemas import TaskItem, VideoDraftRef
from app.models.tables import Project, SourceSnapshot
from app.pipeline.orchestrator import TaskSpec, compile_graph
from app.providers.llm.base import LLMSchemaError
from app.tools.video import visual_assets
from app.tools.video.media_analysis import (
    analyze_image_bytes,
    image_content_reviewer,
    image_reviewer_version,
    review_image_content,
    store_content_review,
    store_media_analysis,
)
from app.tools.video.production import pin_visual_asset_preparation, video_quote_facts
from app.tools.video.production.visual_assets import visual_asset_preparation_fact


def image_draft():
    specs = [
        visual_assets.SceneAssetSpec(
            scene_id=scene_id,
            intent="Show the citation mechanism",
            source={"kind": "minimax_image", "prompt": f"Wordless illustration for {scene_id}"},
            on_screen_copy="Prepare the exact caption separately",
            palette=["#F9F9F9", "#DC0100"],
        )
        for scene_id in ("s1", "s2")
    ]
    draft = {"content": {"scenes": [{"scene_id": spec.scene_id} for spec in specs]},
             "design": {"scene_assets": [spec.model_dump(mode="json") for spec in specs]}}
    return draft, specs


class VisualDraftDB:
    def __init__(self, context):
        self.context = context

    async def scalars(self, query):
        entity = query.column_descriptions[0]["entity"]
        rows = [SimpleNamespace(context=self.context)] if entity.__name__ == "Conversation" else []
        return SimpleNamespace(all=lambda: rows)


@pytest.mark.asyncio
async def test_existing_source_refits_legacy_png_before_review_and_cache(database, monkeypatch):
    from test.core.test_compositions import _project, _user

    owner = await _user(database)
    project_id = await _project(database, owner)
    image = Image.new("RGB", (80, 50), "white")
    image.paste("red", (0, 0, 5, 50))
    image.paste("blue", (75, 0, 80, 50))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    original = buffer.getvalue()
    source = SourceSnapshot(
        id=uuid4(), owner_id=owner, origin_project_id=project_id, kind="image",
        digest=hashlib.sha256(original).hexdigest(), storage_key="original.png",
    )
    async with database() as db:
        db.add(source)
        await db.commit()
    spec = visual_assets.SceneAssetSpec(
        scene_id="process", intent="Show the original diagram",
        source={"kind": "existing_image", "snapshot_id": source.id, "snapshot_digest": source.digest},
        on_screen_copy="The editorial title", output={"width": 160, "height": 90},
    )
    assert "visible_evidence" not in spec.model_dump(mode="json")["source"]
    key = visual_assets.request_key(owner, project_id, spec.request_digest())
    stored = {"original.png": original, key: json.dumps({
        "state": "fixed", "scene_id": spec.scene_id, "request_digest": spec.request_digest(),
        "snapshot": {"snapshot_id": str(source.id), "digest": source.digest},
        "media": {"width": 80, "height": 50, "storage_key": source.storage_key, "digest": source.digest},
    }).encode()}

    async def save(key, data, content_type):
        stored[key] = data

    monkeypatch.setattr(visual_assets, "AsyncSessionLocal", database)
    monkeypatch.setattr(visual_assets.storage, "exists", AsyncMock(side_effect=stored.__contains__))
    monkeypatch.setattr(visual_assets.storage, "read", AsyncMock(side_effect=stored.__getitem__))
    monkeypatch.setattr(visual_assets.storage, "save", save)
    reviewer = AsyncMock(return_value={"status": "pass", "summary": "The diagram is visible."})
    kwargs = dict(
        owner_id=owner, project_id=project_id, spec=spec, reviewer=reviewer,
        draft_ref=VideoDraftRef(draft_id="draft", draft_digest="a" * 64),
    )
    result = await visual_assets.prepare_visual_asset(**kwargs, execution_id="first")
    assert not result["cache_hit"] and result["usage"] == {}
    assert result["provenance"]["snapshot_digest"] == source.digest
    assert result["snapshot"]["digest"] != source.digest and stored[source.storage_key] == original
    assert (result["media"]["width"], result["media"]["height"]) == (160, 90)
    assert result["content_review"]["reviewer_version"] == image_reviewer_version("existing_image")
    with Image.open(io.BytesIO(stored[result["media"]["storage_key"]])) as fitted:
        assert fitted.getchannel("A").getbbox() == (8, 0, 152, 90)
        assert fitted.getpixel((8, 0)) == (255, 0, 0, 255)
        assert fitted.getpixel((151, 89)) == (0, 0, 255, 255)
    evidence_args, media = image_content_reviewer.assemble(**reviewer.await_args.kwargs)
    assert media and evidence_args["existing_image"]
    prompt = jinja_env.get_template(image_content_reviewer.prompt).render(**evidence_args)
    assert "页面区段错误" in prompt and "由后续剪辑负责" in prompt
    cached = await visual_assets.prepare_visual_asset(**kwargs, execution_id="again")
    assert cached["cache_hit"] and cached["snapshot"] == result["snapshot"]
    reviewer.assert_awaited_once()


def website_state(snapshot):
    from app.models.schemas import BrandSourceRef, CreativeState
    from test.core.test_website_promo_readiness import profile

    ref = BrandSourceRef(snapshot_id=str(snapshot.id), digest=snapshot.digest)
    return CreativeState(brand_profile=profile().model_copy(update={"source_refs": [ref]}))




@pytest.mark.asyncio
async def test_website_citation_reflows_preserve_full_frozen_or_supplied_dois():
    from app.tools.video.visual_citations import validate_website_scene_citations

    snapshot = SourceSnapshot(id=uuid4(), kind="web", digest="a" * 64, meta={
        "lines": [{"text": "Source paper (https://doi.org/10.1234/paper.2024-77)."}],
        "views": [{"elements": [{"text": "Read paper", "href": "https://doi.org/10.5678/linked"}]}],
    })
    state = website_state(snapshot)

    class SourceDB:
        async def scalars(self, query):
            return [snapshot]

    async def author(markup):
        scene = visual_assets.SceneAssetSpec(
            scene_id="paper", intent="Show how a viewer follows a citation",
            source={"kind": "controlled_svg", "program": f"<svg>{markup}</svg>"},
        )
        await validate_website_scene_citations(
            SourceDB(), owner_id=uuid4(), state=state, specs=[scene],
            user_text="Also show the reference 10.2222/user-supplied.", source_ids=[],
        )

    await author("<text>DOI 10.1234/paper.</text><text>2024-77</text>")
    await author("<text><tspan>10.1234/paper.</tspan><tspan>2024-77</tspan></text>")
    await author("<text>10.2222/user-supplied</text>")
    await author("<text>10.5678/linked</text>")
    await author("<text>Source paper</text><text>Example format: 10.XXXX/article</text>")
    await author('<defs><text>10.9999/unpainted</text></defs>'
                 '<g display="none"><text>10.9999/hidden</text></g>')
    with pytest.raises(visual_assets.VisualAssetError, match="no full match"):
        await author("<text>DOI 10.1234/paper.2024</text>")
    with pytest.raises(visual_assets.VisualAssetError, match="no full match"):
        await author("<text>DOI 10.9999/unverified-example</text>")


@pytest.mark.asyncio
async def test_chat_plan_and_start_resolve_the_same_saved_scene_spec(monkeypatch):
    draft, specs = image_draft()
    reference = VideoDraftRef(draft_id="draft", draft_digest="a" * 64)
    candidate = {
        "candidate_id": reference.draft_id,
        "candidate_digest": reference.draft_digest,
        "target_tool": "design_video",
    }
    db = VisualDraftDB({
        "schema_version": 1,
        "items": [{"candidate": candidate, "executed_arguments": draft}],
    })
    project = SimpleNamespace(id=uuid4(), user_id=uuid4(), pending_brief={})

    from app.tools.video import generated_images

    async def cache_miss(**kwargs):
        return None

    monkeypatch.setattr(visual_assets, "fixed_visual_asset_manifest", cache_miss)
    monkeypatch.setattr(generated_images, "find_fixed_generated_image", lambda *a: cache_miss())
    task = TaskItem(tool="prepare_visual_assets", params={"draft_ref": reference.model_dump(mode="json"), "scene_ids": ["s2"], "review_existing": False})
    assert "directly" in video_proposal_guard([task])
    assert (await video_quote_facts(db, project, [task]))["visual_images"] == 1
    node = compile_graph(TaskSpec(tasks=[task]))[0]
    pinned = (await pin_visual_asset_preparation(db, project, [task]))["visual_asset_preparation"]
    assert pinned["request"] == node.spec
    assert pinned["scene_assets"] == [specs[1].model_dump(mode="json")]
    legacy = task.model_copy(update={"params": {
        "draft_ref": reference.model_dump(mode="json"),
        "scene_assets": pinned["scene_assets"],
    }})
    assert "directly" in video_proposal_guard([legacy])
    assert (await pin_visual_asset_preparation(db, project, [legacy]))[
        "visual_asset_preparation"
    ]["scene_assets"] == pinned["scene_assets"]

    bad_scene = task.model_copy(update={"params": {**task.params, "scene_ids": ["unknown"]}})
    with pytest.raises(ValueError, match="No current SceneAssetSpec"):
        await pin_visual_asset_preparation(db, project, [bad_scene])
    candidate["candidate_digest"] = "b" * 64
    with pytest.raises(ValueError, match="stale or inactive"):
        await pin_visual_asset_preparation(db, project, [task])


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_fails", [False, True])
async def test_review_recovery_reuses_snapshot_and_is_bounded(monkeypatch, retry_fails):
    stored = {}

    async def save(key, data, content_type=None):
        stored[key] = data

    async def read(key):
        return stored[key]

    async def exists(key):
        return key in stored

    monkeypatch.setattr(visual_assets.storage, "save", save)
    monkeypatch.setattr(visual_assets.storage, "read", read)
    monkeypatch.setattr(visual_assets.storage, "exists", exists)
    _, (spec, missing) = image_draft()
    owner_id, project_id, snapshot_id = uuid4(), uuid4(), str(uuid4())
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "white").save(buffer, format="PNG")
    png = buffer.getvalue()
    digest = hashlib.sha256(png).hexdigest()
    analysis = analyze_image_bytes(png, snapshot_id=snapshot_id, source_digest=digest)
    analysis_ref = await store_media_analysis(analysis)

    async def bad_response(**kwargs):
        raise LLMSchemaError("Private provider response")

    unavailable = await review_image_content(
        png, scene_asset=spec, analysis=analysis, analysis_ref=analysis_ref, reviewer=bad_response,
    )
    assert "expected schema" in unavailable.summary
    assert "Private provider response" not in unavailable.summary
    initial_ref = await store_content_review(unavailable)
    manifest = {
        "state": "fixed",
        "scene_id": spec.scene_id,
        "request_digest": spec.request_digest(),
        "media": {"storage_key": "original.png", "digest": digest},
        "snapshot": {"snapshot_id": snapshot_id, "digest": digest},
        "analysis_ref": analysis_ref,
        "content_review_ref": initial_ref,
    }
    original_key = visual_assets.request_key(owner_id, project_id, spec.request_digest())
    original_manifest = json.dumps(manifest).encode()
    await save(original_key, original_manifest)
    await save("original.png", png)
    calls = []

    async def reviewer(**kwargs):
        calls.append(kwargs["image"])
        if retry_fails:
            raise LLMSchemaError("Still unusable")
        return {"status": "pass", "summary": "The fixed image was reviewed"}

    async def never_generate(**kwargs):
        pytest.fail("Review recovery must never execute image generation")

    monkeypatch.setattr(visual_assets, "prepare_visual_asset", never_generate)
    reference = VideoDraftRef(draft_id="draft", draft_digest="a" * 64)
    project = SimpleNamespace(id=project_id, user_id=owner_id)
    draft, _ = image_draft()
    kwargs = {
        "owner_id": owner_id,
        "project_id": project_id,
        "draft_ref": reference,
        "execution_id": "review-run",
        "review_existing": True,
        "reviewer": reviewer,
    }
    mixed = await visual_assets.prepare_visual_assets(specs=[missing, spec], **kwargs)
    assert [(item["scene_id"], item["code"]) for item in mixed.failures] == [
        (missing.scene_id, "execution_error"),
    ]
    reviewed, = mixed.assets
    cached, = (await visual_assets.prepare_visual_assets(specs=[spec], **kwargs)).assets
    assert cached == reviewed
    assert len(calls) == 1
    assert stored[original_key] == original_manifest
    assert cached["snapshot"] == manifest["snapshot"]
    assert cached["review_retry_of"] == initial_ref
    assert cached["content_review"]["status"] == ("unavailable" if retry_fails else "pass")
    snapshot = SimpleNamespace(
        id=snapshot_id,
        owner_id=owner_id, origin_project_id=project_id, kind="image", digest=digest,
        meta={"visual_asset": {
            "scene_id": spec.scene_id, "request_digest": spec.request_digest(),
            "analysis_ref": analysis_ref, "content_review_ref": initial_ref,
        }},
    )

    async def get(model, identity):
        return {(Project, project_id): project, (SourceSnapshot, snapshot_id): snapshot}.get(
            (model, identity if model is Project else str(identity))
        )

    run = SimpleNamespace(project_id=project_id, context={"visual_asset_preparation": {
        "request": {"scene_ids": ["s1"], "review_existing": True},
        "scene_assets": [scene.model_dump(mode="json") for scene in (missing, spec)],
        "result": {"assets": [reviewed], "failures": mixed.failures, "usage": {"images": 0}},
    }})
    step = SimpleNamespace(
        kind="prepare_visual_assets", status="done", output_refs=[], cost={"units": {}},
    )
    fact = await visual_asset_preparation_fact(SimpleNamespace(get=get), run, [step])
    assert fact["assets"][0]["snapshot_id"] == snapshot_id
    assert fact["assets"][0]["content_review_ref"] == reviewed["content_review_ref"]
    assert fact["usage_images"] == 0
    assert fact["failures"] == mixed.failures


@pytest.mark.asyncio
async def test_prefixed_svg_renders_real_shapes_in_chromium():
    from app.tools.research.capture import resolve_chrome_path

    if resolve_chrome_path() is None:
        pytest.skip("configured Chromium is required for the rasterization regression")

    output = visual_assets.VisualOutputConstraints(width=160, height=90)
    svg, _, _ = visual_assets.sanitize_svg_program(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90">'
        '<rect width="160" height="90" fill="#fff"/>'
        '<rect x="60" y="30" width="40" height="30" fill="#dc0000"/>'
        '<text x="30" y="78" font-size="12">Actual SVG</text>'
        '</svg>',
        output,
    )
    assert b"<ns0:svg " in svg
    png, diagnostics = await visual_assets.rasterize_svg(svg, output)
    with Image.open(io.BytesIO(png)) as image:
        assert image.size == (160, 90)
        assert image.convert("RGB").getpixel((80, 45)) == (220, 0, 0)
        assert image.convert("RGB").getpixel((5, 5)) == (255, 255, 255)
    assert diagnostics["native_svg_viewport_verified"] is True
    report = analyze_image_bytes(
        png, snapshot_id=str(uuid4()), svg_text_bounds=diagnostics["text_bounds"],
        caption_safe_area={"x": 0.0, "y": 0.4, "width": 1.0, "height": 0.2},
    )
    geometry = report.media_facts["svg_text_geometry"]
    assert geometry["caption_safe_area"]["bottom"] == pytest.approx(54)
    assert geometry["text"][0]["inside_canvas"] is True
    assert geometry["text"][0]["inside_caption_safe_area"] is False
    with pytest.raises(ValueError, match="native SVG viewport"):
        await visual_assets.rasterize_svg(b"<svg/>", output)


@pytest.mark.asyncio
async def test_outdated_svg_runner_does_not_reuse_fixed_png(monkeypatch):
    svg_spec = visual_assets.SceneAssetSpec(
        scene_id="scene",
        intent="Test renderer cache",
        source={"kind": "controlled_svg", "program": "<svg/>"},
    )
    _, (provider_spec, _) = image_draft()
    owner_id, project_id = uuid4(), uuid4()
    stored = {
        visual_assets.request_key(owner_id, project_id, spec.request_digest()): json.dumps({
            "state": "fixed",
            "snapshot": {"snapshot_id": "prior"},
            "request_digest": spec.request_digest(),
            "scene_id": spec.scene_id,
            "provenance": {"runner_version": "controlled-svg-browser-v1"},
        }).encode()
        for spec in (svg_spec, provider_spec)
    }

    async def exists(key):
        return key in stored

    async def read(key):
        return stored[key]

    monkeypatch.setattr(visual_assets.storage, "exists", exists)
    monkeypatch.setattr(visual_assets.storage, "read", read)
    keys = {"owner_id": owner_id, "project_id": project_id}
    assert await visual_assets.cached_visual_asset(spec=svg_spec, **keys) is None
    assert await visual_assets.fixed_visual_asset_manifest(spec=provider_spec, **keys) is not None


def test_visual_review_legacy_findings_require_actual_evidence():
    from app.tools.video.media_analysis import ContentReviewAnswer

    finding = {
        "requirement": "The diagram shows the cited paper",
        "evidence": "The area at the center of the PNG is empty",
    }
    report = {"status": "fail", "summary": "Missing diagram", "observed_issue": [finding]}
    answer = ContentReviewAnswer.model_validate(report)
    assert answer.findings[0].kind == "observed_issue"
    assert answer.findings[0].evidence == finding["evidence"]
    with pytest.raises(ValueError, match="pixel evidence"):
        ContentReviewAnswer.model_validate({
            **report,
            "observed_issue": [{"requirement": finding["requirement"]}],
        })
    with pytest.raises(ValueError, match="distinct pixel evidence"):
        ContentReviewAnswer.model_validate({
            **report,
            "observed_issue": [{**finding, "evidence": finding["requirement"]}],
        })


@pytest.mark.asyncio
async def test_bad_svg_is_reported_before_quote_and_later_batches_still_settle(monkeypatch):
    specs = [
        visual_assets.SceneAssetSpec(
            scene_id=f"scene-{i}", intent="Evidence",
            source={"kind": "controlled_svg", "program": (
                '<svg><rect rx rx="5"/></svg>' if i == 2 else '<svg><rect rx="5"/></svg>'
            )},
        )
        for i in range(6)
    ]
    with pytest.raises(ValueError, match=r"Scene scene-2: SVG is not well formed"):
        visual_assets.preflight_scene_svgs(specs)
    draft_ref = VideoDraftRef(draft_id="draft", draft_digest="a" * 64)
    project = SimpleNamespace(id=uuid4(), user_id=uuid4())
    async def worker_item(*, spec, **kwargs):
        visual_assets.preflight_scene_svgs([spec])
        return {"scene_id": spec.scene_id}

    monkeypatch.setattr(visual_assets, "prepare_visual_asset", worker_item)
    progress = AsyncMock()
    active_scene = AsyncMock()
    settled = await visual_assets.prepare_visual_assets(
        owner_id=project.user_id, project_id=project.id, specs=specs,
        draft_ref=draft_ref, execution_id=str(uuid4()), on_prepared=progress, on_active_scene=active_scene,
    )
    ticks = [call.args for call in active_scene.await_args_list]
    assert [scene for count, scene in ticks if scene is not None] == [s.scene_id for s in specs]
    assert ticks[-1] == (len(specs), None)
    assert [call.args for call in progress.await_args_list] == [(1,), (2,), (3,), (4,), (5,)]
    assert [a["scene_id"] for a in settled.assets] == [
        "scene-0", "scene-1", "scene-3", "scene-4", "scene-5",
    ]
    failed, = settled.failures
    assert failed["scene_id"] == "scene-2" and failed["code"] == "invalid_svg"


@pytest.mark.asyncio
async def test_submitted_provider_image_reuses_only_verified_fixed_media(monkeypatch):
    from app.tools.video import generated_images

    _, (spec, _) = image_draft()
    owner_id, project_id = uuid4(), uuid4()
    key = visual_assets.request_key(owner_id, project_id, spec.request_digest())
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "red").save(buffer, format="PNG")
    png = buffer.getvalue()
    manifest = {
        "state": "submitted", "request_digest": spec.request_digest(), "scene_id": spec.scene_id,
    }
    stored = {key: json.dumps(manifest).encode(), "verified.png": png}
    fixed = {
        "media": {"storage_key": "verified.png", "digest": hashlib.sha256(png).hexdigest()},
        "request": {}, "provider_request": {}, "program_digest": "a" * 64,
        "execution_id": "earlier-run", "usage": {"images": 1},
    }
    ready = False

    async def exists(storage_key):
        return storage_key in stored

    async def read(storage_key):
        return stored[storage_key]

    async def find(clip):
        return fixed if ready else None

    async def never_submit(*args, **kwargs):
        pytest.fail("Recovery must not submit another provider request")

    monkeypatch.setattr(visual_assets.storage, "read", read)
    monkeypatch.setattr(visual_assets.storage, "exists", exists)
    monkeypatch.setattr(generated_images, "find_fixed_generated_image", find)
    monkeypatch.setattr(generated_images, "ensure_generated_image_clip", never_submit)
    kwargs = {"owner_id": owner_id, "project_id": project_id, "spec": spec}
    with pytest.raises(visual_assets.VisualAssetOutcomeUnknownError, match="not be resubmitted"):
        await visual_assets.fixed_visual_asset_manifest(**kwargs)

    ready = True
    assert await visual_assets.has_fixed_visual_source(**kwargs)
    cached = await visual_assets._recover_submitted_image(spec)
    recovered, _, usage = await visual_assets._minimax_image(
        spec, execution_id="later-run", fixed=cached,
    )
    assert recovered and usage == {}
    assert json.loads(stored[key])["state"] == "submitted"


@pytest.mark.asyncio
async def test_review_uses_scene_role_and_user_words_and_keeps_pixel_identity():

    draft, _ = image_draft()
    draft["content"]["scenes"][0]["intent"] = "Show the link to a source paper."
    draft["content"]["scenes"][1]["intent"] = "Show a researcher communicating science."
    draft["design"]["scene_assets"][1]["intent"] = "Use a vertically mounted phone."
    draft["design"]["review_user_words"] = ["Show the researcher in the second scene."]
    spec = visual_assets.current_scene_assets(draft)[1]
    pixel_identity = spec.request_digest()
    first_version = spec.review_version()
    output = io.BytesIO()
    Image.new("RGB", (32, 18), "white").save(output, format="PNG")
    data = output.getvalue()
    facts = analyze_image_bytes(data, snapshot_id=str(uuid4()))

    reviewer = AsyncMock(return_value={"status": "pass", "summary": "Use case visible", "findings": []})
    async def review():
        return await review_image_content(data, scene_asset=spec, analysis=facts,
                                          analysis_ref={"digest": facts.report_digest}, reviewer=reviewer)
    first = await review()
    projection = json.loads(reviewer.await_args.kwargs["scene_asset_json"])
    assert "vertically" not in str(projection)
    assert projection["requirements"]["narrative"] == draft["content"]["scenes"][1]["intent"]
    assert projection["other_scene_roles"] == {"s1": "Show the link to a source paper."}
    assert first.status == "pass"

    draft["design"]["review_user_words"].append("Use a vertically mounted phone.")
    spec = visual_assets.current_scene_assets(draft)[1]
    assert spec.request_digest() == pixel_identity and spec.review_version() != first_version
    reviewer.return_value = {"status": "fail", "summary": "Orientation mismatch", "findings": [{
        "kind": "observed_issue", "requirement": "user_1", "observed": "Horizontal phone",
        "evidence": "The grip holds the long edge parallel to the desk.",
    }]}
    second = await review()
    assert second.status == "fail"
    assert json.loads(reviewer.await_args.kwargs["scene_asset_json"])["requirements"]["user_1"] == (
        "Use a vertically mounted phone.")
