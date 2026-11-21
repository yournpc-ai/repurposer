"""Scene-bound visual asset specifications and exact-digest preparation."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5
from xml.etree import ElementTree as ET

from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from app.editing.schemas import (
    Clip,
    GeneratedImageOutput,
    GeneratorObject,
    LayoutBox,
    TimeRange,
)
from app.models.database import AsyncSessionLocal
from app.models.ids import source_snapshot_id
from app.models.schemas import VideoDraftRef, canonical_json_hash
from app.models.tables import SourceSnapshot
from app.providers import storage
from app.tools.video.media_analysis import (
    MediaAnalysisReport,
    analyze_image_bytes,
    image_media_input,
    image_reviewer_version,
    read_report,
    review_image_content,
    store_content_review,
    store_media_analysis,
)
from app.tools.video.preparation import store_source_bytes

VISUAL_ASSET_SCHEMA_VERSION = 1
VISUAL_ASSET_RUNNER_VERSION = "controlled-svg-browser-v2"
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
VISUAL_ASSET_BATCH_SIZE = 4
VISUAL_ASSET_MAX_PER_CALL = 64
_MANIFEST_PREFIX = "visual-assets"
_MAX_SVG_BYTES = 200_000
_MAX_SVG_ELEMENTS = 2048
_SVG_TIMEOUT_SECONDS = 20
_FONT_ROOT = Path(__file__).resolve().parents[3] / "assets" / "fonts"
_FONT_FILES = {
    "normal": _FONT_ROOT / "NotoSansSC-Regular.otf",
    "bold": _FONT_ROOT / "NotoSansSC-Bold.otf",
}


class VisualAssetError(ValueError):
    pass


class InvalidSVGProgramError(VisualAssetError):
    pass


class VisualAssetOutcomeUnknownError(VisualAssetError):
    pass


@dataclass
class VisualAssetBatch:
    assets: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)


class NormalizedRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    y: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    width: float = Field(default=1, gt=0, le=1, allow_inf_nan=False)
    height: float = Field(default=1, gt=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def _inside_canvas(self) -> NormalizedRegion:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("region must stay inside the normalized canvas")
        return self


class VisualOutputConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(default=1920, ge=16, le=4096)
    height: int = Field(default=1080, ge=16, le=4096)
    mime_type: Literal["image/png"] = "image/png"

    @model_validator(mode="after")
    def _pixel_budget(self) -> VisualOutputConstraints:
        if self.width * self.height > 16_777_216:
            raise ValueError("output exceeds the fixed 16-megapixel resource budget")
        return self


class ControlledSVGSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["controlled_svg"] = "controlled_svg"
    program: str = Field(
        min_length=1, max_length=_MAX_SVG_BYTES,
        description="完整 SVG。引用关系可用通用来源标签表达；图中具体 DOI 等标识符须逐字来自已固定来源。",
    )


class MiniMaxImageSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["minimax_image"] = "minimax_image"
    prompt: str = Field(min_length=1, max_length=2000)
    provider: Literal["minimax"] = "minimax"
    model: Literal["image-01"] = "image-01"


class ExistingImageSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["existing_image"] = "existing_image"
    snapshot_id: UUID = Field(
        description="使用图片资源的 snapshot_id，已采集的网页视图同样如此。",
    )
    snapshot_digest: str = Field(
        min_length=64, max_length=64, description="同一图片资源的确切摘要。",
    )
    visible_evidence: str | None = Field(
        default=None, min_length=1, max_length=2000, exclude_if=lambda value: value is None,
        description="描述源图中必须已经可见的主体、页面区段和原文。后续剪辑叠加的标题放入 on_screen_copy。",
    )


VisualAssetSource = Annotated[
    ControlledSVGSource | MiniMaxImageSource | ExistingImageSource,
    Field(discriminator="kind"),
]


class SceneAssetSpec(BaseModel):
    """主模型给出的场景创意要求。执行标识由系统推导。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    scene_id: str = Field(min_length=1, max_length=64, description="本规格所属的 scene_plan.scene_id。")
    intent: str = Field(min_length=1, max_length=2000)
    source: VisualAssetSource
    on_screen_copy: str | None = Field(
        default=None, max_length=4000,
        description="场景计划中的屏幕文案。使用现有图片时，新标题作为原生图层叠加。",
    )
    narration_direction: str | None = Field(default=None, max_length=4000)
    subject_region: NormalizedRegion | None = None
    title_safe_area: NormalizedRegion | None = None
    caption_safe_area: NormalizedRegion | None = None
    palette: list[str] = Field(default_factory=list, max_length=16)
    brand_asset_refs: list[str] = Field(default_factory=list, max_length=32)
    output: VisualOutputConstraints = VisualOutputConstraints()

    @field_validator("palette")
    @classmethod
    def _fixed_palette(cls, value: list[str]) -> list[str]:
        if any(not re.fullmatch(r"#[0-9A-Fa-f]{6}", color) for color in value):
            raise ValueError("palette entries must be fixed six-digit hex colors")
        return value

    # Server-owned review inputs, excluded from the pixel-generation identity and model schema.
    _generation_scope: tuple[UUID, UUID] | None = PrivateAttr(default=None)
    _review_basis: dict[str, Any] | None = PrivateAttr(default=None)

    def review_version(self) -> str:
        version = image_reviewer_version(self.source.kind)
        if self._review_basis is None:
            return version
        return f"{version}-{canonical_json_hash(self._review_basis)}"

    def request_digest(self) -> str:
        request = self.model_dump(mode="json")
        if self._generation_scope:
            request["generation_scope"] = [str(value) for value in self._generation_scope]
        return canonical_json_hash(request)


