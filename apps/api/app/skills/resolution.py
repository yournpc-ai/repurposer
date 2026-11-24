"""Resolve the composer's one explicit video-Skill binding.

This is deliberately separate from @mentions and from the tool registry. A
reference is validated against deployed built-ins or the owner's immutable
SkillVersion before the turn. No resolver searches arbitrary packages or grants creative instructions
any additional tool, material, network, file, production or billing rights.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    BuiltInSkillReference,
    ExternalSkillReference,
    SkillBlueprintSummary,
    SkillOption,
    SkillReference,
)
from app.models.tables import SkillVersion, UserSkill
from app.skills import SKILL_REGISTRY, SkillValidationError, _parse_skill_md
from app.skills.blueprint import BLUEPRINT_CAPABILITY, load_blueprint_from_skill_version
from app.skills.slot_preview import count_blueprint_slots
from app.skills.store import get_skill_version

# Only packs with a real create_video / current-Editor consumer are selectable video Skills.
# The broader instruction-pack registry also contains writers and other crafts.
_BUILTIN_VIDEO_CAPABILITIES = {
    "promo-video": (
        "website_capture",
        "mixed_real_media",
        "native_motion_graphics",
        "remotion_project",
        "progressive_skill_package",
    ),
    "talking-head-video": ("mixed_real_video", "timed_captions"),
    "text-animation": (
        "native_motion_graphics",
        "beat_led_typography",
        "text_style_presets",
    ),
    "knowledge-explainer": ("narration_alignment", "drawing_v1", "remotion_project"),
}

class SkillResolutionError(ValueError):
    """An explicit reference is unknown, foreign, stale or undeclared."""


def get_builtin_skill_option(skill_id: str, *, version: str | None = None) -> SkillOption:
    from app.config import settings
    from app.skills.package_reader import SkillPackageError, open_builtin_skill_package

    capabilities = _BUILTIN_VIDEO_CAPABILITIES.get(skill_id)
    if capabilities and not settings.component_bake_enabled:
        capabilities = tuple(item for item in capabilities if item != "remotion_project")
    pack = SKILL_REGISTRY.get(skill_id)
    active_version = settings.managed_skill_versions.get(skill_id)
    if capabilities and active_version:
        version = version or active_version
        try:
            manifest = open_builtin_skill_package(skill_id, version).root_manifest
            pack = _parse_skill_md(manifest, require_directory_name=False)
        except (SkillPackageError, SkillValidationError) as exc:
            raise SkillResolutionError(f"Installed Skill {skill_id} is unavailable: {exc}") from exc
    if not capabilities or pack is None:
        raise SkillResolutionError("Skill is unavailable")
    version = version if active_version else str(pack.metadata.get("version") or "")
    if not version:
        raise SkillResolutionError("Skill has no declared design capability")
    return SkillOption(
        reference=BuiltInSkillReference(kind="builtin", skill_id=skill_id, version=version),
        skill_id=skill_id,
        name=pack.name,
        description=pack.description,
        capabilities=list(capabilities),
    )


def _blueprint_summary_for_version(
    version: SkillVersion, capabilities: list[str]
) -> SkillBlueprintSummary | None:
    if BLUEPRINT_CAPABILITY not in capabilities:
        return None
    try:
        bp = load_blueprint_from_skill_version(version)
        return SkillBlueprintSummary(
            act_count=len(bp.acts),
            slot_count=count_blueprint_slots(bp),
            duration_s=round(sum(act.target_duration_s for act in bp.acts), 2),
            style_preset=bp.style.preset_id if bp.style is not None else None,
        )
    except Exception:  # noqa: BLE001 - fault-tolerant picker metadata
        return None


def _external_option(skill: UserSkill, version: SkillVersion) -> SkillOption:
    from app.config import settings

    capabilities = [
        str(item)
        for item in ((version.capability_report or {}).get("supported") or [])
        if isinstance(item, str) and item
        and (settings.component_bake_enabled or item not in {"remotion_project", "runtime:remotion-source"})
    ]
    resolved_caps = capabilities or ["progressive_skill_package"]
    return SkillOption(
        reference=ExternalSkillReference(kind="external", skill_version_id=version.id),
        skill_id=str(skill.id),
        name=skill.name,
        description=skill.description,
        capabilities=resolved_caps,
        version_number=version.version,
        blueprint_summary=_blueprint_summary_for_version(version, resolved_caps),
    )


async def list_available_skills(
    db: AsyncSession, *, owner_id: UUID
) -> list[SkillOption]:
    """Public picker projection; instructions/references never leave the DB."""
    from app.config import settings

    options = [
        get_builtin_skill_option(skill_id)
        for skill_id in sorted(_BUILTIN_VIDEO_CAPABILITIES)
        if skill_id in SKILL_REGISTRY or skill_id in settings.managed_skill_versions
    ]
    rows = (
        await db.execute(
            select(UserSkill, SkillVersion)
            .join(SkillVersion, SkillVersion.skill_id == UserSkill.id)
            .where(UserSkill.owner_id == owner_id, SkillVersion.owner_id == owner_id)
            .order_by(UserSkill.name.asc(), SkillVersion.version.desc())
        )
    ).all()
    options.extend(_external_option(skill, version) for skill, version in rows)
    return options


async def resolve_chat_skill(
    db: AsyncSession,
    *,
    owner_id: UUID,
    reference: SkillReference | None,
) -> SkillReference | None:
    """Only the submitted picker reference can bind a method to this opening."""
    if reference is None:
        return None
    if isinstance(reference, BuiltInSkillReference):
        option = get_builtin_skill_option(reference.skill_id, version=reference.version)
        if option.reference != reference:
            raise SkillResolutionError("built-in Skill version is unavailable")
        return option.reference
    version = await get_skill_version(
        db, owner_id=owner_id, skill_version_id=reference.skill_version_id
    )
    return ExternalSkillReference(kind="external", skill_version_id=version.id)
