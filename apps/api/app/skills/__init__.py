"""Skill packs (指令包, N-42) — domain knowledge as data, industry SKILL.md form.

A pack is ``app/skills/<name>/SKILL.md``: YAML frontmatter (Agno's six keys —
``name`` / ``description`` / ``license`` / ``compatibility`` / ``allowed-tools``
/ ``metadata{version, author, tags}``) plus a markdown body of domain
conventions (writing / channel / language craft). Packs parameterize tools;
they never replace them (capability is always code).

Consumption is assembly-time injection ONLY (禁令: no runtime discovery — no
skill tools, the model never decides when a pack loads): an agent declaration
carries ``packs=[...]`` and the assembler weaves the bodies into the prompt
(``agents/contexts.py``). Override semantics are name-wins whole-pack
replacement — a later loader's pack replaces an earlier one's wholesale
(persona-level loaders stack after this platform level in a later batch).

Loading validates eagerly at import (Agno ``SkillValidationError`` spirit):
a malformed pack fails startup, never a generation mid-run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_PACKS_DIR = Path(__file__).parent

_FRONTMATTER_KEYS = {
    "name",
    "description",
    "license",
    "compatibility",
    "allowed-tools",
    "metadata",
}
_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillValidationError(Exception):
    """A SKILL.md failed validation at load (bad frontmatter, name/dir
    mismatch, oversized fields). Raised at import — startup fails loud."""


@dataclass(frozen=True)
class SkillPack:
    """One loaded instruction pack: validated frontmatter + markdown body."""

    name: str
    description: str
    body: str
    license: str | None = None
    compatibility: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _parse_skill_md(path: Path) -> SkillPack:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SkillValidationError(f"{path.name}: missing YAML frontmatter block")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise SkillValidationError(f"{path.name}: unterminated YAML frontmatter")
    try:
        meta = yaml.safe_load(text[4:end])
    except yaml.YAMLError as e:
        raise SkillValidationError(f"{path.name}: frontmatter is not valid YAML: {e}") from e
    if not isinstance(meta, dict):
        raise SkillValidationError(f"{path.name}: frontmatter must be a mapping")
    unknown = set(meta) - _FRONTMATTER_KEYS
    if unknown:
        raise SkillValidationError(
            f"{path.name}: unknown frontmatter keys {sorted(unknown)} "
            f"(allowed: {sorted(_FRONTMATTER_KEYS)})"
        )

    name = meta.get("name")
    if not isinstance(name, str) or not name:
        raise SkillValidationError(f"{path.name}: frontmatter 'name' is required")
    if len(name) > 64 or not _NAME_RE.match(name):
        raise SkillValidationError(
            f"{path.name}: name {name!r} must be lowercase letters/digits with "
            "single hyphens, ≤64 chars, no leading/trailing hyphen"
        )
    if name != path.parent.name:
        raise SkillValidationError(
            f"{path.name}: name {name!r} must equal its directory {path.parent.name!r}"
        )
    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        raise SkillValidationError(f"{path.name}: frontmatter 'description' is required")
    if len(description) > 1024:
        raise SkillValidationError(f"{path.name}: description over 1024 chars")
    compatibility = meta.get("compatibility")
    if compatibility is not None and len(str(compatibility)) > 500:
        raise SkillValidationError(f"{path.name}: compatibility over 500 chars")
    allowed_tools = meta.get("allowed-tools") or []
    if not isinstance(allowed_tools, list) or not all(
        isinstance(t, str) for t in allowed_tools
    ):
        raise SkillValidationError(f"{path.name}: 'allowed-tools' must be a string list")
    metadata = meta.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise SkillValidationError(f"{path.name}: 'metadata' must be a mapping")

    body = text[end + 5 :].lstrip("\n")
    if not body.strip():
        raise SkillValidationError(f"{path.name}: empty body")
    body = body.rstrip("\n") + "\n"
    return SkillPack(
        name=name,
        description=description.strip(),
        body=body,
        license=meta.get("license"),
        compatibility=compatibility,
        allowed_tools=list(allowed_tools),
        metadata=dict(metadata),
    )


def _load_packs() -> dict[str, SkillPack]:
    """Scan ``app/skills/*/SKILL.md`` into the registry. Sorted scan order;
    name-wins on collision (whole-pack replacement, no field-level merge)."""
    registry: dict[str, SkillPack] = {}
    for path in sorted(_PACKS_DIR.glob("*/SKILL.md")):
        pack = _parse_skill_md(path)
        registry[pack.name] = pack  # name-wins: a later loader's pack replaces
    return registry


SKILL_REGISTRY: dict[str, SkillPack] = _load_packs()
