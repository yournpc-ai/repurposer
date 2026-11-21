"""Owned video reads and shared delivery semantics.

Output rows remain internal media, execution and recovery facts. Chat delivery
messages own their exact video references; these helpers never create a gallery.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.schemas import OutputResponse
from app.models.tables import Asset, CompositionVersion, Output, SourceSnapshot


def visible_outputs_stmt() -> Select:
    return select(Output).where(
        Output.type == "video",
        Output.archived_at.is_(None),
    )


def chat_delivery_output_ids(messages: list) -> list[UUID]:
    """Flatten only the exact refs persisted on each delivery message."""
    ordered: list[UUID] = []
    seen: set[UUID] = set()
    for message in messages:
        intent = message.intent or {}
        if (
            getattr(message, "role", "assistant") != "assistant"
            or not isinstance(intent.get("output_refs"), list)
        ):
            continue
        for raw_ref in intent["output_refs"]:
            try:
                output_id = UUID(str(raw_ref))
            except (TypeError, ValueError):
                continue
            if output_id not in seen:
                seen.add(output_id)
                ordered.append(output_id)
    return ordered


def is_delivered_output(output: Output) -> bool:
    render_status = getattr(output.render_status, "value", output.render_status)
    provenance = {
        "composition_id": str(output.composition_id or ""),
        "composition_version_id": str(output.composition_version_id or ""),
        "content_digest": (output.payload or {}).get("composition_digest"),
    }
    spec = output.render_spec or {}
    return (
        output.type == "video"
        and all(provenance.values())
        and spec.get("family") == "video"
        and spec.get("provenance") == provenance
        and render_status == "completed"
        and bool((output.files or {}).get("video"))
    )


async def export_file_referenced(db, location, output_id):
    for query in (
        select(Output.id).where((Output.id == output_id) | (Output.files["video"].astext == location)
                                | (Output.files["image"].astext == location)
                                | (Output.publishing["cover_image_url"].astext == location)),
        select(SourceSnapshot.id).where(SourceSnapshot.storage_key == location),
        select(Asset.id).where(Asset.file_url == location),
    ):
        if await db.scalar(query.limit(1)):
            return True
    return False


def output_to_response(
    output: Output,
    *,
    composition_version_number: int | None = None,
) -> OutputResponse:
    return OutputResponse.model_validate(output).model_copy(
        update={"composition_version_number": composition_version_number}
    )


async def composition_version_number(db: AsyncSession, output: Output) -> int | None:
    if output.composition_version_id is None:
        return None
    version = await db.get(CompositionVersion, output.composition_version_id)
    return version.version if version is not None else None


async def list_visible_outputs(db: AsyncSession, project_id: UUID) -> list[Output]:
    result = await db.execute(
        visible_outputs_stmt()
        .where(Output.project_id == project_id)
        .order_by(Output.created_at.desc())
    )
    return list(result.scalars().all())
