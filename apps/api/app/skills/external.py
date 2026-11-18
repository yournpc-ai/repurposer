"""Untrusted external Skill package → a bounded, reviewable SkillDraft.

This module only parses caller-supplied bytes. It never extracts archives,
imports source modules, resolves tools, or executes scripts. Implementations
remain provenance until a later adapter proves that their required capabilities
are supported by the Composition/Generator contracts.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Mapping
from pathlib import PurePosixPath
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

_MAX_FILES = 2048
_MAX_FILE_BYTES = 1024 * 1024
_MAX_PACKAGE_BYTES = 128 * 1024 * 1024
_MAX_TOTAL_BYTES = 8 * 1024 * 1024
_MAX_PATH_LENGTH = 240
_MAX_PATH_DEPTH = 8
_MAX_FRONTMATTER_BYTES = 64 * 1024
_MAX_REFERENCES = 1536
_MAX_MEDIA_FILES = 256
_MAX_MEDIA_FILE_BYTES = 32 * 1024 * 1024
_MAX_MEDIA_BYTES = 96 * 1024 * 1024
_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_FRONTMATTER_KEYS = {
    "name",
    "description",
    "license",
    "compatibility",
    "allowed-tools",
    "metadata",
}
_TEXT_SUFFIXES = {
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".py",
    ".css",
}
_CODE_SUFFIXES = {".ts", ".tsx", ".js", ".mjs", ".cjs", ".py", ".css"}
_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class ExternalSkillError(ValueError):
    """A bounded package/validation diagnostic safe to show during import."""


class SkillSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    role: Literal["reference", "implementation", "script"]
    digest: str = Field(min_length=64, max_length=64)
    text: str


class UnauthorizedSkillDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["allowed_tool", "script"]
    name: str
    source_paths: list[str] = Field(min_length=1)


class SkillCapabilityGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: str
    source_paths: list[str] = Field(min_length=1)


class SkillCapabilityReport(BaseModel):
    """Observed requirements, not a compatibility guarantee."""

    model_config = ConfigDict(extra="forbid")

    supported: list[str] = []
    gaps: list[SkillCapabilityGap] = []
    unauthorized_dependencies: list[UnauthorizedSkillDependency] = []
    rejected_files: dict[str, str] = {}


class SkillInputDeclaration(BaseModel):
    """A reviewed input binding; external frontmatter cannot grant itself one."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=512)
    binding: Literal["text", "instruction", "media"]
    required: bool = True


class SkillPolicy(BaseModel):
    """Small deterministic Strict/Adaptive contract, not a constraint solver.

    Strict checks only fields explicitly pinned here. Adaptive carries the
    reviewed boundaries into the ordinary design read; demo copy, coordinates
    and durations never become Strict rules merely by appearing in references.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["strict", "adaptive"] = "adaptive"
    scene_count: int | None = Field(default=None, ge=1)
    duration_seconds: float | None = Field(default=None, gt=0, le=118)
    generator_runtime: Literal["draw-2d", "image-generation", "remotion-project"] | None = None
    adaptation_bounds: list[str] = Field(default=[], max_length=16)


class SkillMedia(BaseModel):
    """Content-addressed gallery media; raw bytes never enter version JSON."""

    model_config = ConfigDict(extra="forbid")

    path: str
    digest: str = Field(min_length=64, max_length=64)
    storage_key: str | None = None
    mime_type: str
    byte_size: int = Field(gt=0, le=_MAX_MEDIA_FILE_BYTES)
    # Present only between package parsing and the storage write. Exclusion
    # keeps both SkillDraft JSON and SkillVersion JSON free of media bytes.
    data: bytes | None = Field(default=None, exclude=True, repr=False)


class SkillDraft(BaseModel):
    """External instructions and source evidence pending user/system review."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    instructions: str
    references: list[SkillSource] = []
    media: list[SkillMedia] = []
    source_hash: str = Field(min_length=64, max_length=64)
    source_uri: str | None = None
    source_revision: str | None = None
    capability_report: SkillCapabilityReport
    declared_inputs: list[SkillInputDeclaration] = Field(default=[], max_length=32)
    policy: SkillPolicy = Field(default_factory=SkillPolicy)


