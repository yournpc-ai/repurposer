"""Upload finished bytes without reopening their production Run."""
from uuid import UUID, uuid4

from sqlalchemy import select, update

from app.models.database import AsyncSessionLocal
from app.models.schemas import RenderStatus
from app.models.tables import Composition, Output, Project
from app.pipeline.errors import user_line
from app.pipeline.rendering import render_output, resolve_upload_retry
from app.ui_locale import display_language


async def upload_finished_output(project_id: UUID, owner_id: UUID, output_id: UUID | None):
    """Resolve an owned fixed artifact, claim it, then upload through /upload.

    The original Run and failed step are never rewritten. The Output token
    fences concurrent transfers and edits; the render service forbids a
    cache miss from generating replacement bytes.
    """
    token = uuid4()
    async with AsyncSessionLocal() as db:
        project = await db.scalar(select(Project).where(
            Project.id == project_id, Project.user_id == owner_id,
        ))
        if project is None:
            return None, "Project is unavailable."
        target = await resolve_upload_retry(db, project, output_id=output_id)
        if isinstance(target, str):
            return None, target
        output, _, _ = target
        target_id = output.id
        failure_line = user_line("render_upload_failed", display_language(None, project.language))
        provenance = (output.render_spec or {}).get("provenance") or {}
        if provenance.get("composition_id"):
            composition = await db.get(
                Composition, UUID(provenance["composition_id"]), with_for_update=True,
            )
            if (
                composition is None or composition.owner_id != owner_id
                or str(composition.current_version_id) != provenance.get("composition_version_id")
            ):
                return None, (
                    "The Composition version changed; its current version "
                    "has no matching finished upload."
                )

        claimed = await db.execute(update(Output).where(
            Output.id == target_id,
            Output.project_id == project_id,
            Output.render_status == RenderStatus.FAILED,
            Output.archived_at.is_(None),
        ).values(
            render_status=RenderStatus.RENDERING,
            render_claim_token=token,
            render_error=None,
        ))
        if not claimed.rowcount:
            return None, "This upload is already being retried or its output changed."
        await db.commit()

    try:
        await render_output(target_id, upload_only_recovery=True)
    finally:
        # Cancellation must not leave a rendering row for the worker reaper
        # to enqueue as fresh production. Only this transfer's token may settle.
        async with AsyncSessionLocal() as db:
            await db.execute(update(Output).where(
                Output.id == target_id,
                Output.render_claim_token == token,
                Output.render_status == RenderStatus.RENDERING,
            ).values(render_status=RenderStatus.FAILED,
                     render_error=failure_line))
            await db.commit()
    async with AsyncSessionLocal() as db:
        output = await db.get(Output, target_id)
        if output is None or output.render_claim_token != token:
            return None, "The output changed during upload; no replacement was delivered."
        if output.render_status != RenderStatus.COMPLETED:
            return None, output.render_error or "Upload failed. No video was regenerated."
        return target_id, "Upload completed. The existing video is now available; no rendering ran."