SceneId = Annotated[str, Field(min_length=1, max_length=64)]


class VisualAssetSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_ref: VideoDraftRef
    scene_ids: list[SceneId] = Field(
        min_length=1, max_length=VISUAL_ASSET_MAX_PER_CALL
    )
    review_existing: bool = False

    @model_validator(mode="after")
    def _unique_scenes(self):
        if self.scene_ids is not None and len(self.scene_ids) != len(set(self.scene_ids)):
            raise ValueError("scene_ids must be unique")
        return self


def _validated_spec(spec: SceneAssetSpec) -> SceneAssetSpec:
    for color in spec.palette:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
            raise VisualAssetError("palette entries must be fixed six-digit hex colors")
    if isinstance(spec.source, MiniMaxImageSource):
        if spec.output.width * 9 != spec.output.height * 16:
            raise VisualAssetError("MiniMax image-01 currently supports only a 16:9 output")
    return spec


def scene_asset_specs(content: dict[str, Any], values: Any) -> list[SceneAssetSpec]:
    if not isinstance(values, list) or not values:
        raise VisualAssetError("scene_assets must be a non-empty bounded batch")
    if len(values) > VISUAL_ASSET_MAX_PER_CALL:
        raise VisualAssetError("scene asset batch exceeds the deployment policy")
    specs = [
        _validated_spec(
            item if isinstance(item, SceneAssetSpec) else SceneAssetSpec.model_validate(item)
        )
        for item in values
    ]
    scene_ids = {str(scene.get("scene_id")) for scene in content.get("scenes") or []}
    ids = [item.scene_id for item in specs]
    if len(ids) != len(set(ids)):
        raise VisualAssetError("scene_assets contains a duplicate scene_id")
    missing = [item for item in ids if item not in scene_ids]
    if missing:
        raise VisualAssetError(
            f"scene_assets reference scenes outside the current draft: {missing}"
        )
    return specs


def merge_scene_assets(
    design: dict[str, Any], content: dict[str, Any], values: Any
) -> list[dict[str, Any]]:
    updates = scene_asset_specs(content, values)
    merged = {
        item["scene_id"]: item
        for item in design.get("scene_assets") or []
        if isinstance(item, dict) and item.get("scene_id")
    }
    for spec in updates:
        merged[spec.scene_id] = spec.model_dump(mode="json")
    scene_order = [str(scene.get("scene_id")) for scene in content.get("scenes") or []]
    return [merged[scene_id] for scene_id in scene_order if scene_id in merged]


def current_scene_assets(arguments: dict[str, Any]) -> list[SceneAssetSpec]:
    content = arguments.get("content") or {}
    values = (arguments.get("design") or {}).get("scene_assets") or []
    if not values:
        return []
    specs = scene_asset_specs(content, values)
    words = (arguments.get("design") or {}).get("review_user_words")
    if words is not None:
        roles = {s["scene_id"]: s.get("intent") for s in content.get("scenes", [])}
        for spec in specs:
            spec._review_basis = {"user_words": words, "scene_roles": roles}
    return specs


def select_scene_assets(arguments: dict[str, Any], scene_ids: list[str]) -> list[SceneAssetSpec]:
    available = {spec.scene_id: spec for spec in current_scene_assets(arguments)}
    if len(scene_ids) != len(set(scene_ids)):
        raise VisualAssetError("scene_ids must be unique")
    missing = [scene_id for scene_id in scene_ids if scene_id not in available]
    if missing:
        raise VisualAssetError(f"No current SceneAssetSpec for scene_ids: {', '.join(missing)}")
    return [available[scene_id] for scene_id in scene_ids]


def request_key(owner_id: UUID, project_id: UUID, request_digest: str) -> str:
    return f"{_MANIFEST_PREFIX}/{owner_id}/{project_id}/{request_digest}.json"


def batched_scene_assets(specs: list[SceneAssetSpec], size: int = VISUAL_ASSET_BATCH_SIZE):
    if size <= 0 or size > VISUAL_ASSET_BATCH_SIZE:
        raise ValueError("invalid visual asset batch size")
    for index in range(0, len(specs), size):
        yield specs[index : index + size]


