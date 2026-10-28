"""Version-pinned video assembly on the existing Run/render/billing machinery."""
from sqlalchemy import select

from app.editing.store import get_video_version
from app.models.tables import Output
from app.pipeline.graph import NodeBase, Requirement
from app.pipeline.render_ownership import pend_outputs_for_render
from app.pipeline.step_display import fill_summary, set_spec_field, set_stage, ui_lang_of
from app.tools.video.params import NarrationPolicy, ProduceVideoParams
from app.tools.video.produce import queue_composition_render


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
        units = {"film_seconds": seconds}
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
            await ensure_font_resources()
            output = await queue_composition_render(
                db,
                project=project,
                composition=composition,
                version=version,
                execution_id=str(run.id),
                regenerate_media=production.regenerate_media,
                narration_policy=policy,
            )
            output.workflow_step_id = node.id
            output.payload = {**output.payload, "duration": output.payload["duration_seconds"]}
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
        await pend_outputs_for_render(db, run, [output])
        await fill_summary(node.id, self.kind, ui_language=ui_lang_of(run, project),
                           total_seconds=output.payload["duration_seconds"])
        return [output.id]
