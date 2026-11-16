"""Read built-in packages and immutable SkillVersions through one bounded interface.

The reader exposes package evidence only: selected text, preview media identities
or bytes, and a static shot-library projection. It never imports package modules,
executes source, resolves tools, registers shots, or mutates a package.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import canonical_json_hash
from app.models.tables import SkillVersion, UserSkill
from app.providers import storage
from app.skills.external import (
    _MAX_FILE_BYTES,
    _MAX_FRONTMATTER_BYTES,
    _MAX_MEDIA_BYTES,
    _MAX_MEDIA_FILE_BYTES,
    _MAX_MEDIA_FILES,
    _MAX_REFERENCES,
    _MAX_TOTAL_BYTES,
    _MEDIA_TYPES,
    _TEXT_SUFFIXES,
    ExternalSkillError,
    SkillMedia,
    SkillSource,
    _role,
    _safe_path,
    validate_skill_media_bytes,
    validate_skill_media_identity,
)
from app.skills.store import get_skill_version

_PACKS_ROOT = Path(__file__).parent.resolve()
_LIBRARY_PATH = "gallery/api/library.json"
_LEGACY_TEMPLATE_PATH = "video-template.json"
_CATEGORIES = {
    "opening",
    "camera",
    "transition",
    "typography",
    "ui-entrance",
    "interaction",
    "data",
    "effects",
    "rhythm",
    "outro",
}
_MAX_SHOTS = 512
_MAX_SEQUENCES = 64
_MAX_INDEX_VARIANTS = 32
_MAX_INDEX_PREVIEWS = 8
_FORBIDDEN_INDEX_KEYS = {
    "allowed_tools",
    "callback",
    "callbacks",
    "command",
    "commands",
    "dynamic_import",
    "entry_point",
    "entrypoint",
    "exec",
    "executable",
    "execute",
    "handler",
    "handlers",
    "import",
    "imports",
    "module",
    "modules",
    "permission",
    "permissions",
    "script",
    "scripts",
    "shell",
    "tool",
    "tool_permissions",
    "tools",
}

PackageResourceKind = Literal["shots", "sequences", "demos", "media", "template"]


class SkillPackageError(ValueError):
    """A package path, identity, resource or static-index validation failure."""


class SkillPackageResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    digest: str = Field(min_length=64, max_length=64)
    byte_size: int = Field(ge=0)
    mime_type: str | None = None
    storage_key: str | None = None


class SkillLibraryPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    digest: str = Field(min_length=64, max_length=64)
    mime_type: str
    byte_size: int = Field(gt=0)


class SkillLibraryVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    metadata: dict[str, Any] = {}


class SkillLibraryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    path: str
    category: str
    name: str = Field(min_length=1, max_length=256)
    energy: str | int | float | None = None
    use: str | None = Field(default=None, max_length=2048)
    metadata: dict[str, Any] = {}
    variants: list[SkillLibraryVariant] = []
    previews: list[SkillLibraryPreview] = []
    digest: str = Field(min_length=64, max_length=64)


class SkillLibraryIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["gallery/api/library.json", "references/shots"]
    entries: list[SkillLibraryEntry]


def _relative_path(value: str) -> PurePosixPath:
    try:
        return _safe_path(value)
    except ExternalSkillError as exc:
        raise SkillPackageError(str(exc)) from exc


def _resource(source: SkillSource | SkillMedia) -> SkillPackageResource:
    if isinstance(source, SkillSource):
        return SkillPackageResource(
            path=source.path,
            digest=source.digest,
            byte_size=len(source.text.encode("utf-8")),
        )
    return SkillPackageResource(
        path=source.path,
        digest=source.digest,
        byte_size=source.byte_size,
        mime_type=source.mime_type,
        storage_key=source.storage_key,
    )


def _readable_text_path(path: PurePosixPath) -> bool:
    value = path.as_posix()
    return (
        value in {"SKILL.md", _LIBRARY_PATH, _LEGACY_TEMPLATE_PATH}
        or value.startswith(("references/", "demos/", "template/", "assets/lib/"))
        or value == "assets/audio/ATTRIBUTION.md"
    ) and path.suffix.lower() in _TEXT_SUFFIXES


def _shot_category(path: str) -> str:
    parts = _relative_path(path).parts
    if (
        len(parts) != 4
        or parts[:2] != ("references", "shots")
        or parts[2] not in _CATEGORIES
        or PurePosixPath(path).suffix.lower() != ".md"
    ):
        raise SkillPackageError(f"invalid shot-card path or category: {path}")
    return parts[2]


def _validate_sequence_path(path: str) -> None:
    parts = _relative_path(path).parts
    if (
        len(parts) != 3
        or parts[:2] != ("references", "sequences")
        or PurePosixPath(path).suffix.lower() != ".md"
    ):
        raise SkillPackageError(f"invalid sequence path: {path}")


def _static_value(value: Any, *, depth: int = 0) -> Any:
    """Retain declared JSON-like metadata while rejecting executable shapes."""
    if depth > 4:
        raise SkillPackageError("Skill library metadata is too deeply nested")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        if len(value) > 4096:
            raise SkillPackageError("Skill library metadata string is too long")
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SkillPackageError("Skill library metadata numbers must be finite")
        return value
    if isinstance(value, list):
        if len(value) > 64:
            raise SkillPackageError("Skill library metadata list is too long")
        return [_static_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 64:
            raise SkillPackageError("Skill library metadata mapping is too large")
        projected: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 128:
                raise SkillPackageError("Skill library metadata keys must be bounded strings")
            normalized = key.strip().casefold().replace("-", "_").replace(" ", "_")
            if normalized in _FORBIDDEN_INDEX_KEYS:
                raise SkillPackageError(f"executable Skill library metadata is forbidden: {key}")
            projected[key] = _static_value(item, depth=depth + 1)
        return projected
    raise SkillPackageError(f"unsupported Skill library metadata value: {type(value).__name__}")


def _variants(value: Any) -> list[SkillLibraryVariant]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > _MAX_INDEX_VARIANTS:
        raise SkillPackageError("Skill library variants must be a bounded list")
    result: list[SkillLibraryVariant] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, str):
            item = {"id": item, "name": item}
        if not isinstance(item, dict):
            raise SkillPackageError("Skill library variants must be strings or mappings")
        values = dict(item)
        variant_id = values.pop("id", None)
        name = values.pop("name", None)
        if variant_id is None:
            variant_id = name
        if name is None:
            name = variant_id
        if not isinstance(variant_id, str) or not variant_id.strip() or len(variant_id.strip()) > 128:
            raise SkillPackageError("Skill library variant id must be a bounded non-empty string")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 256:
            raise SkillPackageError("Skill library variant name must be a non-empty string")
        variant_id = variant_id.strip()
        if variant_id in seen:
            raise SkillPackageError(f"duplicate Skill library variant id: {variant_id}")
        seen.add(variant_id)
        metadata = _static_value(values)
        result.append(
            SkillLibraryVariant(
                id=variant_id,
                name=name.strip(),
                metadata=metadata,
            )
        )
    return result


class SkillPackageReader:
    """One immutable package source; use the two entry functions below."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        version: SkillVersion | None = None,
        skill: UserSkill | None = None,
    ) -> None:
        self._root = root
        self._version = version
        self._references: dict[str, SkillSource] = {}
        self._media: dict[str, SkillMedia] = {}
        if version is not None:
            self._load_external(version, skill)

    @property
    def root_manifest(self) -> Path:
        path = self._builtin_path("SKILL.md")
        assert path is not None
        return path

    def _load_external(self, version: SkillVersion, skill: UserSkill | None) -> None:
        if skill is None or skill.id != version.skill_id or skill.owner_id != version.owner_id:
            raise SkillPackageError("SkillVersion owner identity is inconsistent")
        total_text = len(version.instructions.encode("utf-8"))
        if not version.instructions.strip():
            raise SkillPackageError("Skill instructions must not be empty")
        if total_text > _MAX_FILE_BYTES:
            raise SkillPackageError("Skill instructions exceed their text size limit")
        try:
            for item in version.references or []:
                source = SkillSource.model_validate(item)
                path = _relative_path(source.path)
                if source.path in self._references:
                    raise SkillPackageError(f"duplicate Skill source path: {source.path}")
                if source.role != _role(path):
                    raise SkillPackageError(f"Skill source role mismatch: {source.path}")
                size = len(source.text.encode("utf-8"))
                if size > _MAX_FILE_BYTES:
                    raise SkillPackageError(f"Skill source exceeds its size limit: {source.path}")
                total_text += size
                if hashlib.sha256(source.text.encode("utf-8")).hexdigest() != source.digest:
                    raise SkillPackageError(f"Skill source digest mismatch: {source.path}")
                self._references[source.path] = source
            if len(self._references) > _MAX_REFERENCES or total_text > _MAX_TOTAL_BYTES:
                raise SkillPackageError("Skill package exceeds its text count or size limit")
            for item in version.media or []:
                media = SkillMedia.model_validate(item)
                validate_skill_media_identity(media)
                expected_key = media.storage_key
                if expected_key is None:
                    raise SkillPackageError(f"Skill media storage key is missing: {media.path}")
                if media.path in self._media:
                    raise SkillPackageError(f"duplicate Skill media path: {media.path}")
                self._media[media.path] = media
            if len(self._media) > _MAX_MEDIA_FILES:
                raise SkillPackageError("Skill package exceeds its media count limit")
            if sum(item.byte_size for item in self._media.values()) > _MAX_MEDIA_BYTES:
                raise SkillPackageError("Skill package exceeds its media size limit")
        except (ValidationError, ExternalSkillError) as exc:
            raise SkillPackageError(f"invalid persisted Skill package: {exc}") from exc

        # version_digest covers the root instructions and every persisted field,
        # including each media digest. NULL media identifies rows born before
        # this column: retain their historical read path and per-source checks,
        # because older drafts could pin a description not stored on the row.
        # New imports always persist [] or a media list and get full verification.
        if version.version_digest is not None and version.media is not None:
            payload = {
                "name": skill.name,
                "description": skill.description,
                "instructions": version.instructions,
                "references": version.references or [],
                "source_hash": version.source_hash,
                "source_uri": version.source_uri,
                "source_revision": version.source_revision,
                "capability_report": version.capability_report,
                "declared_inputs": version.declared_inputs or [],
                "policy": version.policy or {},
            }
            if version.media:
                payload["media"] = version.media
            if canonical_json_hash(payload) != version.version_digest:
                raise SkillPackageError("SkillVersion digest mismatch")

    def _builtin_path(self, value: str, *, required: bool = True) -> Path | None:
        if self._root is None:
            raise SkillPackageError("not a built-in Skill package")
        path = _relative_path(value)
        candidate = self._root.joinpath(*path.parts)
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            if not required:
                return None
            raise SkillPackageError(f"Skill package resource is missing: {value}") from exc
        except (OSError, RuntimeError) as exc:
            raise SkillPackageError(f"Skill package resource is unavailable: {value}") from exc
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise SkillPackageError(f"Skill package path escapes its root: {value}") from exc
        if not resolved.is_file():
            raise SkillPackageError(f"Skill package resource is not a file: {value}")
        return resolved

    def _read_builtin(self, value: str, limit: int) -> bytes:
        path = self._builtin_path(value)
        assert path is not None
        try:
            if path.stat().st_size > limit:
                raise SkillPackageError(f"Skill package resource exceeds its size limit: {value}")
            data = path.read_bytes()
        except (OSError, RuntimeError) as exc:
            raise SkillPackageError(f"Skill package resource is unavailable: {value}") from exc
        if len(data) > limit:
            raise SkillPackageError(f"Skill package resource exceeds its size limit: {value}")
        return data

    def _candidates(self, kind: PackageResourceKind) -> list[str]:
        if self._version is not None:
            if kind == "media":
                return sorted(self._media)
            values: list[str] = []
            for path in self._references:
                if kind == "shots" and path.startswith("references/shots/"):
                    if PurePosixPath(path).suffix.lower() == ".md":
                        _shot_category(path)
                        values.append(path)
                elif kind == "sequences" and path.startswith("references/sequences/"):
                    if PurePosixPath(path).suffix.lower() == ".md":
                        _validate_sequence_path(path)
                        values.append(path)
                elif kind == "demos" and path.startswith("demos/"):
                    values.append(path)
                elif kind == "template" and (
                    path == _LEGACY_TEMPLATE_PATH or path.startswith("template/")
                ):
                    values.append(path)
            return sorted(values)

        assert self._root is not None
        candidates: list[Path] = []
        if kind == "template":
            legacy = self._root / _LEGACY_TEMPLATE_PATH
            if legacy.exists() or legacy.is_symlink():
                candidates.append(legacy)
            base = self._root / "template"
        else:
            base = self._root / {
                "shots": "references/shots",
                "sequences": "references/sequences",
                "demos": "demos",
                "media": "gallery/media",
            }[kind]
        if base.exists():
            candidates.extend(path for path in base.rglob("*") if not path.is_dir())
        values = []
        for candidate in candidates:
            value = candidate.relative_to(self._root).as_posix()
            path = _relative_path(value)
            self._builtin_path(value)  # resolve every listed symlink inside the root
            if kind == "media":
                if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"}:
                    continue
            else:
                if path.suffix.lower() not in _TEXT_SUFFIXES:
                    continue
                if kind == "shots":
                    _shot_category(value)
                elif kind == "sequences":
                    _validate_sequence_path(value)
            values.append(value)
        return sorted(values)

    def _validate_builtin_media_limits(self) -> None:
        paths = self._candidates("media")
        if len(paths) > _MAX_MEDIA_FILES:
            raise SkillPackageError("Skill package exceeds its media count limit")
        total = 0
        for value in paths:
            path = self._builtin_path(value)
            assert path is not None
            try:
                size = path.stat().st_size
            except OSError as exc:
                raise SkillPackageError(f"Skill preview media is unavailable: {value}") from exc
            if size <= 0 or size > _MAX_MEDIA_FILE_BYTES:
                raise SkillPackageError(f"Skill preview media has an invalid byte size: {value}")
            total += size
        if total > _MAX_MEDIA_BYTES:
            raise SkillPackageError("Skill package exceeds its media size limit")

    def available_resources(self) -> tuple[str, ...]:
        """Report present logical resources without pretending incomplete packs are full."""
        available = ["SKILL.md"]
        for kind in ("shots", "sequences", "media", "demos", "template"):
            if self._candidates(kind):
                available.append(kind)
        if self._version is not None:
            has_library = _LIBRARY_PATH in self._references
        else:
            has_library = self._builtin_path(_LIBRARY_PATH, required=False) is not None
        if has_library:
            available.append("library")
        return tuple(available)

    async def list_resources(self, kind: PackageResourceKind) -> list[SkillPackageResource]:
        if kind not in {"shots", "sequences", "demos", "media", "template"}:
            raise SkillPackageError(f"unsupported Skill package resource kind: {kind}")
        paths = self._candidates(kind)
        limit = _MAX_SHOTS if kind == "shots" else _MAX_SEQUENCES if kind == "sequences" else None
        if limit is not None and len(paths) > limit:
            raise SkillPackageError(f"Skill package exceeds its {kind} count limit")
        if kind == "media":
            resources = [await self.get_media(path) for path in paths]
            if len(resources) > _MAX_MEDIA_FILES:
                raise SkillPackageError("Skill package exceeds its media count limit")
            if sum(item.byte_size for item in resources) > _MAX_MEDIA_BYTES:
                raise SkillPackageError("Skill package exceeds its media size limit")
            return resources
        if len(paths) > _MAX_REFERENCES:
            raise SkillPackageError("Skill package exceeds its text resource count limit")
        result = []
        for path in paths:
            if self._version is not None:
                source = self._references[path]
            else:
                source = await self.read_text(path)
            result.append(_resource(source))
        if sum(item.byte_size for item in result) > _MAX_TOTAL_BYTES:
            raise SkillPackageError("Skill package exceeds its listed text size limit")
        return result

    async def read_text(self, value: str) -> SkillSource:
        path = _relative_path(value)
        if not _readable_text_path(path):
            raise SkillPackageError(f"Skill text resource is outside readable package roots: {value}")
        role = _role(path)
        if self._version is not None:
            if value == "SKILL.md":
                text = self._version.instructions
                return SkillSource(
                    path=value,
                    role="reference",
                    digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    text=text,
                )
            source = self._references.get(value)
            if source is None:
                raise SkillPackageError(f"Skill text resource is missing: {value}")
            if source.role != role:
                raise SkillPackageError(f"Skill source role mismatch: {value}")
            if hashlib.sha256(source.text.encode("utf-8")).hexdigest() != source.digest:
                raise SkillPackageError(f"Skill source digest mismatch: {value}")
            return source
        data = self._read_builtin(value, _MAX_FILE_BYTES)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SkillPackageError(f"Skill text resource is not valid UTF-8: {value}") from exc
        return SkillSource(
            path=value,
            role=role,
            digest=hashlib.sha256(data).hexdigest(),
            text=text,
        )

    async def get_media(self, value: str) -> SkillPackageResource:
        path = _relative_path(value)
        if path.parts[:2] != ("gallery", "media"):
            raise SkillPackageError(f"Skill preview is outside gallery/media: {value}")
        if self._version is not None:
            media = self._media.get(value)
            if media is None:
                raise SkillPackageError(f"Skill preview media is missing: {value}")
            try:
                validate_skill_media_identity(media)
            except ExternalSkillError as exc:
                raise SkillPackageError(str(exc)) from exc
            return _resource(media)
        data = self._read_builtin(value, _MAX_MEDIA_FILE_BYTES)
        if not data:
            raise SkillPackageError(f"Skill preview media is empty: {value}")
        media = SkillMedia(
            path=value,
            digest=hashlib.sha256(data).hexdigest(),
            storage_key=None,
            mime_type=_MEDIA_TYPES.get(path.suffix.lower(), ""),
            byte_size=len(data),
        )
        try:
            validate_skill_media_bytes(media, data)
        except ExternalSkillError as exc:
            raise SkillPackageError(str(exc)) from exc
        return _resource(media)

    async def read_media(self, value: str) -> bytes:
        media = await self.get_media(value)
        if self._version is None:
            data = self._read_builtin(value, _MAX_MEDIA_FILE_BYTES)
        else:
            assert media.storage_key is not None
            data = await storage.read(media.storage_key)
        identity = SkillMedia(
            path=media.path,
            digest=media.digest,
            storage_key=media.storage_key,
            mime_type=media.mime_type or "",
            byte_size=media.byte_size,
        )
        try:
            validate_skill_media_bytes(identity, data)
        except ExternalSkillError as exc:
            raise SkillPackageError(str(exc)) from exc
        return data

    async def _entry(self, raw: Any, *, default_path: str | None = None) -> SkillLibraryEntry:
        if not isinstance(raw, dict):
            raise SkillPackageError("Skill library entries must be mappings")
        values = dict(raw)
        path = values.pop("path", default_path)
        if not isinstance(path, str):
            raise SkillPackageError("Skill library entry needs a shot-card path")
        category = _shot_category(path)
        source = await self.read_text(path)
        declared_category = values.pop("category", category)
        if declared_category != category:
            raise SkillPackageError(f"Skill library category does not match its card: {path}")
        entry_id = values.pop("id", PurePosixPath(path).stem)
        name = values.pop("name", PurePosixPath(path).stem)
        if not isinstance(entry_id, str) or not entry_id.strip() or len(entry_id.strip()) > 128:
            raise SkillPackageError(f"Skill library entry id is invalid: {path}")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 256:
            raise SkillPackageError(f"Skill library entry name is invalid: {path}")
        energy = values.pop("energy", None)
        if energy is not None and (
            isinstance(energy, bool)
            or not isinstance(energy, (str, int, float))
            or (isinstance(energy, float) and not math.isfinite(energy))
            or (isinstance(energy, str) and len(energy) > 256)
        ):
            raise SkillPackageError(f"Skill library energy must be a string or number: {path}")
        use = values.pop("use", values.pop("use_for", values.pop("purpose", None)))
        if use is not None and (not isinstance(use, str) or len(use) > 2048):
            raise SkillPackageError(f"Skill library use must be a bounded string: {path}")
        variants = _variants(values.pop("variants", None))
        previews_value = values.pop("previews", values.pop("preview", None))
        if previews_value is None:
            previews_value = []
        if isinstance(previews_value, (str, dict)):
            previews_value = [previews_value]
        if not isinstance(previews_value, list) or len(previews_value) > _MAX_INDEX_PREVIEWS:
            raise SkillPackageError(f"Skill library previews must be a bounded list: {path}")
        previews: list[SkillLibraryPreview] = []
        for item in previews_value:
            if isinstance(item, str):
                item = {"path": item}
            if not isinstance(item, dict) or set(item) - {"path", "digest", "mime_type", "byte_size"}:
                raise SkillPackageError(f"invalid Skill library preview reference: {path}")
            preview_path = item.get("path")
            if not isinstance(preview_path, str):
                raise SkillPackageError(f"Skill library preview needs a path: {path}")
            media = await self.get_media(preview_path)
            if item.get("digest") is not None and item["digest"] != media.digest:
                raise SkillPackageError(f"Skill library preview digest mismatch: {preview_path}")
            if "mime_type" in item and item["mime_type"] != media.mime_type:
                raise SkillPackageError(f"Skill library preview MIME mismatch: {preview_path}")
            if "byte_size" in item and (type(item["byte_size"]) is not int or item["byte_size"] != media.byte_size):
                raise SkillPackageError(f"Skill library preview byte size mismatch: {preview_path}")
            previews.append(
                SkillLibraryPreview(
                    path=media.path,
                    digest=media.digest,
                    mime_type=media.mime_type or "",
                    byte_size=media.byte_size,
                )
            )
        declared_digest = values.pop("digest", None)
        if declared_digest is not None and declared_digest != source.digest:
            raise SkillPackageError(f"Skill library card digest mismatch: {path}")
        declared_metadata = values.pop("metadata", {})
        if not isinstance(declared_metadata, dict):
            raise SkillPackageError(f"Skill library metadata must be a mapping: {path}")
        metadata = _static_value({**values, **declared_metadata})
        return SkillLibraryEntry(
            id=entry_id.strip(),
            path=path,
            category=category,
            name=name.strip(),
            energy=energy,
            use=use,
            metadata=metadata,
            variants=variants,
            previews=previews,
            digest=source.digest,
        )

    async def library_index(self) -> SkillLibraryIndex:
        """Read library.json, or project only shot-card frontmatter in memory."""
        entries: list[SkillLibraryEntry] = []
        if self._version is not None:
            has_library = _LIBRARY_PATH in self._references
        else:
            has_library = self._builtin_path(_LIBRARY_PATH, required=False) is not None
        if has_library:
            source = await self.read_text(_LIBRARY_PATH)
            try:
                payload = json.loads(source.text)
            except json.JSONDecodeError as exc:
                raise SkillPackageError(f"Skill library.json is invalid JSON: {exc}") from exc
            if self._root is not None and isinstance(payload, dict) and "cards" in payload:
                payload = self._gallery_projection(payload)
            if not isinstance(payload, dict) or set(payload) - {"schema_version", "shots", "entries"}:
                raise SkillPackageError("Skill library.json has an unsupported root shape")
            if payload.get("schema_version", 1) != 1 or isinstance(
                payload.get("schema_version", 1), bool
            ):
                raise SkillPackageError("Skill library.json schema_version must be 1")
            if ("shots" in payload) == ("entries" in payload):
                raise SkillPackageError("Skill library.json needs exactly one shots/entries list")
            raw_entries = payload.get("shots", payload.get("entries"))
            if not isinstance(raw_entries, list) or len(raw_entries) > _MAX_SHOTS:
                raise SkillPackageError("Skill library.json entries must be a bounded list")
            for raw in raw_entries:
                entries.append(await self._entry(raw))
            index_source = "gallery/api/library.json"
        else:
            shot_paths = self._candidates("shots")
            if len(shot_paths) > _MAX_SHOTS:
                raise SkillPackageError("Skill package exceeds its shot-card count limit")
            for path in shot_paths:
                source = await self.read_text(path)
                metadata: dict[str, Any] = {}
                if source.text.startswith("---\n"):
                    end = source.text.find("\n---\n", 4)
                    if end < 0:
                        raise SkillPackageError(f"shot card has unterminated frontmatter: {path}")
                    raw = source.text[4:end]
                    if len(raw.encode("utf-8")) > _MAX_FRONTMATTER_BYTES:
                        raise SkillPackageError(f"shot card frontmatter is too large: {path}")
                    try:
                        loaded = yaml.safe_load(raw)
                    except yaml.YAMLError as exc:
                        raise SkillPackageError(f"shot card frontmatter is invalid: {path}") from exc
                    if loaded is not None and not isinstance(loaded, dict):
                        raise SkillPackageError(f"shot card frontmatter must be a mapping: {path}")
                    metadata = loaded or {}
                entries.append(await self._entry(metadata, default_path=path))
            index_source = "references/shots"

        entries.sort(key=lambda entry: entry.path)
        ids: set[str] = set()
        paths: set[str] = set()
        for entry in entries:
            if entry.id in ids or entry.path in paths:
                raise SkillPackageError(f"duplicate Skill library id or path: {entry.id}")
            ids.add(entry.id)
            paths.add(entry.path)
        return SkillLibraryIndex(source=index_source, entries=entries)

    def _gallery_projection(self, payload: dict) -> dict:
        """Project an installed Gallery export onto the existing shot index."""
        cards = payload["cards"]
        if not isinstance(cards, list) or len(cards) > _MAX_SHOTS:
            raise SkillPackageError("Skill Gallery cards must be a bounded list")
        entries = []
        for card in cards:
            if not isinstance(card, dict):
                raise SkillPackageError("Skill Gallery cards must be mappings")
            styles = card.get("styles", [])
            if not isinstance(styles, list) or not all(isinstance(style, dict) for style in styles):
                raise SkillPackageError("Skill Gallery styles must be mappings")
            previews = []
            for style in styles:
                key = style.get("key")
                if not isinstance(key, str) or not key or "/" in key or "\\" in key:
                    raise SkillPackageError("Skill Gallery style needs a local key")
                for path in (f"gallery/media/{key}.mp4", f"gallery/media/poster/{key}.jpg"):
                    if self._builtin_path(path, required=False) is not None and path not in previews:
                        previews.append(path)
            entries.append({
                "id": card.get("name"),
                "path": card.get("source"),
                "category": card.get("category"),
                "name": card.get("name"),
                "energy": card.get("energy"),
                "use": card.get("use"),
                "variants": [{"id": style.get("key"), "name": style.get("label")} for style in styles],
                "previews": previews,
            })
        return {"shots": entries}