def sanitize_svg_program(program: str, output: VisualOutputConstraints) -> tuple[bytes, str, str]:
    raw = program.encode("utf-8")
    if len(raw) > _MAX_SVG_BYTES or re.search(r"<!DOCTYPE|<!ENTITY", program, re.I):
        raise InvalidSVGProgramError("SVG program exceeds its budget or contains a declaration")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise InvalidSVGProgramError(f"SVG is not well formed: {exc}") from exc
    allowed = {
        "svg",
        "g",
        "rect",
        "circle",
        "ellipse",
        "line",
        "polyline",
        "polygon",
        "path",
        "text",
        "tspan",
        "defs",
        "linearGradient",
        "radialGradient",
        "stop",
    }
    elements = list(root.iter())
    if _local_name(root.tag) != "svg" or len(elements) > _MAX_SVG_ELEMENTS:
        raise InvalidSVGProgramError("SVG root or element budget is invalid")
    for element in elements:
        name = _local_name(element.tag)
        if name not in allowed or element.tag not in {name, f"{{{_SVG_NAMESPACE}}}{name}"}:
            raise InvalidSVGProgramError(f"SVG element {element.tag!r} is not allowed")
        # Unqualified SVG is accepted at input, but imported DOM nodes must carry the SVG namespace.
        element.tag = f"{{{_SVG_NAMESPACE}}}{name}"
        for key, value in list(element.attrib.items()):
            attribute = _local_name(key).lower()
            if key.startswith("{") and key not in {
                f"{{{_XML_NAMESPACE}}}space", f"{{{_XML_NAMESPACE}}}lang"
            }:
                raise InvalidSVGProgramError(f"SVG attribute {key!r} is not allowed")
            if attribute.startswith("on") or attribute in {"href", "src", "style"}:
                raise InvalidSVGProgramError(f"SVG attribute {attribute!r} is not allowed")
            if re.search(
                r"(?:https?:|data:|file:|javascript:|url\s*\(|@import|expression\s*\()", value, re.I
            ):
                raise InvalidSVGProgramError(
                    "SVG external references and executable CSS are forbidden"
                )
            if len(value) > 100_000:
                raise InvalidSVGProgramError("SVG attribute exceeds its resource budget")
        if name in {"text", "tspan"}:
            element.set("font-family", "VisualAssetFixed")
    root.set("width", str(output.width))
    root.set("height", str(output.height))
    if not root.get("viewBox"):
        root.set("viewBox", f"0 0 {output.width} {output.height}")
    root.set("font-family", "VisualAssetFixed")
    for element in elements:
        element.attrib.update(dict(sorted(element.attrib.items())))
    sanitized = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return sanitized, hashlib.sha256(raw).hexdigest(), hashlib.sha256(sanitized).hexdigest()


def preflight_scene_svgs(specs: list[SceneAssetSpec]) -> None:
    """Validate all selected SVG sources before quoting or running any provider."""
    errors = []
    for spec in specs:
        if isinstance(spec.source, ControlledSVGSource):
            try:
                sanitize_svg_program(spec.source.program, spec.output)
            except InvalidSVGProgramError as exc:
                errors.append(f"Scene {spec.scene_id}: {exc}")
    if errors:
        raise InvalidSVGProgramError("; ".join(errors))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


