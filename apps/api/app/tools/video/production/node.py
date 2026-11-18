"""Version-pinned video assembly on the existing Run/render/billing machinery."""
from sqlalchemy import select

from app.editing.store import get_video_version
from app.models.tables import Output
from app.pipeline.graph import NodeBase, Requirement
from app.pipeline.render_ownership import pend_outputs_for_render
from app.pipeline.step_display import fill_summary, set_spec_field, set_stage, ui_lang_of
from app.tools.video.params import (
    NarrationPolicy,
    PrepareMusicParams,
    PrepareNarrationParams,
    PrepareVisualAssetsParams,
    ProduceVideoParams,
)
from app.tools.video.produce import queue_composition_render
from app.tools.video.production.stages import ProductionStages


class SavedVideoRequirement(Requirement):
    key = "saved_video"

    async def missing(self, db, project):
        receipt = (project.pending_brief or {}).get("video_presentation") or {}
        return not receipt.get("composition_version_id")


class ProduceVideo(NodeBase):
    kind = "produce_video"
    node_type = "video"
    prototype = "generator"
    output_type = "video"
    slot_label = "Video"
    slot_label_zh = "短片"
    task_name = "Prepare video"
    task_name_zh = "准备短片"
    produces_outputs = True
    # A submitted model-image request has an unconfirmed outcome after failure;
    # never give this preparation step a blind TransientNodeError retry budget.
    retries = 0
    requires = (SavedVideoRequirement(),)

    def estimate(self, ctx):
        ref = (ctx.get("spec") or {}).get("version_ref") or {}
        seconds = (ctx.get("video_seconds") or {}).get(str(ref.get("composition_version_id")))
        if seconds is None:
            return None
        units = {"video_seconds": seconds}
        tts_characters = (ctx.get("video_tts_characters") or {}).get(
            str(ref.get("composition_version_id")), 0
        )
        if tts_characters:
            units["tts_chars"] = float(tts_characters)
        images = (ctx.get("video_images") or {}).get(str(ref.get("composition_version_id")), 0)
        if images:
            units["images"] = images
        return {"prompt_tokens": [0, 0], "completion_tokens": [0, 0], "units": units}

    async def run(self, db, run, node, project):
        stages = ProductionStages(
            run_id=run.id,
            step_id=node.id,
            attempt=node.attempt,
            claim_token=node.claim_token,
        )
        async with stages.stage("validate"):
            production = ProduceVideoParams.model_validate({
                "version_ref": (run.context or {}).get("version_ref"),
                "regenerate_media": (run.context or {}).get("regenerate_media", False),
            })
            ref = production.version_ref
            policy = NarrationPolicy.model_validate((run.context or {}).get("narration_policy"))
            if node.spec.get("version_ref") != ref.model_dump(mode="json"):
                raise ValueError("The production step does not match its authorized version")
            if bool(node.spec.get("regenerate_media", False)) != production.regenerate_media:
                raise ValueError("The production step does not match its authorized media-regeneration request")
            if node.spec.get("narration_policy") != policy.model_dump(mode="json"):
                raise ValueError("The production step does not match its authorized narration policy")
            await set_stage(node.id, "preparing_video")
            composition, version = await get_video_version(
                db, owner_id=project.user_id, version_id=ref.composition_version_id
            )
            if composition.id != ref.composition_id or version.content_digest != ref.content_digest:
                raise ValueError("The saved video identity no longer matches the authorized version")
        # A resumed step reuses its own Output; it never deletes earlier deliveries.
        output = await db.scalar(select(Output).where(Output.workflow_step_id == node.id))
        if output is None:
            from app.tools.video.preparation import ensure_font_resources
            async with stages.stage("fonts") as facts:
                font_facts = await ensure_font_resources()
                if isinstance(font_facts, dict):
                    facts.update(font_facts)
            output = await queue_composition_render(
                db,
                project=project,
                composition=composition,
                version=version,
                execution_id=str(run.id),
                regenerate_media=production.regenerate_media,
                narration_policy=policy,
                stages=stages,
            )
            output.workflow_step_id = node.id
            output.payload = {**output.payload, "duration": output.payload["duration_seconds"]}
            if (output.payload or {}).get("narration_policy") != policy.model_dump(mode="json"):
                raise ValueError("The prepared output does not match its authorized narration policy")
        else:
            async with stages.stage("output_resume") as facts:
                facts["reused"] = True
                if (output.payload or {}).get("narration_policy") != policy.model_dump(mode="json"):
                    raise ValueError("The prepared output does not match its authorized narration policy")
        manifest = {
            "version_ref": ref.model_dump(mode="json"),
            "narration_policy": policy.model_dump(mode="json"),
            "generator_media": (output.payload or {}).get("generator_media") or {},
            "speech_media": (output.payload or {}).get("speech_media") or {},
            "render_spec": output.render_spec,
        }
        if production.regenerate_media:
            manifest["regenerate_media"] = True
        if output.render_spec.get("provenance") != ref.model_dump(mode="json"):
            raise ValueError("The prepared output belongs to another video version")
        from app.models.schemas import canonical_json_hash
        digest = canonical_json_hash(manifest)
        output.payload = {**output.payload, "execution_digest": digest}
        run.context = {**run.context, "execution_digest": digest, "execution_manifest": manifest}
        await set_spec_field(node.id, "execution_digest", digest)
        await set_spec_field(node.id, "execution_manifest", manifest)
        async with stages.stage("render_queue"):
            await pend_outputs_for_render(db, run, [output])
        await fill_summary(node.id, self.kind, ui_language=ui_lang_of(run, project),
                           total_seconds=output.payload["duration_seconds"])
        return [output.id]


