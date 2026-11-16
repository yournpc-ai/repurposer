"""Owner-scoped persistence for external Skills and immutable versions."""
from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import canonical_json_hash
from app.models.tables import SkillVersion, UserSkill
from app.providers import storage
from app.skills.external import (
    ExternalSkillError,
    SkillDraft,
    skill_draft_payload,
    validate_skill_media_bytes,
)


class SkillNotFoundError(ValueError):
    """A missing or cross-owner Skill is indistinguishable to the caller."""


async def import_external_skill(
    db: AsyncSession,
    *,
    owner_id: UUID,
    draft: SkillDraft,
) -> tuple[SkillVersion, bool]:
    """Persist a parsed package without renaming or rewriting its sources.

    The caller owns the transaction. Re-importing an identical reviewed draft
    returns the existing version; changed sources or declarations append a
    new version while ``source_hash`` continues to identify the source alone.
    """
    skill = (
        await db.execute(
            select(UserSkill)
            .where(UserSkill.owner_id == owner_id, UserSkill.name == draft.name)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if skill is None:
        skill = UserSkill(
            id=uuid4(),
            owner_id=owner_id,
            name=draft.name,
            description=draft.description,
        )
        db.add(skill)
        await db.flush()

    draft_json = skill_draft_payload(draft)
    # SkillVersion persists this field on UserSkill, so its immutable digest
    # must use the description that will actually be read back with the row.
    draft_json["description"] = skill.description
    version_digest = canonical_json_hash(draft_json)
    existing = (
        await db.execute(
            select(SkillVersion).where(
                SkillVersion.skill_id == skill.id,
                SkillVersion.owner_id == owner_id,
                SkillVersion.version_digest == version_digest,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, True
    # Rows born before version_digest have no mutable backfill. Full-field
    # comparison preserves replay without weakening the immutability trigger.
    legacy_rows = (
        (
            await db.execute(
                select(SkillVersion).where(
                    SkillVersion.skill_id == skill.id,
                    SkillVersion.owner_id == owner_id,
                    SkillVersion.source_hash == draft.source_hash,
                    SkillVersion.version_digest.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for row in legacy_rows:
        persisted = {
            "name": draft.name,
            "description": skill.description,
            "instructions": row.instructions,
            "references": row.references,
            "source_hash": row.source_hash,
            "source_uri": row.source_uri,
            "source_revision": row.source_revision,
            "capability_report": row.capability_report,
            "declared_inputs": row.declared_inputs,
            "policy": row.policy,
        }
        if "media" in draft_json or row.media:
            persisted["media"] = row.media or []
        if persisted == draft_json:
            return row, True

    version = await db.scalar(
        select(func.max(SkillVersion.version)).where(SkillVersion.skill_id == skill.id)
    )
    for item in draft.media:
        if item.data is None or item.storage_key is None:
            raise ExternalSkillError(f"Skill media bytes are missing: {item.path}")
        validate_skill_media_bytes(item, item.data)
        # Digest-derived keys make repeated writes idempotent. A later database
        # rollback may leave an unreferenced object; no mutable row is rewritten.
        await storage.save(item.storage_key, item.data, content_type=item.mime_type)

    row = SkillVersion(
        id=uuid4(),
        skill_id=skill.id,
        owner_id=owner_id,
        version=(version or 0) + 1,
        instructions=draft.instructions,
        references=[item.model_dump(mode="json") for item in draft.references],
        media=[item.model_dump(mode="json") for item in draft.media],
        declared_inputs=[item.model_dump(mode="json") for item in draft.declared_inputs],
        capability_report=draft.capability_report.model_dump(mode="json"),
        policy=draft.policy.model_dump(mode="json"),
        source_uri=draft.source_uri,
        source_revision=draft.source_revision,
        source_hash=draft.source_hash,
        version_digest=version_digest,
    )
    db.add(row)
    await db.flush()
    return row, False


async def get_skill_version(
    db: AsyncSession,
    *,
    owner_id: UUID,
    skill_version_id: UUID,
) -> SkillVersion:
    row = await db.get(SkillVersion, skill_version_id)
    if row is None or row.owner_id != owner_id:
        raise SkillNotFoundError("SkillVersion is unavailable to this user")
    skill = await db.get(UserSkill, row.skill_id)
    if skill is None or skill.owner_id != owner_id:
        raise SkillNotFoundError("SkillVersion is unavailable to this user")
    return row