def open_builtin_skill_package(skill_id: str, version: str | None = None) -> SkillPackageReader:
    """Open one deployed built-in directory with symlink-safe root confinement."""
    path = _relative_path(skill_id)
    if len(path.parts) != 1:
        raise SkillPackageError(f"invalid built-in Skill id: {skill_id!r}")
    from app.config import settings

    base = _PACKS_ROOT
    directory = base / skill_id
    if skill_id in settings.managed_skill_versions:
        version = version or settings.managed_skill_versions.get(skill_id)
        if settings.managed_skill_root is None or not version:
            raise SkillPackageError(f"managed Skill is not installed: {skill_id}")
        if len(_relative_path(version).parts) != 1:
            raise SkillPackageError(f"invalid managed Skill version: {version!r}")
        base = settings.managed_skill_root.resolve()
        directory = base / skill_id / version
    try:
        root = directory.resolve(strict=True)
        root.relative_to(base)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise SkillPackageError(f"built-in Skill package is unavailable: {skill_id}") from exc
    if root == base or not root.is_dir():
        raise SkillPackageError(f"built-in Skill package is unavailable: {skill_id}")
    reader = SkillPackageReader(root=root)
    reader._builtin_path("SKILL.md")
    reader._validate_builtin_media_limits()
    return reader


async def open_external_skill_package(
    db: AsyncSession,
    *,
    owner_id: UUID,
    skill_version_id: UUID,
) -> SkillPackageReader:
    """Resolve owner + immutable version before exposing any package content."""
    version = await get_skill_version(
        db,
        owner_id=owner_id,
        skill_version_id=skill_version_id,
    )
    skill = await db.get(UserSkill, version.skill_id)
    if skill is None or skill.owner_id != owner_id:
        raise SkillPackageError("SkillVersion is unavailable to this user")
    return SkillPackageReader(version=version, skill=skill)
