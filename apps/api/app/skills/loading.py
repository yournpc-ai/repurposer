"""Load an immutable SkillVersion through the bounded progressive reader.

Only the small SKILL.md entry is injected up front. Shot cards, sequences,
templates, demos and previews are read on demand by the ordinary Chat tool
loop through one owner-pinned PackageReader session. External scripts and
tool declarations never become runtime capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import SkillVersion
from app.skills.external import SkillInputDeclaration, SkillPolicy
from app.skills.package_reader import open_external_skill_package
from app.skills.package_session import SkillPackageSession


@dataclass(frozen=True)
class SkillCreativeContext:
    version: SkillVersion
    declared_inputs: tuple[SkillInputDeclaration, ...]
    policy: SkillPolicy
    package: SkillPackageSession

    @property
    def provenance(self) -> dict:
        return {
            "skill_version_id": str(self.version.id),
            "skill_id": str(self.version.skill_id),
            "source_hash": self.version.source_hash,
            "version_digest": self.version.version_digest,
            "source_uri": self.version.source_uri,
            "source_revision": self.version.source_revision,
            "policy": self.policy.model_dump(mode="json"),
            **self.package.provenance,
        }

    @property
    def presentation(self) -> dict:
        """Policy facts accompanying the normal storyboard/program result."""
        return {
            "mode": self.policy.mode,
            "adaptation_bounds": list(self.policy.adaptation_bounds),
            "skill_version_id": str(self.version.id),
            "source_hash": self.version.source_hash,
        }


async def load_skill_creative_context(
    db: AsyncSession,
    *,
    owner_id: UUID,
    skill_version_id: UUID,
) -> SkillCreativeContext:
    """Resolve owner + immutable version, then read only the root instructions."""
    from app.skills.store import get_skill_version

    version = await get_skill_version(
        db, owner_id=owner_id, skill_version_id=skill_version_id
    )
    reader = await open_external_skill_package(
        db,
        owner_id=owner_id,
        skill_version_id=skill_version_id,
    )
    package = SkillPackageSession(
        reader,
        owner_id=owner_id,
        package_identity=version.id,
    )
    await package.read_initial(["SKILL.md"])
    return SkillCreativeContext(
        version=version,
        declared_inputs=tuple(
            SkillInputDeclaration.model_validate(item)
            for item in (version.declared_inputs or [])
        ),
        policy=SkillPolicy.model_validate(version.policy or {}),
        package=package,
    )