class PrepareNarration(NodeBase):
    """One authorized speed-1.0 original, with no Composition or video Output."""

    kind = "prepare_narration"
    node_type = "audio"
    prototype = "generator"
    task_name = "Prepare narration"
    task_name_zh = "准备旁白原音"
    produces_outputs = False
    retries = 0

    def estimate(self, ctx):
        from app.tools.video.narration import narration_original_request_key

        spec = ctx.get("spec") or {}
        params = PrepareNarrationParams.model_validate({
            key: spec.get(key) for key in ("text", "voice_id", "language")
        })
        key = narration_original_request_key(
            text=params.text, voice_id=params.voice_id, language=params.language
        )
        characters = (ctx.get("narration_tts_characters") or {}).get(key)
        if characters is None:
            return None
        units = {"tts_chars": float(characters)} if characters else {}
        return {"prompt_tokens": [0, 0], "completion_tokens": [0, 0], "units": units}

    async def run(self, db, run, node, project):
        from app.editing.schemas import (
            Clip,
            CompositionContent,
            SpeechObject,
            TimeRange,
            Timeline,
            Track,
            VersionSettings,
        )
        from app.editing.timing import SOURCE_TIMEBASE
        from app.models.database import AsyncSessionLocal
        from app.tools.video.alignment_store import request_alignment
        from app.tools.video.narration import prepare_speech_media
        from app.tools.video.preparation import snapshot_narration_original

        preparation = (run.context or {}).get("narration_preparation") or {}
        params = PrepareNarrationParams.model_validate(preparation.get("request"))
        policy = NarrationPolicy.model_validate(preparation.get("narration_policy"))
        expected = params.model_dump(mode="json", exclude_none=True)
        if any(node.spec.get(key) != value for key, value in expected.items()):
            raise ValueError("The narration step does not match its authorized request")
        if node.spec.get("narration_policy") != policy.model_dump(mode="json"):
            raise ValueError("The narration step does not match its authorized TTS policy")

        stages = ProductionStages(
            run_id=run.id,
            step_id=node.id,
            attempt=node.attempt,
            claim_token=node.claim_token,
        )
        async with stages.stage("validate"):
            await set_stage(node.id, "preparing_narration")

        speech = SpeechObject(
            kind="speech",
            object_id="obj_prepare_narration",
            text=params.text,
            voice_id=params.voice_id,
            language=params.language,
        )
        timebase = 90000
        # Computation-only adapter for the existing fixed-window core. The
        # generous window keeps the original at 1.0×; max_attempts=1 means an
        # impossible window still fails without a second paid submission.
        content = CompositionContent(
            settings=VersionSettings(width=1, height=1, timebase=timebase),
            timeline=Timeline(tracks=[Track(
                track_id="trk_prepare_narration",
                kind="audio",
                role="dialogue",
                order=0,
                clips=[Clip(
                    clip_id="clp_prepare_narration",
                    range=TimeRange(start=0, end=86400 * timebase),
                    object=speech,
                )],
            )]),
        )
        reuse: list[bool] = []
        async with stages.stage("speech_media") as facts:
            prepared = await prepare_speech_media(
                content,
                user_id=project.user_id,
                execution_id=str(run.id),
                policy=policy,
                on_reuse=reuse.append,
            )
            facts["item_count"] = len(reuse)
            facts["reused_count"] = sum(reuse)
        manifest = prepared[speech.object_id]
        original = manifest["original"]

        async with stages.stage("audio_snapshot"):
            async with AsyncSessionLocal() as freeze_db:
                asset, snapshot = await snapshot_narration_original(
                    freeze_db, project, text=params.text, original=original, scene_id=params.scene_id
                )
                await freeze_db.commit()
                asset_id = asset.id
                snapshot_id = snapshot.id
                snapshot_digest = snapshot.digest
                duration_ticks = snapshot.duration_ticks
        if duration_ticks is None:
            raise ValueError("The fixed narration snapshot has no real duration")

        async with stages.stage("alignment_request"):
            alignment = await request_alignment(
                owner_id=project.user_id,
                audio_snapshot_id=snapshot_id,
                text=params.text,
            )
        result = {
            "asset_id": str(asset_id),
            "audio_snapshot_id": str(snapshot_id),
            "audio_digest": snapshot_digest,
            "duration_ticks": duration_ticks,
            "duration_seconds": duration_ticks / SOURCE_TIMEBASE,
            "alignment_id": alignment["alignment_id"],
            "alignment_status": alignment["status"],
            "analysis_ref": (snapshot.meta or {}).get("analysis_ref"),
            "scene_id": params.scene_id,
            "draft_ref": params.draft_ref.model_dump(mode="json") if params.draft_ref else None,
            "usage_characters": int((manifest.get("usage") or {}).get("tts_chars") or 0),
            "cache_hit": bool(original.get("cache_hit")),
        }
        run.context = {
            **(run.context or {}),
            "narration_preparation": {**preparation, "result": result},
        }
        await set_spec_field(node.id, "narration_preparation", result)
        await fill_summary(
            node.id,
            self.kind,
            ui_language=ui_lang_of(run, project),
            duration_seconds=duration_ticks / SOURCE_TIMEBASE,
        )
        return []


