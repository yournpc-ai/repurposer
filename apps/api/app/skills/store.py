"""Owner-scoped persistence for external Skills and immutable versions."""
from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import canonical_json_hash
from app.models.tables import SkillVersion, UserSkill
from app.skills.external import SkillDraft


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

    draft_json = draft.model_dump(mode="json")
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
        if persisted == draft_json:
            return row, True

    version = await db.scalar(
        select(func.max(SkillVersion.version)).where(SkillVersion.skill_id == skill.id)
    )
    row = SkillVersion(
        id=uuid4(),
        skill_id=skill.id,
        owner_id=owner_id,
        version=(version or 0) + 1,
        instructions=draft.instructions,
        references=[item.model_dump(mode="json") for item in draft.references],
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