def _safe_path(value: str) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_PATH_LENGTH
        or "\x00" in value
        or "\\" in value
    ):
        raise ExternalSkillError(f"unsafe Skill source path: {value!r}")
    raw_parts = value.split("/")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in raw_parts):
        raise ExternalSkillError(f"Skill source path must stay relative to the package: {value!r}")
    if len(path.parts) > _MAX_PATH_DEPTH or any(part == ".git" for part in path.parts):
        raise ExternalSkillError(f"unsupported Skill source path: {value!r}")
    return path


def skill_media_storage_key(path: str, digest: str) -> str:
    """Derive the only legal object key for one gallery media payload."""
    suffix = _safe_path(path).suffix.lower()
    if suffix not in _MEDIA_TYPES or not _DIGEST_RE.fullmatch(digest):
        raise ExternalSkillError(f"invalid Skill media identity: {path!r}")
    return f"skill-media/{digest[:2]}/{digest}{suffix}"


def _matches_media_type(data: bytes, suffix: str) -> bool:
    if suffix == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if suffix == ".webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if suffix == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".mp4":
        return len(data) >= 12 and data[4:8] == b"ftyp"
    if suffix == ".webm":
        return data.startswith(b"\x1a\x45\xdf\xa3")
    return False


def validate_skill_media_identity(media: SkillMedia) -> None:
    """Validate path, type, digest and the optional content-addressed key."""
    path = _safe_path(media.path)
    suffix = path.suffix.lower()
    expected_mime = _MEDIA_TYPES.get(suffix)
    expected_key = skill_media_storage_key(media.path, media.digest)
    if (
        path.parts[:2] != ("gallery", "media")
        or expected_mime is None
        or media.mime_type != expected_mime
        or not _DIGEST_RE.fullmatch(media.digest)
        or (media.storage_key is not None and media.storage_key != expected_key)
    ):
        raise ExternalSkillError(f"invalid Skill media identity: {media.path}")


def validate_skill_media_bytes(media: SkillMedia, data: bytes) -> None:
    """Fail closed on identity, size, content-type or object-key drift."""
    validate_skill_media_identity(media)
    if not data or len(data) > _MAX_MEDIA_FILE_BYTES or len(data) != media.byte_size:
        raise ExternalSkillError(f"Skill media byte size mismatch: {media.path}")
    if hashlib.sha256(data).hexdigest() != media.digest:
        raise ExternalSkillError(f"Skill media digest mismatch: {media.path}")
    if not _matches_media_type(data, PurePosixPath(media.path).suffix.lower()):
        raise ExternalSkillError(f"Skill media content does not match its type: {media.path}")


def skill_draft_payload(draft: SkillDraft) -> dict[str, Any]:
    """Serialize immutable identity without bytes or a new empty-field digest bump."""
    return draft.model_dump(
        mode="json",
        exclude={"media"} if not draft.media else None,
    )


def _role(path: PurePosixPath) -> Literal["reference", "implementation", "script"]:
    if "scripts" in path.parts:
        return "script"
    if path.suffix.lower() in _CODE_SUFFIXES:
        return "implementation"
    return "reference"