class PrepareVisualAssets(NodeBase):
    """Fixed scene images and their reports; no Composition or video Output."""

    kind = "prepare_visual_assets"
    node_type = "image"
    prototype = "generator"
    task_name = "Prepare scene images"
    task_name_zh = "准备分镜图片"
    produces_outputs = False
    retries = 0

    def estimate(self, ctx):
        images = int(ctx.get("visual_images") or 0)
        units = {"images": images} if images else {}
        return {"prompt_tokens": [0, 0], "completion_tokens": [0, 0], "units": units}

    async def run(self, db, run, node, project):
        from app.tools.video.visual_assets import SceneAssetSpec, prepare_visual_assets

        preparation = (run.context or {}).get("visual_asset_preparation") or {}
        params = PrepareVisualAssetsParams.model_validate(preparation.get("request"))
        expected = params.model_dump(mode="json", exclude_none=True)
        # Old steps predate the explicit review mode. They are generation-only.
        step_spec = {"review_existing": False, **node.spec}
        if any(step_spec.get(key) != value for key, value in expected.items()):
            raise ValueError("The visual asset step does not match its authorized draft and sources")
        pinned = preparation.get("scene_assets")
        specs = (
            [SceneAssetSpec.model_validate(spec) for spec in pinned]
            if pinned is not None else params.scene_assets
        )
        if not specs or (
            [spec.scene_id for spec in specs] != params.scene_ids
            if params.scene_ids is not None else specs != params.scene_assets
        ):
            raise ValueError("The visual asset step has no matching pinned scene specifications")
        attempts = preparation.get("content_attempts") or {}
        stages = ProductionStages(
            run_id=run.id,
            step_id=node.id,
            attempt=node.attempt,
            claim_token=node.claim_token,
        )
        async with stages.stage("validate"):
            await set_stage(node.id, "preparing_visual_assets")
        async with stages.stage("visual_assets") as facts:
            settled = await prepare_visual_assets(
                owner_id=project.user_id,
                project_id=project.id,
                specs=specs,
                review_existing=params.review_existing,
                draft_ref=params.draft_ref,
                execution_id=str(run.id),
                content_attempts={str(key): int(value) for key, value in attempts.items()},
                step_attempt=node.attempt + 1,
            )
            results = settled.assets
            facts["item_count"] = len(results)
            facts["failed_count"] = len(settled.failures)
            facts["reused_count"] = sum(bool(item.get("cache_hit")) for item in results)
        result = {
            "draft_ref": params.draft_ref.model_dump(mode="json"),
            "assets": results,
            "failures": settled.failures,
            "usage": {
                "images": sum(
                    float((item.get("usage") or {}).get("images") or 0)
                    for item in results if not item.get("cache_hit")
                )
            },
        }
        run.context = {
            **(run.context or {}),
            "visual_asset_preparation": {**preparation, "result": result},
        }
        await set_spec_field(node.id, "visual_asset_preparation", result)
        await fill_summary(
            node.id,
            self.kind,
            ui_language=ui_lang_of(run, project),
            total_assets=len(results),
        )
        return []


