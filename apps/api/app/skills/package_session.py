"""One bounded progressive-read session for the currently bound Skill package.

The session, not the model, owns the immutable PackageReader. Tool arguments
select only logical resources inside that reader; they cannot switch owner,
SkillVersion, local root, URL, or storage identity. Observations contain real
package facts and bytes, never assistant-copy drafts.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid5

import structlog

from pydantic import BaseModel, ConfigDict, Field

from app.agents.errors import AgentBudgetError
from app.editing.schemas import ProgramOutput, REMOTION_RESOURCE_LIMIT
from app.models.ids import source_snapshot_id
from app.models.schemas import MediaInput, MediaInputType
from app.skills.package_reader import (
    SkillLibraryIndex,
    SkillLibraryPreview,
    SkillPackageError,
    SkillPackageReader,
)

logger = structlog.get_logger()

_MAX_CALLS = 24
_MAX_GENERATIONS = 16
_READ_TIMEOUT_SECONDS = 240.0
_MAX_TEXT_CHARS = 240_000
_MAX_DEMO_FILES = 24
_MAX_MEDIA_FILES = 4
_MAX_MEDIA_BYTES = 16 * 1024 * 1024
_MAX_TEXT_SLICE = 40_000
_GENERATOR_ROOT = "template/generators/"


class SkillPackageBudgetError(SkillPackageError, AgentBudgetError):
    """A terminal shared-budget exhaustion, not a repairable package read."""


class SkillGeneratorDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry: str
    composition_id: str
    files: list[str] = Field(min_length=2, max_length=24)
    resources: dict[str, str] = Field(default_factory=dict, max_length=REMOTION_RESOURCE_LIMIT)
    output: ProgramOutput


class ListSkillShotsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str | None = Field(default=None, max_length=64)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=40, ge=1, le=80)


class ReadSkillReferenceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=240)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=30_000, ge=1, le=_MAX_TEXT_SLICE)


class ReadSkillDemoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=240)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=30_000, ge=1, le=_MAX_TEXT_SLICE)


class GetSkillPreviewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_id: str = Field(min_length=1, max_length=128)
    path: str | None = Field(
        default=None,
        description="镜头索引中的一个确切预览路径。省略则取其声明的首个预览。",
    )


@dataclass(frozen=True)
class PackageObservation:
    text: str
    ok: bool = True
    images: tuple[MediaInput, ...] = ()


@dataclass
class SkillPackageSession:
    reader: SkillPackageReader
    owner_id: UUID | None = None
    package_identity: UUID | None = None
    calls: int = 0
    generations: int = 0
    text_chars: int = 0
    media_files: int = 0
    media_bytes: int = 0
    demo_paths: set[str] = field(default_factory=set)
    reads: list[dict[str, Any]] = field(default_factory=list)
    initial_content: str = ""
    evidence: dict[tuple[str, int, int], str] = field(default_factory=dict)
    _text_cache: dict[str, Any] = field(default_factory=dict)
    _initial_lengths: dict[str, int] = field(default_factory=dict)
    _initial_parts: dict[str, str] = field(default_factory=dict)
    _library: SkillLibraryIndex | None = None
    _media_cache: dict[str, bytes] = field(default_factory=dict)
    _preview_checks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def can_read(self) -> bool:
        return (
            self.generations < _MAX_GENERATIONS
            and self.calls < _MAX_CALLS
            and self.text_chars < _MAX_TEXT_CHARS
        )

    def receipt_identity(self, skill: Any) -> str:
        return str(self.package_identity or skill.model_dump(mode="json"))

    async def restore_text_reads(
        self,
        receipt: dict[str, Any],
        *,
        skill: Any,
        owner_id: UUID,
    ) -> int:
        """Restore settled text facts only after identity, owner and digest checks."""
        reference = skill.model_dump(mode="json")
        if (
            receipt.get("package_identity") != self.receipt_identity(skill)
            or receipt.get("skill_reference") != reference
            or receipt.get("owner_id") not in {None, str(owner_id)}
            or (self.owner_id is not None and self.owner_id != owner_id)
        ):
            return 0
        restored = 0
        for read in receipt.get("reads") or []:
            if not isinstance(read, dict) or read.get("kind") not in {"initial", "reference", "demo"}:
                continue
            path, digest = read.get("path"), read.get("digest")
            if not isinstance(path, str) or not isinstance(digest, str):
                continue
            try:
                current = await self.reader.read_text(path)
            except (SkillPackageError, ValueError, OSError):
                continue
            if current.digest != digest:
                continue
            if any(
                existing.get("path") == path
                and existing.get("digest") == digest
                and existing.get("kind") == read.get("kind")
                and existing.get("offset") == read.get("offset")
                for existing in self.reads
            ):
                continue
            self.reads.append(dict(read))
            restored += 1
        return restored

    def read_tool_names(self) -> set[str]:
        """All package reads share the same bounded ordinary Chat loop."""
        if not self.can_read():
            return set()
        return {"list_skill_shots", "read_skill_reference", "read_skill_demo", "get_skill_preview"}

    @property
    def director_context(self) -> str:
        # Exact successful observations only; no generated summary or hidden
        # unbounded read. Initial + evidence never exceeds the text budget.
        return self.initial_content + "\n\n已读取的包内证据（直接复用，无需重读）：\n" + "\n".join(self.evidence.values())

    @property
    def execution_facts(self) -> dict[str, Any]:
        return {
            "generations": self.generations, "reads": self.calls,
            "preview_checks": list(self._preview_checks.values()),
            "media_files": self.media_files,
            "version_saved": False, "run_started": False,
        }

    def budget_error(self, message: str) -> SkillPackageBudgetError:
        error = SkillPackageBudgetError(message)
        error.facts = self.execution_facts
        return error

    def _check_budget(self) -> None:
        if self.calls >= _MAX_CALLS:
            raise self.budget_error(f"Skill read call budget exhausted ({_MAX_CALLS})")

    def charge_generation(self) -> None:
        if self.generations >= _MAX_GENERATIONS:
            raise self.budget_error(
                f"Director generation budget exhausted ({_MAX_GENERATIONS})"
            )
        self.generations += 1
        logger.info("director_generation", generation=self.generations,
                    remaining_generations=_MAX_GENERATIONS - self.generations, reads=self.calls)

    def _charge_text(self, text: str) -> None:
        self.text_chars += len(text)
        if self.text_chars > _MAX_TEXT_CHARS:
            raise self.budget_error("Skill read text budget exhausted")

    def _record(self, path: str, digest: str, kind: str, **facts: Any) -> None:
        self.reads.append({"path": path, "digest": digest, "kind": kind, **facts})
        logger.info("director_package_read", path=path, digest=digest,
                    kind=kind, reads=self.calls, text_chars=self.text_chars)

    async def _read_with_timeout(self, operation):
        """Only the current IO operation owns this timeout, never session age."""
        try:
            async with asyncio.timeout(_READ_TIMEOUT_SECONDS):
                return await operation
        except TimeoutError as exc:
            raise self.budget_error("Skill read execution timed out") from exc

    async def read_initial(self, paths: list[str]) -> str:
        """Read the small mandatory entry set once; cards/demos stay on demand."""
        for path in dict.fromkeys(paths):
            if path in self._initial_parts:
                continue
            self._check_budget()
            self.calls += 1
            source = self._text_cache.get(path)
            if source is None:
                source = await self._read_with_timeout(self.reader.read_text(path))
                self._text_cache[path] = source
            text = source.text[:_MAX_TEXT_SLICE]
            self._initial_lengths[path] = len(text)
            truncated = len(source.text) > len(text)
            section = (
                f"PACKAGE RESOURCE {path} (digest {source.digest}; "
                f"truncated={str(truncated).lower()}):\n{text}"
            )
            self._charge_text(section + "\n\n")
            self._initial_parts[path] = section
            self._record(path, source.digest, "initial", truncated=truncated)
        self.initial_content = "\n\n".join(self._initial_parts.values())
        return self.initial_content

    async def _index(self) -> SkillLibraryIndex:
        library = self._library
        if library is None:
            library = await self.reader.library_index()
            self._library = library
        return library

    async def _list_shots(self, args: ListSkillShotsArgs) -> PackageObservation:
        index = await self._index()
        entries = [
            entry for entry in index.entries
            if args.category is None or entry.category == args.category
        ]
        page = entries[args.offset:args.offset + args.limit]
        sequences = await self.reader.list_resources("sequences")
        templates = await self.reader.list_resources("template")
        payload = {
            "index_source": index.source,
            "total_matching_shots": len(entries),
            "offset": args.offset,
            "returned": len(page),
            "shots": [
                {
                    "id": entry.id,
                    "path": entry.path,
                    "category": entry.category,
                    "name": entry.name,
                    "energy": entry.energy,
                    "use": (entry.use or "")[:300],
                    "digest": entry.digest,
                    "variants": [item.model_dump(mode="json") for item in entry.variants],
                    "preview_paths": [item.path for item in entry.previews],
                    "metadata": entry.metadata,
                }
                for entry in page
            ],
            "sequences": [item.model_dump(mode="json") for item in sequences],
            "templates": [item.model_dump(mode="json") for item in templates],
        }
        if self.package_identity is not None:
            generators = []
            for item in templates:
                if item.path.startswith(_GENERATOR_ROOT) and item.path.endswith(".json"):
                    resource_id = item.path[len(_GENERATOR_ROOT):-5]
                    if "/" in resource_id:
                        continue
                    try:
                        declaration, digest = await self.generator_declaration(resource_id)
                    except SkillPackageError as exc:
                        generators.append({"id": resource_id, "error": str(exc)})
                    else:
                        generators.append({
                            "id": resource_id,
                            "composition_id": declaration.composition_id,
                            "duration_seconds": declaration.output.duration_frames / declaration.output.fps,
                            "digest": digest,
                        })
            if generators:
                payload["generator_resources"] = generators
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self._charge_text(text)
        projection_digest = hashlib.sha256(
            index.model_dump_json(exclude_none=True).encode("utf-8")
        ).hexdigest()
        self._record(index.source, projection_digest, "index", returned=len(page))
        return PackageObservation(text)

    async def _read_text(
        self,
        path: str,
        offset: int,
        limit: int,
        *,
        demo: bool,
    ) -> PackageObservation:
        if demo:
            if not path.startswith(("demos/", "assets/lib/")):
                raise SkillPackageError("read_skill_demo accepts only demos/ or declared assets/lib paths")
            if path in self.demo_paths:
                pass
            elif len(self.demo_paths) >= _MAX_DEMO_FILES:
                raise SkillPackageError("Skill demo-file budget exhausted")
        elif path.startswith(("demos/", "assets/lib/")):
            raise SkillPackageError("use read_skill_demo for implementation source")
        cache_key = (path, offset, limit)
        if cache_key in self.evidence:
            logger.info("director_package_read_reused", path=path)
            return PackageObservation(self.evidence[cache_key])
        source = self._text_cache.get(path)
        if source is None:
            source = await self.reader.read_text(path)
            self._text_cache[path] = source
        text = source.text[offset:offset + limit]
        if offset > len(source.text):
            raise SkillPackageError("text offset exceeds the resource length")
        if demo:
            self.demo_paths.add(path)
        self._record(
            path,
            source.digest,
            "demo" if demo else "reference",
            offset=offset,
            returned_chars=len(text),
            total_chars=len(source.text),
            truncated=offset + len(text) < len(source.text),
        )
        payload = {
            "path": path,
            "digest": source.digest,
            "offset": offset,
            "returned_chars": len(text),
            "total_chars": len(source.text),
            "truncated": offset + len(text) < len(source.text),
            "text": text,
        }
        result = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        # Charge the serialized envelope too, keeping cross-stage context bounded.
        if offset + len(text) <= self._initial_lengths.get(path, -1):
            # Already included verbatim in initial_content; don't inject a
            # second copy into every downstream Director prompt.
            return PackageObservation(result)
        self._charge_text(result)
        self.evidence[cache_key] = result
        return PackageObservation(result)

    async def generator_declaration(self, resource_id: str) -> tuple[SkillGeneratorDeclaration, str]:
        if self.package_identity is None or not resource_id or "/" in resource_id:
            raise SkillPackageError("choose a declared Generator id from the bound external Skill")
        source = await self.reader.read_text(f"{_GENERATOR_ROOT}{resource_id}.json")
        try:
            declaration = SkillGeneratorDeclaration.model_validate_json(source.text)
        except ValueError as exc:
            raise SkillPackageError(f"invalid Generator declaration {resource_id!r}: {exc}") from exc
        return declaration, source.digest

    async def fixed_image_binding(self, path: str) -> dict[str, Any]:
        """Resolve one current-SkillVersion image into a server-derived snapshot identity."""
        if self.owner_id is None or self.package_identity is None:
            raise SkillPackageError("this package has no external SkillVersion resource binding")
        media = await self.reader.get_media(path)
        if media.mime_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise SkillPackageError("only PNG, JPEG and WebP package images can become fixed resources")
        anchor = uuid5(
            UUID(int=0),
            f"skill-version-media:{self.package_identity}:{media.path}:{media.digest}",
        )
        return {
            "path": media.path,
            "snapshot_id": source_snapshot_id(self.owner_id, anchor, "image", media.digest),
            "snapshot_digest": media.digest,
            "content_type": media.mime_type,
            "storage_key": media.storage_key,
            "byte_size": media.byte_size,
        }

    async def _read_media_budgeted(self, preview: SkillLibraryPreview) -> bytes:
        cached = self._media_cache.get(preview.path)
        if cached is not None and hashlib.sha256(cached).hexdigest() == preview.digest:
            return cached
        if self.media_files >= _MAX_MEDIA_FILES:
            raise SkillPackageBudgetError("Skill preview-media count budget exhausted")
        if self.media_bytes + preview.byte_size > _MAX_MEDIA_BYTES:
            raise SkillPackageBudgetError("Skill preview-media byte budget exhausted")
        data = await self._read_with_timeout(self.reader.read_media(preview.path))
        self.media_files += 1
        self.media_bytes += len(data)
        if self.media_bytes > _MAX_MEDIA_BYTES:
            raise SkillPackageBudgetError("Skill preview-media byte budget exhausted")
        self._media_cache[preview.path] = data
        return data

    async def read_fixed_image(self, binding: dict[str, Any]) -> bytes:
        preview = SkillLibraryPreview(
            path=binding["path"],
            digest=binding["snapshot_digest"],
            mime_type=binding["content_type"],
            byte_size=binding["byte_size"],
        )
        return await self._read_media_budgeted(preview)

    async def _preview(self, args: GetSkillPreviewArgs) -> PackageObservation:
        index = await self._index()
        entry = next((item for item in index.entries if item.id == args.shot_id), None)
        if entry is None:
            raise SkillPackageError(f"unknown Skill shot id: {args.shot_id}")
        if not entry.previews:
            self._preview_checks[args.shot_id] = {
                "shot_id": args.shot_id,
                "available": False,
                "preview_path": None,
            }
            return PackageObservation(json.dumps({
                "shot_id": args.shot_id,
                "available": False,
                "previews": [],
                "fact": "this package declares no real preview media for the shot",
            }, separators=(",", ":")))
        preview = (
            next((item for item in entry.previews if item.path == args.path), None)
            if args.path is not None else next(
                (
                    item for item in entry.previews
                    if item.mime_type in {"image/jpeg", "image/png", "image/webp"}
                ),
                entry.previews[0],
            )
        )
        if preview is None:
            raise SkillPackageError("preview path is not declared on this shot")
        binding = (
            await self.fixed_image_binding(preview.path)
            if self.owner_id is not None
            and preview.mime_type in {"image/png", "image/jpeg", "image/webp"}
            else None
        )
        data = await self._read_media_budgeted(preview)
        kind = MediaInputType.VIDEO if preview.mime_type.startswith("video/") else MediaInputType.IMAGE
        media = MediaInput(
            type=kind,
            mime=preview.mime_type,
            data_url=f"data:{preview.mime_type};base64," + base64.b64encode(data).decode("ascii"),
            caption=f"Real Skill preview {preview.path}; digest {preview.digest}",
        )
        self._record(preview.path, preview.digest, "preview", byte_size=len(data))
        self._preview_checks[args.shot_id] = {
            "shot_id": args.shot_id,
            "available": True,
            "preview_path": preview.path,
            "preview_digest": preview.digest,
            "mime_type": preview.mime_type,
        }
        return PackageObservation(
            json.dumps({
                "shot_id": args.shot_id,
                "available": True,
                "preview": preview.model_dump(mode="json"),
                "generator_resource": (
                    {
                        "path": binding["path"],
                        "snapshot_id": str(binding["snapshot_id"]),
                        "snapshot_digest": binding["snapshot_digest"],
                        "content_type": binding["content_type"],
                    }
                    if binding is not None else None
                ),
            }, separators=(",", ":")),
            images=(media,),
        )

    async def observe(self, name: str, params: BaseModel | None) -> PackageObservation:
        """Execute one declared read; failures return facts for bounded repair."""
        try:
            async with asyncio.timeout(_READ_TIMEOUT_SECONDS):
                self._check_budget()
                self.calls += 1
                if name == "list_skill_shots" and isinstance(params, ListSkillShotsArgs):
                    return await self._list_shots(params)
                if name == "read_skill_reference" and isinstance(params, ReadSkillReferenceArgs):
                    return await self._read_text(params.path, params.offset, params.limit, demo=False)
                if name == "read_skill_demo" and isinstance(params, ReadSkillDemoArgs):
                    return await self._read_text(params.path, params.offset, params.limit, demo=True)
                if name == "get_skill_preview" and isinstance(params, GetSkillPreviewArgs):
                    return await self._preview(params)
                raise SkillPackageError(f"unknown or malformed Skill read: {name}")
        except TimeoutError as exc:
            raise self.budget_error("Skill read execution timed out") from exc
        except SkillPackageBudgetError:
            raise
        except (SkillPackageError, ValueError, OSError) as exc:
            return PackageObservation(
                json.dumps({"ok": False, "tool": name, "error": str(exc)}, ensure_ascii=False),
                ok=False,
            )

    @property
    def provenance(self) -> dict[str, Any]:
        reference_paths = list(dict.fromkeys(
            item["path"] for item in self.reads if item["kind"] != "index"
        ))
        return {
            "reference_paths": reference_paths,
            "reads": self.reads,
            "preview_checks": list(self._preview_checks.values()),
            "budget": {
                "calls": self.calls,
                "generations": self.generations,
                "text_chars": self.text_chars,
                "demo_files": len(self.demo_paths),
                "media_files": self.media_files,
                "media_bytes": self.media_bytes,
            },
        }