async def rasterize_svg(
    svg: bytes, output: VisualOutputConstraints
) -> tuple[bytes, dict[str, Any]]:
    from playwright.async_api import async_playwright

    from app.tools.research.capture import resolve_chrome_path

    chrome = resolve_chrome_path()
    if chrome is None:
        raise VisualAssetError("controlled SVG requires the deployment's configured Chrome")
    fonts = {weight: path.read_bytes() for weight, path in _FONT_FILES.items()}
    font_parts = []
    for weight, data in fonts.items():
        encoded = base64.b64encode(data).decode("ascii")
        font_parts.append(
            "@font-face{font-family:VisualAssetFixed;font-style:normal;"
            f"font-weight:{700 if weight == 'bold' else 400};"
            f"src:url(data:font/otf;base64,{encoded})"
            " format('opentype');}"
        )
    font_css = "".join(font_parts)
    html = (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        + font_css
        + "html,body{margin:0;padding:0;overflow:hidden;background:transparent}"
        "</style></head><body></body></html>"
    )

    async def execute() -> tuple[bytes, str, list[dict[str, Any]]]:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=chrome,
                headless=True,
                args=["--disable-gpu", "--hide-scrollbars", "--mute-audio"],
            )
            try:
                page = await browser.new_page(
                    viewport={"width": output.width, "height": output.height},
                    device_scale_factor=1,
                )
                await page.route("**/*", lambda route: route.abort())
                await page.set_content(html, wait_until="load", timeout=_SVG_TIMEOUT_SECONDS * 1000)
                # Parse as XML before inserting into HTML. The HTML parser does not
                # recognize XML namespace prefixes emitted by ElementTree.
                rendered = await page.evaluate(
                    """async ({ source, width, height }) => {
                        const parsed = new DOMParser().parseFromString(source, "image/svg+xml");
                        const root = parsed.documentElement;
                        if (root.localName !== "svg" || root.namespaceURI !== "http://www.w3.org/2000/svg"
                            || parsed.querySelector("parsererror")) {
                            return false;
                        }
                        const svg = document.importNode(root, true);
                        if (!(svg instanceof SVGSVGElement)) return false;
                        svg.style.display = "block";
                        document.body.appendChild(svg);
                        await document.fonts.ready;
                        const bounds = svg.getBoundingClientRect();
                        if (bounds.x !== 0 || bounds.y !== 0
                            || bounds.width !== width || bounds.height !== height) {
                            return false;
                        }
                        return Array.from(svg.getElementsByTagNameNS(root.namespaceURI, "text"))
                            .slice(0, 128).map(node => {
                                const box = node.getBoundingClientRect();
                                return {
                                    text: node.textContent.slice(0, 300),
                                    left: box.left, top: box.top,
                                    right: box.right, bottom: box.bottom
                                };
                            });
                    }""",
                    {"source": svg.decode("utf-8"), "width": output.width, "height": output.height},
                )
                if rendered is False:
                    raise VisualAssetError("controlled SVG did not mount as a native SVG viewport")
                png = await page.screenshot(type="png", animations="disabled")
                return png, browser.version, rendered
            finally:
                await browser.close()

    try:
        png, browser_version, text_bounds = await asyncio.wait_for(execute(), _SVG_TIMEOUT_SECONDS)
    except VisualAssetError:
        raise
    except (TimeoutError, OSError, ValueError) as exc:
        raise VisualAssetError(
            f"controlled SVG rasterization failed: {type(exc).__name__}"
        ) from exc
    diagnostics = {
        "runner_version": VISUAL_ASSET_RUNNER_VERSION,
        "browser": "chromium",
        "browser_version": browser_version,
        "native_svg_viewport_verified": True,
        "text_bounds": text_bounds,
        "viewport": {"width": output.width, "height": output.height, "device_scale_factor": 1},
        "timeout_seconds": _SVG_TIMEOUT_SECONDS,
        "network": "disabled",
        "fonts": [
            {"weight": weight, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
            for weight, data in sorted(fonts.items())
        ],
    }
    return png, diagnostics


def _fixed_png(
    data: bytes, *, fit: VisualOutputConstraints | None = None,
) -> tuple[bytes, int, int, str]:
    """Return the prepared PNG together with the input dimensions and digest."""
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            width, height = source.size
            source_digest = hashlib.sha256(data).hexdigest()
            transparent = "A" in source.getbands() or (fit is not None and "transparency" in source.info)
            image = source.convert("RGBA" if transparent else "RGB")
            if fit is not None and source.size != (fit.width, fit.height):
                image = ImageOps.pad(
                    image.convert("RGBA"), (fit.width, fit.height),
                    method=Image.Resampling.LANCZOS, color=(0, 0, 0, 0),
                )
        target = io.BytesIO()
        image.save(target, format="PNG")
        return target.getvalue(), width, height, source_digest
    except (OSError, ValueError) as exc:
        raise VisualAssetError(f"provider returned invalid image bytes: {exc}") from exc


async def _save_immutable(key: str, data: bytes, content_type: str) -> None:
    if await storage.exists(key):
        existing = await storage.read(key)
        if hashlib.sha256(existing).hexdigest() != hashlib.sha256(data).hexdigest():
            raise VisualAssetError("immutable visual source identity collision")
        return
    await storage.save(key, data, content_type=content_type)


async def _save_manifest(key: str, value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    if not await storage.exists(key):
        await storage.save(key, encoded, content_type="application/json")
        return
    existing_bytes = await storage.read(key)
    existing = json.loads(existing_bytes)
    if existing == value:
        return
    if (
        isinstance(existing, dict)
        and existing.get("request_digest") == value.get("request_digest")
        and existing.get("scene_id") == value.get("scene_id")
        and (
            (existing.get("state") == "submitted" and value.get("state") == "fixed")
            or (existing.get("state") == "fixed" and value.get("state") == "fixed")
        )
    ):
        await storage.save(key, encoded, content_type="application/json")
        return
    raise VisualAssetError("fixed visual asset manifest cannot be overwritten")


def versioned_request_key(owner_id: UUID, project_id: UUID, spec: SceneAssetSpec) -> str:
    version = spec.review_version()
    if isinstance(spec.source, ControlledSVGSource):
        version = f"{VISUAL_ASSET_RUNNER_VERSION}/{version}"
    return (
        f"{_MANIFEST_PREFIX}/{owner_id}/{project_id}/{spec.request_digest()}/reviews/{version}.json"
    )


async def _read_manifest(key: str) -> dict[str, Any] | None:
    if not await storage.exists(key):
        return None
    try:
        value = json.loads(await storage.read(key))
    except (ValueError, json.JSONDecodeError) as exc:
        raise VisualAssetError(f"visual asset manifest is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise VisualAssetError("visual asset manifest is malformed")
    if value.get("state") == "submitted":
        return value
    if value.get("state") != "fixed" or not value.get("snapshot"):
        raise VisualAssetError("visual asset manifest has no fixed snapshot")
    return value


def _review_retry_key(owner_id: UUID, project_id: UUID, manifest: dict[str, Any]) -> str:
    return (
        f"{_MANIFEST_PREFIX}/{owner_id}/{project_id}/{manifest['request_digest']}/"
        f"review-retries/{manifest['content_review_ref']['digest']}.json"
    )


async def fixed_visual_asset_manifest(
    *, owner_id: UUID, project_id: UUID, spec: SceneAssetSpec
) -> dict[str, Any] | None:
    request_digest = spec.request_digest()
    manifest = await _read_manifest(request_key(owner_id, project_id, request_digest))
    if manifest is None:
        return None
    if (
        manifest.get("request_digest") != request_digest
        or manifest.get("scene_id") != spec.scene_id
    ):
        raise VisualAssetError("visual asset cache identity mismatch")
    if manifest.get("state") == "submitted":
        await _recover_submitted_image(spec)
        return None  # Worker still needs to fix the scene-specific PNG and review.
    if (
        isinstance(spec.source, ControlledSVGSource)
        and (manifest.get("provenance") or {}).get("runner_version") != VISUAL_ASSET_RUNNER_VERSION
    ):
        return None
    if isinstance(spec.source, ExistingImageSource):
        media = manifest.get("media") or {}
        if (media.get("width"), media.get("height")) != (spec.output.width, spec.output.height):
            return None
    return manifest


async def cached_visual_asset(
    *, owner_id: UUID, project_id: UUID, spec: SceneAssetSpec
) -> dict[str, Any] | None:
    manifest = await fixed_visual_asset_manifest(
        owner_id=owner_id, project_id=project_id, spec=spec
    )
    if manifest is None:
        return None
    media = manifest["media"]
    data = await storage.read(media["storage_key"])
    if hashlib.sha256(data).hexdigest() != media["digest"]:
        raise VisualAssetError("fixed visual asset bytes do not match their digest")
    analysis = await read_report(manifest["analysis_ref"])
    review = await read_report(manifest["content_review_ref"])
    if review.get("reviewer_version") != spec.review_version():
        return None
    result = {**manifest, "cache_hit": True, "analysis": analysis, "content_review": review}
    if review["status"] == "unavailable":
        retry_key = _review_retry_key(owner_id, project_id, manifest)
        if await storage.exists(retry_key):
            ref = json.loads(await storage.read(retry_key))
            repeated = await read_report(ref)
            if any(
                repeated.get(field) != review.get(field)
                for field in ("source_ref", "scene_id", "request_digest",
                              "analysis_report_ref", "reviewer_version")
            ):
                raise VisualAssetError("replacement content review identity mismatch")
            result.update(
                content_review_ref=ref,
                content_review=repeated,
                review_retry_of=manifest["content_review_ref"],
            )
    return result


async def review_fixed_visual_asset(
    *,
    owner_id: UUID,
    project_id: UUID,
    spec: SceneAssetSpec,
    reviewer: Any = None,
) -> dict[str, Any]:
    result = await cached_visual_asset(owner_id=owner_id, project_id=project_id, spec=spec)
    if result is None:
        raise VisualAssetError(f"Scene {spec.scene_id} has no fixed PNG to review")
    if result.get("review_retry_of") or result["content_review"]["status"] != "unavailable":
        return result

    # The report is appended against the same immutable PNG and analysis.
    # Project Runs are serialized, and a completed retry is reused on resume.
    data = await storage.read(result["media"]["storage_key"])
    if hashlib.sha256(data).hexdigest() != result["media"]["digest"]:
        raise VisualAssetError("fixed visual asset bytes do not match their digest")
    analysis = MediaAnalysisReport.model_validate(result["analysis"])
    review = await review_image_content(
        data, scene_asset=spec, analysis=analysis,
        analysis_ref=result["analysis_ref"], reviewer=reviewer,
    )
    ref = await store_content_review(review)
    await _save_immutable(
        _review_retry_key(owner_id, project_id, result),
        json.dumps(ref, sort_keys=True).encode(),
        "application/json",
    )
    return {
        **result,
        "review_retry_of": result["content_review_ref"],
        "content_review_ref": ref,
        "content_review": review.model_dump(mode="json"),
    }


async def _existing_image(spec: SceneAssetSpec, owner_id: UUID) -> tuple[bytes, dict[str, Any]]:
    assert isinstance(spec.source, ExistingImageSource)
    async with AsyncSessionLocal() as db:
        snapshot = await db.get(SourceSnapshot, spec.source.snapshot_id)
    if (
        snapshot is None
        or snapshot.owner_id != owner_id
        or snapshot.kind != "image"
        or snapshot.digest != spec.source.snapshot_digest
    ):
        raise VisualAssetError(
            "existing image SourceSnapshot is inaccessible or its digest changed"
        )
    data = await storage.read(snapshot.storage_key)
    if hashlib.sha256(data).hexdigest() != snapshot.digest:
        raise VisualAssetError("existing image bytes do not match their snapshot digest")
    return data, {
        "kind": "existing_image",
        "snapshot_id": str(snapshot.id),
        "snapshot_digest": snapshot.digest,
    }


def _minimax_clip(spec: SceneAssetSpec) -> Clip:
    assert isinstance(spec.source, MiniMaxImageSource)
    obj = GeneratorObject(
        kind="generator",
        object_id=f"obj_{spec.request_digest()[:24]}",
        producer="image-generation",
        prompt=spec.source.prompt,
        provider="minimax",
        model="image-01",
        output=GeneratedImageOutput(),
        layout=LayoutBox(x=0, y=0, width=spec.output.width, height=spec.output.height),
    )
    return Clip(
        clip_id=f"clp_{spec.request_digest()[:24]}",
        range=TimeRange(start=0, end=1),
        object=obj,
    )


async def has_fixed_visual_source(
    *, owner_id: UUID, project_id: UUID, spec: SceneAssetSpec
) -> bool:
    from app.tools.video.generated_images import find_fixed_generated_image

    fixed = await fixed_visual_asset_manifest(owner_id=owner_id, project_id=project_id, spec=spec)
    return fixed is not None or (
        isinstance(spec.source, MiniMaxImageSource)
        and await find_fixed_generated_image(_minimax_clip(spec), scope=spec._generation_scope) is not None
    )


async def _recover_submitted_image(spec: SceneAssetSpec) -> dict[str, Any]:
    from app.tools.video.generated_images import GeneratedImageError, find_fixed_generated_image

    if isinstance(spec.source, MiniMaxImageSource):
        try:
            fixed = await find_fixed_generated_image(_minimax_clip(spec), scope=spec._generation_scope)
        except GeneratedImageError as exc:
            raise VisualAssetOutcomeUnknownError(
                "The earlier image request lacks a verified fixed result; no resubmission."
            ) from exc
        if fixed is not None:
            return fixed
    raise VisualAssetOutcomeUnknownError(
        "The earlier image request has no fixed result; it will not be resubmitted."
    )


async def _minimax_image(
    spec: SceneAssetSpec, *, execution_id: str, fixed: dict[str, Any] | None = None,
) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    from app.metering import record_media_usage
    from app.tools.video.generated_images import ensure_generated_image_clip

    reused = fixed is not None

    def on_reuse(value: bool):
        nonlocal reused
        reused = value

    try:
        generated = fixed or await ensure_generated_image_clip(
            _minimax_clip(spec), execution_id=execution_id, on_reuse=on_reuse,
            **({"scope": spec._generation_scope} if spec._generation_scope else {}),
        )
    except Exception as exc:
        raise VisualAssetOutcomeUnknownError(
            "MiniMax did not return a verified fixed result; no automatic resubmission."
        ) from exc
    usage = (generated.get("usage") or {}) if generated.get("execution_id") == execution_id else {}
    if reused and usage:
        await record_media_usage(usage)
    source = generated["media"]
    original = await storage.read(source["storage_key"])
    if hashlib.sha256(original).hexdigest() != source["digest"]:
        raise VisualAssetError("MiniMax fixed media differs from its execution manifest")
    png, width, height, source_digest = _fixed_png(original)
    return (
        png,
        {
            "kind": "minimax_image",
            "provider": "minimax",
            "model": "image-01",
            "program_digest": generated["program_digest"],
            "request": generated["request"],
            "provider_request": generated["provider_request"],
            "provider_media_digest": source_digest,
            "provider_dimensions": {"width": width, "height": height},
        },
        usage,
    )


async def prepare_visual_asset(
    *,
    owner_id: UUID,
    project_id: UUID,
    spec: SceneAssetSpec,
    draft_ref: VideoDraftRef | None,
    execution_id: str,
    media_usage: dict | None = None,
    content_attempt: int = 1,
    step_attempt: int = 1,
    rasterizer: Any = None,
    reviewer: Any = None,
) -> dict[str, Any]:
    spec = _validated_spec(spec)
    cached = await cached_visual_asset(owner_id=owner_id, project_id=project_id, spec=spec)
    if cached is not None:
        if (cached.get("execution") or {}).get("media_job_id" if media_usage is not None else "run_id") == execution_id:
            usage = cached.get("usage") or {}
            if usage:
                from app.metering import record_media_usage

                await record_media_usage(usage)
            return {**cached, "cache_hit": False}
        return cached
    key = request_key(owner_id, project_id, spec.request_digest())
    legacy = await fixed_visual_asset_manifest(
        owner_id=owner_id, project_id=project_id, spec=spec
    )
    usage: dict[str, Any] = {}
    if legacy is not None:
        media = legacy["media"]
        png = await storage.read(media["storage_key"])
        if hashlib.sha256(png).hexdigest() != media["digest"]:
            raise VisualAssetError("fixed visual asset bytes do not match their digest")
        provenance = legacy["provenance"]
        diagnostics = {
            "recovered_from": legacy["execution"],
            "reason": "reviewer_version_changed",
            "text_bounds": (legacy.get("diagnostics") or {}).get("text_bounds"),
        }
    elif isinstance(spec.source, ExistingImageSource):
        png, provenance = await _existing_image(spec, owner_id)
        png, width, height, _ = _fixed_png(png, fit=spec.output)
        diagnostics = {
            "source": "existing_fixed_image", "fit": "contain",
            "source_dimensions": {"width": width, "height": height},
        }
    elif isinstance(spec.source, ControlledSVGSource):
        svg, program_digest, svg_digest = sanitize_svg_program(spec.source.program, spec.output)
        await _save_immutable(
            f"visual-asset-programs/{program_digest}.svg",
            spec.source.program.encode("utf-8"),
            "image/svg+xml",
        )
        await _save_immutable(f"visual-asset-svg/{svg_digest}.svg", svg, "image/svg+xml")
        rasterize = rasterizer or rasterize_svg
        png, diagnostics = await rasterize(svg, spec.output)
        png, width, height, _ = _fixed_png(png)
        if (width, height) != (spec.output.width, spec.output.height):
            raise VisualAssetError("controlled SVG PNG dimensions do not match its viewport")
        provenance = {
            "kind": "controlled_svg",
            "program_digest": program_digest,
            "program_storage_key": f"visual-asset-programs/{program_digest}.svg",
            "svg_digest": svg_digest,
            "svg_storage_key": f"visual-asset-svg/{svg_digest}.svg",
            "runner_version": VISUAL_ASSET_RUNNER_VERSION,
        }
    else:
        marker = {
            "schema_version": 1,
            "state": "submitted",
            "scene_id": spec.scene_id,
            "request_digest": spec.request_digest(),
            "execution_id": execution_id,
        }
        prior = await _read_manifest(key)
        fixed = None
        if prior is not None and prior.get("state") == "submitted":
            fixed = await _recover_submitted_image(spec)
        else:
            await _save_immutable(
                key,
                json.dumps(marker, sort_keys=True, separators=(",", ":")).encode(),
                "application/json",
            )
        png, provenance, usage = await _minimax_image(
            spec, execution_id=execution_id, fixed=fixed,
        )
        diagnostics = {"provider_manifest": "video-generated-images", "submitted_marker": True}
        provider_size = provenance["provider_dimensions"]
        actual_size = (int(provider_size["width"]), int(provider_size["height"]))
        requested_size = (spec.output.width, spec.output.height)
        if actual_size != requested_size:
            with Image.open(io.BytesIO(png)) as provider_image:
                resized = provider_image.resize(requested_size, Image.Resampling.LANCZOS)
                output = io.BytesIO()
                resized.save(output, format="PNG")
                png = output.getvalue()
            diagnostics["deterministic_resize"] = {
                "from": actual_size,
                "to": requested_size,
                "filter": "Pillow.LANCZOS",
            }
    media_key, media_digest = await store_source_bytes(png, ".png", "image/png")
    revision = spec.review_version()
    if isinstance(spec.source, ControlledSVGSource):
        revision = f"{VISUAL_ASSET_RUNNER_VERSION}:{revision}"
    identity_key = f"visual-asset:{spec.request_digest()}:{revision}"
    identity = uuid5(NAMESPACE_URL, f"{project_id}:{identity_key}" if media_usage is not None else identity_key)
    snapshot_id = source_snapshot_id(owner_id, identity, "image", media_digest)
    analysis = analyze_image_bytes(
        png, snapshot_id=str(snapshot_id), source_digest=media_digest,
        svg_text_bounds=diagnostics.get("text_bounds"),
        caption_safe_area=(
            spec.caption_safe_area.model_dump(mode="json") if spec.caption_safe_area else None
        ),
    )
    analysis_ref = await store_media_analysis(analysis)
    review = await review_image_content(
        png,
        scene_asset=spec,
        analysis=analysis,
        analysis_ref=analysis_ref,
        reviewer=reviewer,
    )
    review_ref = await store_content_review(review)
    snapshot_meta = {
        "origin": "visual_asset",
        "width": analysis.media_facts["dimensions"]["width"],
        "height": analysis.media_facts["dimensions"]["height"],
        "mime_type": "image/png",
        "visual_asset": {
            "schema_version": VISUAL_ASSET_SCHEMA_VERSION,
            "scene_id": spec.scene_id,
            "request_digest": spec.request_digest(),
            "provenance": provenance,
            "execution_diagnostics": diagnostics,
            "analysis_ref": analysis_ref,
            "content_review_ref": review_ref,
        },
    }
    from app.editing.sources import register_snapshot

    async with AsyncSessionLocal() as db:
        snapshot = await register_snapshot(
            db,
            owner_id=owner_id,
            asset=None,
            origin_project_id=project_id,
            kind="image",
            storage_key=media_key,
            digest=media_digest,
            duration_ticks=None,
            captured_at=datetime.now(UTC),
            identity=identity,
            meta=snapshot_meta,
        )
        await db.commit()
    manifest = {
        "schema_version": VISUAL_ASSET_SCHEMA_VERSION,
        "state": "fixed",
        "scene_id": spec.scene_id,
        "request_digest": spec.request_digest(),
        "scene_asset": spec.model_dump(mode="json"),
        "draft_ref_at_birth": draft_ref.model_dump(mode="json") if draft_ref else None,
        "execution": {
            ("media_job_id" if media_usage is not None else "run_id"): execution_id,
            **({"metered_cost": dict(media_usage)} if media_usage is not None else {}),
            "content_attempt": content_attempt,
            "step_attempt": step_attempt,
        },
        "media": {
            "storage_key": media_key,
            "digest": media_digest,
            "width": analysis.media_facts["dimensions"]["width"],
            "height": analysis.media_facts["dimensions"]["height"],
            "mime_type": "image/png",
        },
        "snapshot": {"snapshot_id": str(snapshot.id), "digest": snapshot.digest},
        "provenance": provenance,
        "diagnostics": diagnostics,
        "analysis_ref": analysis_ref,
        "content_review_ref": review_ref,
        "reviewer_version": review.reviewer_version,
        "usage": usage,
    }
    await _save_immutable(
        versioned_request_key(owner_id, project_id, spec),
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
        "application/json",
    )
    await _save_manifest(key, manifest)
    return {
        **manifest,
        "cache_hit": legacy is not None,
        "analysis": analysis.model_dump(mode="json"),
        "content_review": review.model_dump(mode="json"),
    }


async def prepare_visual_assets(
    *,
    owner_id: UUID,
    project_id: UUID,
    specs: list[SceneAssetSpec],
    draft_ref: VideoDraftRef | None,
    execution_id: str,
    content_attempts: dict[str, int] | None = None,
    step_attempt: int = 1,
    review_existing: bool = False,
    rasterizer: Any = None,
    reviewer: Any = None,
    on_prepared: Callable[[int], Awaitable[None]] | None = None,
    on_active_scene: Callable[[int, str | None], Awaitable[None]] | None = None,
) -> VisualAssetBatch:
    results = VisualAssetBatch()
    prepared_count = 0

    async def prepare_scene(spec: SceneAssetSpec) -> dict[str, Any]:
        nonlocal prepared_count
        if review_existing:
            asset = await review_fixed_visual_asset(
                owner_id=owner_id, project_id=project_id, spec=spec, reviewer=reviewer
            )
        else:
            asset = await prepare_visual_asset(
                owner_id=owner_id, project_id=project_id, spec=spec, draft_ref=draft_ref,
                execution_id=execution_id, content_attempt=(content_attempts or {}).get(spec.scene_id, 1),
                step_attempt=step_attempt, rasterizer=rasterizer, reviewer=reviewer,
            )
        prepared_count += 1
        if on_prepared is not None:
            await on_prepared(prepared_count)
        return asset

    completed = 0
    progress_lock = asyncio.Lock()

    async def track_scene(spec: SceneAssetSpec, active: list[str]) -> dict[str, Any]:
        nonlocal completed
        try:
            return await prepare_scene(spec)
        finally:
            async with progress_lock:
                active.remove(spec.scene_id)
                completed += 1
                if on_active_scene is not None:
                    await on_active_scene(completed, next(iter(active), None))

    for batch in batched_scene_assets(specs):
        active = [spec.scene_id for spec in batch]
        if on_active_scene is not None:
            await on_active_scene(completed, active[0])
        settled = await asyncio.gather(*(track_scene(spec, active) for spec in batch), return_exceptions=True)
        for spec, item in zip(batch, settled, strict=True):
            if isinstance(item, dict):
                results.assets.append(item)
                continue
            if not isinstance(item, Exception):
                raise item  # cancellation must not settle the run
            code = "execution_error"
            if isinstance(item, VisualAssetOutcomeUnknownError):
                code = "outcome_unknown"
            elif isinstance(item, InvalidSVGProgramError):
                code = "invalid_svg"
            detail = str(item)[:400] if isinstance(item, VisualAssetError) else type(item).__name__
            results.failures.append({
                "scene_id": spec.scene_id,
                "request_digest": spec.request_digest(),
                "execution_id": execution_id,
                "code": code,
                "detail": detail,
            })
    return results


async def visual_asset_result_images(results: list[dict[str, Any]]) -> list[Any]:
    images = []
    for result in results:
        media = result["media"]
        data = await storage.read(media["storage_key"])
        if hashlib.sha256(data).hexdigest() != media["digest"]:
            raise VisualAssetError("result media differs from its fixed digest")
        images.append(
            image_media_input(
                data,
                caption=(
                    f"Actual fixed PNG for scene {result['scene_id']}; snapshot "
                    f"{result['snapshot']['snapshot_id']}; digest {media['digest']}"
                ),
            )
        )
    return images


__all__ = [
    "ControlledSVGSource",
    "ExistingImageSource",
    "MiniMaxImageSource",
    "NormalizedRegion",
    "SceneAssetSpec",
    "VISUAL_ASSET_BATCH_SIZE",
    "VISUAL_ASSET_MAX_PER_CALL",
    "VisualAssetError",
    "VisualAssetOutcomeUnknownError",
    "VisualOutputConstraints",
    "batched_scene_assets",
    "cached_visual_asset",
    "current_scene_assets",
    "merge_scene_assets",
    "prepare_visual_asset",
    "prepare_visual_assets",
    "rasterize_svg",
    "sanitize_svg_program",
    "scene_asset_specs",
    "visual_asset_result_images",
]
