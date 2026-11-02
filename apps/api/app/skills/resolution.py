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

from app.editing.templates import load_template
from app.models.schemas import (
    BuiltInSkillReference,
    ExternalSkillReference,
    SkillOption,
    SkillReference,
)
from app.models.tables import SkillVersion, UserSkill
from app.skills import SKILL_REGISTRY
from app.skills.store import get_skill_version

# Only packs with a real design_video consumer are selectable video Skills.
# The broader instruction-pack registry also contains writers and other crafts.
_BUILTIN_VIDEO_CAPABILITIES = {
    "launch-film": ("website_capture", "launch_film_template"),
}


class SkillResolutionError(ValueError):
    """An explicit reference is unknown, foreign, stale or undeclared."""


@dataclass(frozen=True)
class SkillResolution:
    reference: SkillReference | None = None
    ambiguous: tuple[SkillOption, ...] = ()


def get_builtin_skill_option(skill_id: str) -> SkillOption:
    capabilities = _BUILTIN_VIDEO_CAPABILITIES.get(skill_id)
    pack = SKILL_REGISTRY.get(skill_id)
    if not capabilities or pack is None:
        raise SkillResolutionError("Skill is unavailable")
    version = str(pack.metadata.get("version") or "")
    template = load_template(skill_id)
    if not version or template.template_id != skill_id:
        raise SkillResolutionError("Skill has no declared design capability")
    return SkillOption(
        reference=BuiltInSkillReference(kind="builtin", skill_id=skill_id, version=version),
        skill_id=skill_id,
        name=pack.name,
        description=pack.description,
        capabilities=list(capabilities),
    )


def _external_option(skill: UserSkill, version: SkillVersion) -> SkillOption | None:
    capabilities = [
        str(item)
        for item in ((version.capability_report or {}).get("supported") or [])
        if isinstance(item, str) and item
    ]
    if not capabilities:
        return None
    return SkillOption(
        reference=ExternalSkillReference(kind="external", skill_version_id=version.id),
        skill_id=str(skill.id),
        name=skill.name,
        description=skill.description,
        capabilities=capabilities,
        version_number=version.version,
    )


async def list_available_skills(
    db: AsyncSession, *, owner_id: UUID
) -> list[SkillOption]:
    """Public picker projection; instructions/references never leave the DB."""
    options = [get_builtin_skill_option(skill_id) for skill_id in sorted(_BUILTIN_VIDEO_CAPABILITIES)]
    rows = (
        await db.execute(
            select(UserSkill, SkillVersion)
            .join(SkillVersion, SkillVersion.skill_id == UserSkill.id)
            .where(UserSkill.owner_id == owner_id, SkillVersion.owner_id == owner_id)
            .order_by(UserSkill.name.asc(), SkillVersion.version.desc())
        )
    ).all()
    options.extend(
        option
        for skill, version in rows
        if (option := _external_option(skill, version)) is not None
    )
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
        name = _normalized_name(option.name)
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
        option = get_builtin_skill_option(reference.skill_id)
        if option.reference != reference:
            raise SkillResolutionError("built-in Skill version is unavailable")
        return SkillResolution(reference=option.reference)
    version = await get_skill_version(
        db, owner_id=owner_id, skill_version_id=reference.skill_version_id
    )
    skill = await db.get(UserSkill, version.skill_id)
    if (
        skill is None
        or skill.owner_id != owner_id
        or _external_option(skill, version) is None
    ):
        raise SkillResolutionError("Skill has no declared design capability")
    return SkillResolution(reference=reference)