def _source_hash(sources: Mapping[str, str], media: Mapping[str, str]) -> str:
    rows = [
        {"path": path, "digest": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        for path, text in sources.items()
    ]
    rows.extend({"path": path, "digest": digest} for path, digest in media.items())
    rows.sort(key=lambda row: row["path"])
    encoded = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise ExternalSkillError("SKILL.md is missing its YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ExternalSkillError("SKILL.md has unterminated YAML frontmatter")
    raw = text[4:end]
    if len(raw.encode("utf-8")) > _MAX_FRONTMATTER_BYTES:
        raise ExternalSkillError("SKILL.md frontmatter exceeds its size limit")
    try:
        meta = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ExternalSkillError(f"SKILL.md frontmatter is invalid YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise ExternalSkillError("SKILL.md frontmatter must be a mapping")
    unknown = set(meta) - _FRONTMATTER_KEYS
    if unknown:
        raise ExternalSkillError(
            f"unsupported SKILL.md frontmatter keys: {sorted(unknown, key=str)}"
        )
    body = text[end + 5 :].strip()
    if not body:
        raise ExternalSkillError("SKILL.md instructions must not be empty")
    return meta, body


# Detection is intentionally evidence-based. The integration supplies the
# capabilities declared by its current Composition/Generator registry; a rule
# not present there remains a gap instead of being silently adapted away.
_CAPABILITY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (capability, re.compile(pattern, re.IGNORECASE))
    for capability, pattern in (
        ("runtime:remotion-source", r"from\s+['\"]remotion['\"]|npx\s+remotion|\bremotion\b"),
        ("runtime:three", r"@react-three|@remotion/three|['\"`]three['\"`]"),
        ("runtime:remotion-motion-blur", r"@remotion/motion-blur"),
        ("runtime:librosa", r"\blibrosa\b"),
        ("animation:opacity", r"\bopacity\b"),
        ("animation:transform.position", r"\btranslate[XY]\s*\(|transform\.position"),
        ("animation:transform.scale", r"\bscale\s*\(|transform\.scale"),
        ("animation:transform.rotation", r"\brotate\s*\(|transform\.rotation"),
        ("animation:blur", r"\bblur\s*\(|\bblur\s*[=:]|\bblur\s+\d"),
        ("animation:letter-spacing", r"\bletterSpacing\b|\bletter-spacing\b"),
        ("text:word-parts", r"split\(['\"] ['\"]\)|逐词|word-by-word"),
        ("capture:web", r"真实截图|page captures?|screenshots?"),
        ("audio:beat-grid", r"beat sync|beat-grid|节拍|卡拍"),
        ("external:freesound", r"\bfreesound\b"),
        ("tool:workbench", r"\bworkbench\b|工作台"),
        ("export:jianying", r"jianying-export|剪映工程"),
        ("publish:external", r"publish-upload-post|发布到社交平台"),
    )
)


def _capabilities(
    sources: Mapping[str, str], declared: Collection[str]
) -> tuple[list[str], list[SkillCapabilityGap]]:
    evidence: dict[str, set[str]] = {}
    for path, text in sources.items():
        for capability, pattern in _CAPABILITY_RULES:
            if pattern.search(text):
                evidence.setdefault(capability, set()).add(path)
    declared_set = set(declared)
    supported = sorted(capability for capability in evidence if capability in declared_set)
    gaps = [
        SkillCapabilityGap(capability=capability, source_paths=sorted(paths))
        for capability, paths in sorted(evidence.items())
        if capability not in declared_set
    ]
    return supported, gaps


def build_skill_draft(
    files: Mapping[str, bytes],
    *,
    declared_capabilities: Collection[str],
    source_uri: str | None = None,
    source_revision: str | None = None,
    declared_inputs: Collection[SkillInputDeclaration] = (),
    policy: SkillPolicy | None = None,
) -> SkillDraft:
    """Parse an untrusted package without granting any of its dependencies.

    ``files`` is an already-enumerated package, keyed by relative POSIX paths.
    Unsupported text/media types are reported and excluded; unsafe paths,
    oversized input, malformed UTF-8 and an invalid root SKILL.md fail closed.
    Accepted gallery media retains only its content identity in the draft; the
    persistence layer writes bytes to content-addressed object storage.
    ``source_hash`` covers the root instructions and every accepted source.
    """
    if source_revision is not None and source_uri is None:
        raise ExternalSkillError("a pinned Skill source revision needs its source URI")
    if not files or len(files) > _MAX_FILES:
        raise ExternalSkillError(f"Skill package must contain 1–{_MAX_FILES} files")
    if sum(len(data) for data in files.values()) > _MAX_PACKAGE_BYTES:
        raise ExternalSkillError("Skill package exceeds its raw package size limit")

    decoded: dict[str, str] = {}
    media: dict[str, SkillMedia] = {}
    rejected: dict[str, str] = {}
    for raw_path, data in sorted(files.items()):
        path = _safe_path(raw_path)
        if path.parts[:2] == ("gallery", "media"):
            mime_type = _MEDIA_TYPES.get(path.suffix.lower())
            if mime_type is None:
                rejected[raw_path] = "unsupported_media_type"
                continue
            if len(data) > _MAX_MEDIA_FILE_BYTES:
                raise ExternalSkillError(f"Skill media exceeds its file size limit: {raw_path}")
            if not _matches_media_type(data, path.suffix.lower()):
                rejected[raw_path] = "invalid_media_content"
                continue
            digest = hashlib.sha256(data).hexdigest()
            media[raw_path] = SkillMedia(
                path=raw_path,
                digest=digest,
                storage_key=skill_media_storage_key(raw_path, digest),
                mime_type=mime_type,
                byte_size=len(data),
                data=data,
            )
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            rejected[raw_path] = "unsupported_source_type"
            continue
        if len(data) > _MAX_FILE_BYTES:
            raise ExternalSkillError(f"Skill source exceeds its file size limit: {raw_path}")
        try:
            decoded[raw_path] = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExternalSkillError(f"Skill source is not valid UTF-8: {raw_path}") from exc

    if len(media) > _MAX_MEDIA_FILES:
        raise ExternalSkillError("Skill package exceeds its accepted-media limit")
    if sum(item.byte_size for item in media.values()) > _MAX_MEDIA_BYTES:
        raise ExternalSkillError("Skill package exceeds its accepted media size limit")
    if "SKILL.md" not in decoded:
        raise ExternalSkillError("Skill package needs a root SKILL.md text source")
    if sum(len(text.encode("utf-8")) for text in decoded.values()) > _MAX_TOTAL_BYTES:
        raise ExternalSkillError("Skill package exceeds its accepted text size limit")
    meta, instructions = _frontmatter(decoded["SKILL.md"])
    name = meta.get("name")
    description = meta.get("description")
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name) or len(name) > 64:
        raise ExternalSkillError("SKILL.md has an invalid skill name")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ExternalSkillError("SKILL.md needs a bounded description")
    allowed_tools = meta.get("allowed-tools") or []
    if not isinstance(allowed_tools, list) or not all(
        isinstance(tool, str) and tool.strip() for tool in allowed_tools
    ):
        raise ExternalSkillError("SKILL.md allowed-tools must be a string list")

    source_texts = {"SKILL.md": decoded["SKILL.md"]}
    references: list[SkillSource] = []
    unauthorized: list[UnauthorizedSkillDependency] = []
    for path, text in decoded.items():
        if path == "SKILL.md":
            continue
        source_texts[path] = text
        role = _role(PurePosixPath(path))
        references.append(
            SkillSource(
                path=path,
                role=role,
                digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                text=text,
            )
        )
        if role == "script":
            unauthorized.append(
                UnauthorizedSkillDependency(kind="script", name=path, source_paths=[path])
            )
    if len(references) > _MAX_REFERENCES:
        raise ExternalSkillError("Skill package exceeds its accepted-reference limit")
    for tool in sorted(allowed_tools):
        unauthorized.append(
            UnauthorizedSkillDependency(
                kind="allowed_tool",
                name=tool.strip(),
                source_paths=["SKILL.md"],
            )
        )

    supported, gaps = _capabilities(source_texts, declared_capabilities)
    return SkillDraft(
        name=name,
        description=description.strip(),
        instructions=instructions,
        references=references,
        media=list(media.values()),
        source_hash=_source_hash(
            source_texts,
            {path: item.digest for path, item in media.items()},
        ),
        source_uri=source_uri,
        source_revision=source_revision,
        capability_report=SkillCapabilityReport(
            supported=supported,
            gaps=gaps,
            unauthorized_dependencies=unauthorized,
            rejected_files=rejected,
        ),
        declared_inputs=list(declared_inputs),
        policy=policy or SkillPolicy(),
    )
