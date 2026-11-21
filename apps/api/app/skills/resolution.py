"""Resolve the composer's one explicit video-Skill binding.

This is deliberately separate from @mentions and from the tool registry. A
reference is validated against deployed built-ins or the owner's immutable
SkillVersion before the turn; natural-language names bind only on a unique
match. No resolver searches arbitrary packages or grants creative instructions
any additional tool, material, network, file, production or billing rights.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import (
    BuiltInSkillReference,
    ExternalSkillReference,
    SkillOption,
    SkillReference,
)
from app.models.tables import SkillVersion, UserSkill
from app.skills import SKILL_REGISTRY, SkillValidationError, _parse_skill_md
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
    "text-animation": ("native_motion_graphics",),
    "knowledge-explainer": ("narration_alignment", "drawing_v1", "remotion_project"),
}

# Display names live in the web locales; these aliases are the deterministic
# natural-language binding face for the same exact built-in references.
_BUILTIN_SKILL_ALIASES = {
    "promo-video": ("Promotional video", "宣传视频制作"),
    "talking-head-video": ("Talking-head motion video", "口播动效视频制作"),
    "text-animation": ("Text animation video", "文字动画视频制作"),
    "knowledge-explainer": ("Knowledge explainer video", "知识讲解视频制作"),
}


class SkillResolutionError(ValueError):
    """An explicit reference is unknown, foreign, stale or undeclared."""


@dataclass(frozen=True)
class SkillResolution:
    reference: SkillReference | None = None
    ambiguous: tuple[SkillOption, ...] = ()


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


def _external_option(skill: UserSkill, version: SkillVersion) -> SkillOption:
    from app.config import settings

    capabilities = [
        str(item)
        for item in ((version.capability_report or {}).get("supported") or [])
        if isinstance(item, str) and item
        and (settings.component_bake_enabled or item not in {"remotion_project", "runtime:remotion-source"})
    ]
    return SkillOption(
        reference=ExternalSkillReference(kind="external", skill_version_id=version.id),
        skill_id=str(skill.id),
        name=skill.name,
        description=skill.description,
        capabilities=capabilities or ["progressive_skill_package"],
        version_number=version.version,
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


def _normalized_name(value: str) -> str:
    return re.sub(r"[\W_]+", " ", value.casefold(), flags=re.UNICODE).strip()


def _version_mentioned(normalized_message: str, option: SkillOption) -> bool:
    reference = option.reference
    if isinstance(reference, ExternalSkillReference):
        if option.version_number is None:
            return False
        version = str(option.version_number)
    else:
        version = _normalized_name(reference.version)
    return bool(
        re.search(
            rf"(?<![a-z0-9])(?:v(?:ersion)?|版本)\s*{re.escape(version)}(?![a-z0-9])",
            normalized_message,
        )
    )


def _has_version_query(normalized_message: str) -> bool:
    return bool(
        re.search(r"(?<![a-z0-9])(?:v(?:ersion)?|版本)\s*\d", normalized_message)
    )


def resolve_named_skill(
    message: str,
    options: list[SkillOption],
    *,
    prior_options: tuple[SkillOption, ...] = (),
) -> SkillResolution:
    """Bind a unique accessible name/version, including an ambiguity follow-up."""
    normalized_message = _normalized_name(message)
    matches: dict[str, SkillOption] = {}
    for option in options:
        aliases = [option.name]
        if isinstance(option.reference, BuiltInSkillReference):
            aliases.extend((option.skill_id, *_BUILTIN_SKILL_ALIASES.get(option.skill_id, ())))
        for alias in dict.fromkeys(aliases):
            name = _normalized_name(alias)
            if not name:
                continue
            # ASCII word edges prevent substring guesses ("craft" inside
            # "minecraft"); CJK may directly adjoin a Latin or Chinese Skill name.
            if not re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", normalized_message):
                continue
            identity = (
                f"builtin:{option.skill_id}:{option.reference.version}"
                if isinstance(option.reference, BuiltInSkillReference)
                else f"external:{option.reference.skill_version_id}"
            )
            matches.setdefault(identity, option)

    versioned = [
        option for option in matches.values()
        if _version_mentioned(normalized_message, option)
    ]
    if len(versioned) == 1:
        return SkillResolution(reference=versioned[0].reference)
    if versioned or (_has_version_query(normalized_message) and matches):
        return SkillResolution(
            ambiguous=tuple(versioned or matches.values())
        )
    if len(matches) > 1:
        return SkillResolution(ambiguous=tuple(matches.values()))
    if matches:
        return SkillResolution(reference=next(iter(matches.values())).reference)

    # A short "v2" answer may bind only a candidate persisted by the previous
    # ambiguous turn. The caller intersects those refs with current access.
    prior = [
        option for option in prior_options
        if _version_mentioned(normalized_message, option)
    ]
    if len(prior) == 1:
        return SkillResolution(reference=prior[0].reference)
    if _has_version_query(normalized_message) and prior_options:
        return SkillResolution(ambiguous=tuple(prior or prior_options))
    return SkillResolution()


async def resolve_chat_skill(
    db: AsyncSession,
    *,
    owner_id: UUID,
    reference: SkillReference | None,
    message: str,
    prior_references: list[SkillReference] | None = None,
) -> SkillResolution:
    """Validate a chip, or resolve a unique natural-language Skill name."""
    if reference is None:
        options = await list_available_skills(db, owner_id=owner_id)
        prior = tuple(
            option
            for option in options
            if any(option.reference == old for old in prior_references or [])
        )
        return resolve_named_skill(message, options, prior_options=prior)
    if isinstance(reference, BuiltInSkillReference):
        option = get_builtin_skill_option(reference.skill_id, version=reference.version)
        if option.reference != reference:
            raise SkillResolutionError("built-in Skill version is unavailable")
        return SkillResolution(reference=option.reference)
    version = await get_skill_version(
        db, owner_id=owner_id, skill_version_id=reference.skill_version_id
    )
    return SkillResolution(
        reference=ExternalSkillReference(kind="external", skill_version_id=version.id)
    )