class PrepareMusic(NodeBase):
    """One deterministic electronic score, with no Composition or video Output."""

    kind = "prepare_music"
    node_type = "audio"
    prototype = "generator"
    task_name = "Prepare electronic score"
    task_name_zh = "准备电子配乐"
    produces_outputs = False
    retries = 0

    def estimate(self, ctx):
        return {"prompt_tokens": [0, 0], "completion_tokens": [0, 0], "units": {}}

    async def run(self, db, run, node, project):
        from app.tools.music.score import ScoreSpec
        from app.tools.video.music_preparation import prepare_programmatic_music

        preparation = (run.context or {}).get("music_preparation") or {}
        params = PrepareMusicParams.model_validate(preparation.get("request"))
        expected = params.model_dump(mode="json", exclude_none=True)
        if any(node.spec.get(key) != value for key, value in expected.items()):
            raise ValueError("The music step does not match its authorized creative request")
        score = ScoreSpec.model_validate(preparation.get("score_spec"))
        if (
            score.score_digest != preparation.get("score_digest")
            or node.spec.get("score_digest") != score.score_digest
            or node.spec.get("score_spec") != score.model_dump(mode="json")
        ):
            raise ValueError("The music step does not match its authorized ScoreSpec")
        stages = ProductionStages(
            run_id=run.id,
            step_id=node.id,
            attempt=node.attempt,
            claim_token=node.claim_token,
        )
        async with stages.stage("validate"):
            await set_stage(node.id, "preparing_music")
        async with stages.stage("music_synthesis") as facts:
            result = await prepare_programmatic_music(
                project=project,
                score=score,
                name=params.name,
                execution_id=str(run.id),
            )
            facts["reused"] = bool(result.get("cache_hit"))
            facts["sample_count"] = (result.get("usage") or {}).get("synth_samples", 0)
        run.context = {
            **(run.context or {}),
            "music_preparation": {**preparation, "result": result},
        }
        await set_spec_field(node.id, "music_preparation", result)
        await fill_summary(
            node.id,
            self.kind,
            ui_language=ui_lang_of(run, project),
            duration_seconds=result["duration_seconds"],
        )
        return []
