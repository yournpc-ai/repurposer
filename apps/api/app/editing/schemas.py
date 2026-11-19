"""CompositionVersion content schemas (VIDEO_PROJECT §2–§6).

The four JSONB columns of a ``composition_versions`` row (settings / sources
/ scenes / timeline) serialize from ``CompositionContent`` — this module is
the single shape law for what a version may carry. Current scope: Text /
Shape / Image / Web / Video / Audio / Speech objects over visual + audio
tracks; centered crossfades connect adjacent opaque fixed-media clips.
Pending Speech carries its reviewed
script and voice, never fabricated source media.

Three time domains stay name-separated (§6.1):
- Output time:  ``Scene.range`` / ``Clip.range`` — ticks at ``settings.timebase``.
- Source time:  ``ClipSource.source_range`` — ticks at ``timing.SOURCE_TIMEBASE``.
- Clip-local:   ``Keyframe.at`` — ticks at ``settings.timebase``, zero at the
  clip's own start; it travels when the clip moves.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import TYPE_CHECKING, Annotated, Any, Literal, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from app.editing.fonts import FONT_ID, FONT_SET_DIGEST, LAYOUT_VERSION, SEGMENTATION_VERSION
from app.editing.timing import DEFAULT_TIMEBASE

if TYPE_CHECKING:
    from app.models.schemas import CreativeState

SCHEMA_VERSION = 1

_ID = Field(min_length=1, max_length=64)
_HEX_COLOR = Field(pattern=r"^#[0-9a-fA-F]{6}$")
_OPACITY = Field(
    default=1.0, ge=0, le=1,
    description="归一化透明度，范围 [0, 1]。0 为透明，1 为不透明，不使用百分比。",
)


def _list_wire(value: Any) -> Any:
    """Absorb empty/singleton/item-wrapped list dialect before element validation."""
    if value is None or value == "" or value == {}:
        return []
    if isinstance(value, dict) and set(value) == {"item"}:
        return _list_wire(value["item"])
    if isinstance(value, (dict, str)):
        return [value]
    return value


class Fps(BaseModel):
    """用有理数表示的帧率。当前为 30/1，也可表示 30000/1001。"""

    model_config = ConfigDict(extra="forbid")

    num: int = Field(default=30, gt=0)
    den: int = Field(default=1, gt=0)


class VersionSettings(BaseModel):
    """单个版本的制作设置快照（§2.1 settings）。"""

    model_config = ConfigDict(extra="forbid")

    width: int = Field(gt=0, description="画布宽度，单位为像素。")
    height: int = Field(gt=0, description="画布高度，单位为像素。")
    fps: Fps = Fps()
    timebase: int = Field(default=DEFAULT_TIMEBASE, gt=0, description="输出及片段局部时钟的每秒刻度数。相关时间均为整数刻度，不使用秒数或帧数。")
    sample_rate: int = Field(default=48000, gt=0)
    channels: int = Field(default=2, gt=0)
    background: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")


class TimeRange(BaseModel):
    """用整数刻度表示的左闭右开范围 [start, end)。具体字段决定采用哪种时钟，参见模块说明中的三个时间域。"""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0, description="包含起点的整数刻度。具体字段决定这是成片、源素材还是片段局部时间。不要填秒数或帧数。")
    end: int = Field(gt=0, description="不包含终点的整数刻度，与 start 的时间域和时基一致。end 必须大于 start。")

    @model_validator(mode="after")
    def _half_open(self) -> TimeRange:
        if self.end <= self.start:
            raise ValueError("range end must be after start ([start, end))")
        return self

    @property
    def duration(self) -> int:
        return self.end - self.start


class SourceBinding(BaseModel):
    """此版本绑定的一个不可变 SourceSnapshot（§2.1 sources）。绑定时写入入口从快照记录解析摘要并固定在版本内。以后刷新素材会产生新快照，不改写已有绑定。"""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID
    snapshot_digest: str = Field(min_length=64, max_length=64)


class ClipSource(BaseModel):
    """片段的媒体来源，包含一个已绑定快照和可选的源时间窗。只有音频或视频才有 source_range。图片、静态网页视图等静态来源不设源时间窗，显示时长由 Clip 自身的成片范围决定（§4.2）。"""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID
    snapshot_digest: str = Field(min_length=64, max_length=64)
    source_range: TimeRange | None = Field(default=None, description="可选，按 SOURCE_TIMEBASE 刻度表示的左闭右开源时间窗。填写源素材时间，不使用成片时间、片段局部时间或秒数。")


class LayoutBox(BaseModel):
    """布局在画布中的静态矩形框，单位为像素（§4.3）。"""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(description="左边缘在画布中的像素位置。")
    y: float = Field(description="上边缘在画布中的像素位置。")
    width: float = Field(gt=0, description="框的宽度，单位为画布像素，不使用归一化比例。")
    height: float = Field(gt=0, description="框的高度，单位为画布像素，不使用归一化比例。")


class Transform(BaseModel):
    """相对于布局框的变换，不另设第二套绝对位置（§4.3）。"""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(default=0.0, description="相对于布局框的水平偏移，单位为画布像素。")
    y: float = Field(default=0.0, description="相对于布局框的垂直偏移，单位为画布像素。")
    scale: float = Field(default=1.0, gt=0, description="正的缩放倍数。1 为原大小，2 为布局尺寸的两倍，不使用像素或百分比。")
    rotation: float = Field(default=0.0, description="绕指定原点旋转的角度，单位为度，不使用弧度。")
    origin: Literal["center", "top_left"] = "center"


class FontRef(BaseModel):
    """不可变的字体集标识，编译器负责解析到具体文件。"""

    model_config = ConfigDict(extra="forbid")

    font_id: str = FONT_ID
    digest: str = FONT_SET_DIGEST


class TextStroke(BaseModel):
    """与渲染器无关的文字描边，宽度以画布像素计。"""

    model_config = ConfigDict(extra="forbid")

    color: str = _HEX_COLOR
    width: float = Field(ge=0, le=64, description="描边宽度，单位为画布像素。")


class TextShadow(BaseModel):
    """一项结构化的文字阴影，不接受任意 CSS 阴影列表。"""

    model_config = ConfigDict(extra="forbid")

    color: str = _HEX_COLOR
    offset: tuple[float, float] = Field(description="阴影的 [x, y] 偏移，单位为画布像素。")
    blur: float = Field(ge=0, le=100, description="阴影模糊半径，单位为画布像素。")


class TextStyle(BaseModel):
    """使用封闭的文字样式集合，不接受自由 CSS（§11.1）。"""

    model_config = ConfigDict(extra="forbid")

    font_size: int = Field(gt=0, le=400, description="字号，单位为画布像素。")
    color: str = _HEX_COLOR
    background: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    weight: Literal[400, 500, 600, 700, 800, 900] = 600
    align: Literal["left", "center", "right"] = "left"
    line_height: float = Field(default=1.2, gt=0, description="相对字号的行高倍数，不使用像素。")
    letter_spacing: float = Field(
        default=0.0, ge=-0.2, le=0.5,
        description="相对字号的字间距，单位为 em，有效范围 [-0.2, 0.5]。不要填像素或未经换算的像素数。",
    )
    stroke: TextStroke | None = None
    shadow: TextShadow | None = None
    font: FontRef = FontRef()

    @field_validator("weight", mode="before")
    @classmethod
    def _weight_wire(cls, value: Any) -> Any:
        if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
            return int(value.strip())
        return value


class CaptionDerivation(BaseModel):
    """字幕与已审阅 SpeechObject 文本的可编辑关联。实际提示点时间来自执行结果，不修改版本。derived 字幕随 Speech 编辑更新，independent 保留用户手改文字，直至显式同步重新建立关联。源音频对齐的字幕还固定 READY 对齐结果及其语义内容摘要。"""

    model_config = ConfigDict(extra="forbid")

    speech_object_id: str = _ID
    source_text_digest: str = Field(min_length=64, max_length=64)
    alignment: Literal["minimax-t2a-v2-sentence-v1", "faster-whisper-script-v1"]
    state: Literal["derived", "independent"] = "derived"
    narration_alignment_id: UUID | None = None
    narration_content_digest: str | None = Field(default=None, min_length=64, max_length=64)
    sentence_id: str | None = Field(default=None, min_length=1, max_length=64)
    text_start: int | None = Field(default=None, ge=0)
    text_end: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _phrase_span(self) -> CaptionDerivation:
        if (self.text_start is None) != (self.text_end is None):
            raise ValueError("caption phrase text_start/text_end must arrive together")
        if self.text_start is not None and (
            self.sentence_id is None or self.text_end is None or self.text_end <= self.text_start
        ):
            raise ValueError("a caption phrase needs its sentence and a non-empty text range")
        return self


class SourceCaptionDerivation(BaseModel):
    """从固定的 ASR 或旁白对齐结果取得的原生字幕文字和时序。"""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID
    snapshot_digest: str = Field(min_length=64, max_length=64)
    sentence_id: str = _ID
    source_range: TimeRange
    source_text_digest: str = Field(min_length=64, max_length=64)
    alignment: Literal[
        "faster-whisper-source-v1",
        "faster-whisper-script-v1",
        "minimax-t2a-v2-sentence-v1",
    ] = "faster-whisper-source-v1"
    state: Literal["derived", "independent"] = "derived"
    narration_alignment_id: UUID | None = None
    narration_content_digest: str | None = Field(default=None, min_length=64, max_length=64)


def speech_text_digest(text: str) -> str:
    """Exact reviewed-text identity (whitespace is content, not normalized away)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TextObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["text"]
    object_id: str = _ID
    text: str = Field(min_length=1)
    layout: LayoutBox
    style: TextStyle
    transform: Transform = Transform()
    opacity: float = _OPACITY
    segmentation_version: str = SEGMENTATION_VERSION
    layout_version: str = LAYOUT_VERSION
    caption: CaptionDerivation | SourceCaptionDerivation | None = None


class ImageObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["image"]
    object_id: str = _ID
    layout: LayoutBox
    fit: Literal["cover", "contain"] = "cover"
    transform: Transform = Transform()
    opacity: float = _OPACITY


class WebObject(BaseModel):
    """不可变网页快照的一个静态视图。运镜与其他视觉对象采用相同的变换动画，不为视图编造源时间窗。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["web"]
    object_id: str = _ID
    view_id: str = _ID
    layout: LayoutBox
    fit: Literal["cover", "contain"] = "cover"
    transform: Transform = Transform()
    opacity: float = _OPACITY


class VideoObject(BaseModel):
    """一个真实视频片段及其同步原声。画面和原声共用此 Clip 的源和成片时间窗，静音不会增删第二个音频片段。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["video"]
    object_id: str = _ID
    layout: LayoutBox
    fit: Literal["cover", "contain"] = "contain"
    transform: Transform = Transform()
    opacity: float = _OPACITY
    gain_db: float = Field(default=0.0, ge=-60, le=12)
    muted: bool = False


class ShapeObject(BaseModel):
    """一个原生矢量图元，路径数据仅描述几何，不传渲染器代码。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["shape"]
    object_id: str = _ID
    shape: Literal["rect", "ellipse", "path"]
    layout: LayoutBox
    fill: str | None = Field(default="#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    stroke: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_width: float = Field(default=0.0, ge=0, le=200)
    corner_radius: float = Field(default=0.0, ge=0, le=1000)
    path: str | None = Field(default=None, max_length=4096)
    transform: Transform = Transform()
    opacity: float = _OPACITY

    @model_validator(mode="after")
    def _geometry_matches_shape(self) -> ShapeObject:
        if self.shape == "path":
            if not self.path or not re.fullmatch(
                r"[MmLlHhVvCcQqZz0-9eE+\-.,\s]+", self.path
            ):
                raise ValueError("path shapes need numeric M/L/H/V/C/Q/Z path data")
        elif self.path is not None:
            raise ValueError("only path shapes carry path data")
        if self.shape != "rect" and self.corner_radius:
            raise ValueError("corner_radius belongs to rect shapes")
        return self


# One Generator keeps the same raster/time contract for design preview and
# authorized production. Thirty fps matches the Composition's native timeline;
# the frame cap bounds one baked clip to two minutes, while Directors normally
# split a longer work into smaller scenes. The isolated runner still applies
# its independent wall-clock, memory, storage and media-byte budgets.
GENERATOR_FPS = 30
GENERATOR_MAX_FRAMES = 3600


class ProgramOutput(BaseModel):
    """单个受控视觉程序的固定画幅约束。"""

    model_config = ConfigDict(extra="forbid")

    width: int = Field(ge=16, le=1920)
    height: int = Field(ge=16, le=1920)
    fps: int = Field(default=GENERATOR_FPS, gt=0, le=60)
    duration_frames: int = Field(gt=0, le=GENERATOR_MAX_FRAMES)
    background: str = _HEX_COLOR

    @model_validator(mode="after")
    def _even_raster(self) -> ProgramOutput:
        if self.width % 2 or self.height % 2:
            raise ValueError("program output dimensions must be even for H.264")
        return self


class GeneratedImageOutput(BaseModel):
    """B-V 使用的单张生成图片输出约束。"""

    model_config = ConfigDict(extra="forbid")

    aspect_ratio: Literal["16:9"] = "16:9"


# These exact locked versions are part of the project's content identity and
# checked again by the upstream bake runner. No runtime dependency installation.
COMPONENT_DEPENDENCIES = {
    "react": "19.2.7",
    "react-dom": "19.2.7",
    "remotion": "4.0.484",
    "@remotion/bundler": "4.0.484",
    "@remotion/renderer": "4.0.484",
}


_PROJECT_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,119}$")
_COMPOSITION_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def _validate_project_path(value: str, *, source_file: bool = False) -> str:
    if (
        not _PROJECT_PATH.fullmatch(value)
        or value.startswith(("/", "."))
        or ".." in value.split("/")
        or "//" in value
        or value.endswith("/")
    ):
        raise ValueError("project paths are bounded relative paths without traversal")
    if source_file and not value.endswith((".ts", ".tsx")):
        raise ValueError("Remotion project source files must be .ts or .tsx")
    return value


def _validate_json_numbers(value: JsonValue) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        if abs(value) > 9007199254740991:
            raise ValueError("project integer props must be JavaScript-safe integers")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("project numeric props must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_numbers(item)
        return
    for item in value.values():
        _validate_json_numbers(item)


def _validate_props_schema(schema: dict[str, Any], props: dict[str, JsonValue]) -> None:
    """The deliberately small JSON-Schema subset shared with the TS runner."""
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValueError("props_schema must be a closed object schema")
    if set(schema) - {"type", "additionalProperties", "properties", "required"}:
        raise ValueError("props_schema supports only type/properties/required/additionalProperties")
    properties = schema.get("properties")
    required = schema.get("required", [])
    if not isinstance(properties, dict) or not isinstance(required, list):
        raise ValueError("props_schema properties/required are malformed")
    if set(properties) != set(props) or set(required) - set(properties):
        raise ValueError("props_schema must describe exactly the supplied props")
    if any(not isinstance(key, str) for key in required) or len(set(required)) != len(required):
        raise ValueError("props_schema required keys are malformed")
    kinds = {
        str: "string", bool: "boolean", int: "integer", float: "number",
        list: "array", dict: "object", type(None): "null",
    }
    for key, prop in props.items():
        rule = properties[key]
        if not isinstance(rule, dict) or set(rule) - {"type"} or rule.get("type") not in {
            "string", "number", "integer", "boolean", "array", "object", "null"
        }:
            raise ValueError(f"props_schema.{key} needs one supported type")
        expected = rule["type"]
        actual = "number" if isinstance(prop, float) else kinds[type(prop)]
        if actual != expected and not (expected == "number" and actual == "integer"):
            raise ValueError(f"prop {key!r} does not match props_schema")
        if actual in {"array", "object"}:
            # Nested values remain typed JSON, but this first schema subset does
            # not pretend to validate an unbounded recursive JSON-Schema DSL.
            encoded = json.dumps(prop, ensure_ascii=False, allow_nan=False)
            if len(encoded) > 4096:
                raise ValueError(f"prop {key!r} exceeds its structured-value budget")


class RemotionSourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str = Field(min_length=1, max_length=24000)
    digest: str = Field(default="", pattern=r"^$|^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _pin_file(self) -> RemotionSourceFile:
        is_json = self.path.endswith(".json")
        _validate_project_path(self.path, source_file=not is_json)
        if is_json:
            try:
                _validate_json_numbers(json.loads(self.content))
            except (ValueError, RecursionError) as exc:
                raise ValueError(f"project data file {self.path!r} must contain valid JSON") from exc
        actual = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.digest and self.digest != actual:
            raise ValueError(f"source file {self.path!r} digest does not match its content")
        self.digest = actual
        return self


class RemotionResource(BaseModel):
    """固定的图片，与其他媒体一样绑定到不可变 SourceSnapshot。"""

    model_config = ConfigDict(extra="forbid")

    path: str
    snapshot_id: UUID
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: Literal["image/png", "image/jpeg", "image/webp"]

    @field_validator("path")
    @classmethod
    def _safe_path(cls, value: str) -> str:
        return _validate_project_path(value)

    @model_validator(mode="after")
    def _matching_suffix(self) -> RemotionResource:
        expected = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
        if not self.path.lower().endswith(expected[self.content_type]):
            raise ValueError("resource path suffix must match its fixed content type")
        return self


REMOTION_RESOURCE_LIMIT = 64


class RemotionProjectSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    entry: str
    composition_id: str
    files: list[RemotionSourceFile] = Field(min_length=2, max_length=24)
    props: dict[str, JsonValue] = Field(default={}, max_length=32)
    props_schema: dict[str, Any]
    resources: list[RemotionResource] = Field(default=[], max_length=REMOTION_RESOURCE_LIMIT)
    dependencies: dict[str, str] = COMPONENT_DEPENDENCIES

    @model_validator(mode="before")
    @classmethod
    def _empty_props_wire(cls, value: Any) -> Any:
        """Null/serialized empty props mean a closed zero-parameter project."""
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        props = normalized.get("props")
        if props is None:
            normalized["props"] = props = {}
        schema = normalized.get("props_schema")
        if isinstance(schema, str):
            stripped = schema.strip()
            if not stripped:
                schema = None
            else:
                try:
                    schema = json.loads(stripped)
                except (json.JSONDecodeError, ValueError):
                    schema = stripped
        empty_object_schema = (
            isinstance(schema, dict)
            and set(schema) <= {"type", "properties"}
            and schema.get("type") in {None, "", "object"}
            and schema.get("properties") in (None, {})
        )
        if (schema is None or schema == {} or empty_object_schema) and not props:
            schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {},
                "required": [],
            }
        normalized["props_schema"] = schema
        return normalized

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version_wire(cls, value: Any) -> Any:
        return 1 if value == "1" else value

    @field_validator("files", "resources", mode="before")
    @classmethod
    def _list_fields_wire(cls, value: Any) -> Any:
        return _list_wire(value)

    @field_validator("props_schema", mode="before")
    @classmethod
    def _props_schema_wire(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "required" in normalized:
            normalized["required"] = _list_wire(normalized["required"])
        additional = normalized.get("additionalProperties")
        if isinstance(additional, str) and additional in {"true", "false"}:
            normalized["additionalProperties"] = additional == "true"
        return normalized

    @model_validator(mode="after")
    def _complete_project(self) -> RemotionProjectSource:
        _validate_project_path(self.entry, source_file=True)
        if not _COMPOSITION_ID.fullmatch(self.composition_id):
            raise ValueError("invalid Remotion Composition id")
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)) or self.entry not in paths:
            raise ValueError("project files need unique paths and the declared entry")
        if sum(len(item.content.encode("utf-8")) for item in self.files) > 96000:
            raise ValueError("Remotion project source exceeds its 96k-byte budget")
        resource_paths = [item.path for item in self.resources]
        if len(resource_paths) != len(set(resource_paths)) or set(resource_paths) & set(paths):
            raise ValueError("project resource paths must be unique and outside source files")
        if self.dependencies != COMPONENT_DEPENDENCIES:
            raise ValueError("Remotion project dependencies differ from the approved lock")
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", key) for key in self.props):
            raise ValueError("project prop keys use letters, digits and underscores")
        if len(json.dumps(self.props, ensure_ascii=False, allow_nan=False)) > 8192:
            raise ValueError("project props exceed their 8k-byte budget")
        _validate_json_numbers(self.props)
        _validate_props_schema(self.props_schema, self.props)
        return self


class GeneratorObject(BaseModel):
    """可审阅的程序或模型请求，制作时据此解析固定媒体。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["generator"]
    object_id: str = _ID
    producer: Literal["draw-2d", "image-generation", "remotion-project"] = "draw-2d"
    code: str | None = Field(default=None, min_length=1, max_length=24000)
    project: RemotionProjectSource | None = None
    prompt: str | None = Field(default=None, min_length=1, max_length=2000)
    provider: Literal["minimax"] | None = None
    model: Literal["image-01"] | None = None
    parameters: dict[str, str | float | bool] = Field(default={}, max_length=24)
    output: ProgramOutput | GeneratedImageOutput
    layout: LayoutBox
    fit: Literal["cover", "contain"] = "cover"
    transform: Transform = Transform()
    opacity: float = _OPACITY

    @model_validator(mode="after")
    def _bounded_parameters(self) -> GeneratorObject:
        for key, value in self.parameters.items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", key):
                raise ValueError("program parameter keys use letters, digits and underscores")
            if isinstance(value, str) and len(value) > 128:
                raise ValueError("program string parameters stay within 128 characters")
        if self.producer == "draw-2d":
            if self.code is None or self.project is not None or not isinstance(self.output, ProgramOutput):
                raise ValueError("draw-2d needs code and program output constraints")
            if self.prompt is not None or self.provider is not None or self.model is not None:
                raise ValueError("draw-2d does not take model-generation fields")
        elif self.producer == "remotion-project":
            if (self.code is None) == (self.project is None) or not isinstance(self.output, ProgramOutput):
                raise ValueError("remotion-project needs exactly one complete project or historical code source")
            if self.project is not None and self.parameters:
                raise ValueError("complete Remotion projects keep values in project.props")
            if self.prompt is not None or self.provider is not None or self.model is not None:
                raise ValueError("remotion-project does not take model-generation fields")
        else:
            if (
                self.prompt is None
                or self.provider != "minimax"
                or self.model != "image-01"
                or not isinstance(self.output, GeneratedImageOutput)
            ):
                raise ValueError("image-generation needs a MiniMax image-01 prompt and image output")
            if self.code is not None or self.project is not None or self.parameters:
                raise ValueError("image-generation exposes only its prompt and declared image output")
        return self

    def program_digest(self) -> str:
        if self.producer == "remotion-project" and self.project is not None:
            payload = {
                "producer": self.producer,
                "project": self.project.model_dump(mode="json"),
                "output": self.output.model_dump(mode="json"),
            }
        elif self.producer in {"draw-2d", "remotion-project"}:
            # Historical single-component versions retain their original digest.
            payload = {
                "producer": self.producer,
                "code": self.code,
                "parameters": self.parameters,
                "output": self.output.model_dump(mode="json"),
                **(
                    {"dependencies": COMPONENT_DEPENDENCIES}
                    if self.producer == "remotion-project"
                    else {}
                ),
            }
        else:
            payload = {
                "producer": self.producer,
                "prompt": self.prompt,
                "provider": self.provider,
                "model": self.model,
                "parameters": self.parameters,
                "output": self.output.model_dump(mode="json"),
            }
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class AudioObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["audio"]
    object_id: str = _ID
    gain_db: float = Field(default=0.0, ge=-60, le=12)


class NarrationAlignmentRef(BaseModel):
    """源音频对齐的 Speech 所引用的 READY 对齐结果及不可变音频字节。"""

    model_config = ConfigDict(extra="forbid")

    alignment_id: UUID
    content_digest: str = Field(min_length=64, max_length=64)
    audio_snapshot_id: UUID
    audio_digest: str = Field(min_length=64, max_length=64)


class SpeechObject(BaseModel):
    """已审阅的旁白，制作时转换为普通音频。待合成的 Speech 需要 TTS 请求字段。已与源音频对齐的 Speech 使用固定音频来源，不启动新合成。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["speech"]
    object_id: str = _ID
    text: str = Field(min_length=1, max_length=9000)
    provider: Literal["minimax"] | None = "minimax"
    model: Literal["speech-2.6-hd"] | None = "speech-2.6-hd"
    voice_id: str | None = Field(default=None, min_length=1, max_length=255)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    gain_db: float = Field(default=0.0, ge=-60, le=12)
    alignment: NarrationAlignmentRef | None = None

    @model_validator(mode="after")
    def _nonblank_script(self) -> SpeechObject:
        if not self.text.strip():
            raise ValueError("speech text must not be blank")
        if self.alignment is None and (
            self.provider is None
            or self.model is None
            or self.voice_id is None
            or self.language is None
        ):
            raise ValueError("pending speech needs provider, model, voice and language")
        if self.alignment is not None and (self.provider is not None or self.model is not None):
            raise ValueError("source-aligned speech does not carry a TTS provider request")
        return self


Object = Annotated[
    TextObject | ShapeObject | ImageObject | WebObject | VideoObject
    | GeneratorObject | AudioObject | SpeechObject,
    Field(discriminator="kind"),
]


class Easing(BaseModel):
    """分段缓动（§5.1），作用于当前关键帧至下一关键帧的区间。hold 将当前值保持至下一关键帧，再跳变。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["linear", "hold", "cubic_bezier"] = "linear"
    # Cubic-bezier control points (x1, y1, x2, y2); required iff kind asks.
    params: tuple[float, float, float, float] | None = None

    @field_validator("params", mode="before")
    @classmethod
    def _params_wire(cls, value: Any) -> Any:
        if isinstance(value, dict) and set(value) == {"item"}:
            return _list_wire(value["item"])
        return value

    @model_validator(mode="after")
    def _params_when_bezier(self) -> Easing:
        if self.kind == "cubic_bezier" and self.params is None:
            raise ValueError("cubic_bezier easing requires params (x1, y1, x2, y2)")
        if self.kind != "cubic_bezier" and self.params is not None:
            raise ValueError(f"{self.kind} easing takes no params")
        if self.params is not None and not (0 <= self.params[0] <= 1 and 0 <= self.params[2] <= 1):
            raise ValueError("cubic_bezier x control points must stay in [0, 1]")
        return self


class Keyframe(BaseModel):
    """at 使用 Clip 局部整数刻度，时基为 settings.timebase，0 表示片段开始。"""

    model_config = ConfigDict(extra="forbid")

    at: int = Field(ge=0, description="以 settings.timebase 表示的片段局部整数刻度。0 对应该 Clip 在成片中的起点，不使用秒数、帧数或绝对时间线时间。")
    value: float | tuple[float, float] | str = Field(description="单位由所属 Animation.property 决定：opacity/path.reveal 为 [0,1] 的归一化值，transform.scale 为倍数，transform.rotation 为度，transform.position 为画布像素偏移 [x,y]，filter.blur/text.stroke_width 为像素，text.letter_spacing 为 em，audio.gain 为线性倍数。仅 text.color/text.stroke_color 使用精确的 #RRGGBB 字符串。")
    easing: Easing = Easing()


AnimatableProperty = Literal[
    "opacity",
    "transform.position",
    "transform.scale",
    "transform.rotation",
    "filter.blur",
    "text.letter_spacing",
    "text.color",
    "text.stroke_color",
    "text.weight",
    "text.stroke_width",
    "path.reveal",
    "audio.gain",
]


class TextPartTarget(BaseModel):
    """明确指定派生文字部分及片段局部的错峰刻度。ID 由内容和范围确定，不用数组下标。编辑文字若导致目标失效则拒绝修改，不静默改指其他动画目标。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["line", "word", "grapheme"]
    part_ids: list[str] = Field(min_length=1)
    stagger: int = Field(default=0, ge=0, description="派生 TextParts 之间的片段局部延迟，单位为 settings.timebase 刻度，不使用秒数。")


class NarrationAnchor(BaseModel):
    """服务端解析的词级来源，用于片段局部动画。"""

    model_config = ConfigDict(extra="forbid")

    alignment_id: UUID
    content_digest: str = Field(min_length=64, max_length=64)
    speech_object_id: str = _ID
    word_id: str = _ID


class Animation(BaseModel):
    """一个对象或其派生 TextParts 上的一条属性动画轨迹。"""

    model_config = ConfigDict(extra="forbid")

    animation_id: str = _ID
    target_object_id: str = Field(..., description="该 Animation 所属 Clip 内的 object_id，不可跨片段指定目标。", min_length=1, max_length=64)
    text_part: TextPartTarget | None = None
    property: AnimatableProperty
    keyframes: list[Keyframe] = Field(min_length=1)
    narration_anchor: NarrationAnchor | None = None

    @model_validator(mode="before")
    @classmethod
    def _numeric_keyframe_strings(cls, value: Any) -> Any:
        # Keyframe.value also accepts color strings. Its parent property owns
        # the scalar interpretation; generic union coercion cannot decide it.
        if not isinstance(value, dict) or value.get("property") not in get_args(AnimatableProperty):
            return value
        frames = _list_wire(value.get("keyframes"))
        if not isinstance(frames, list):
            return value
        value = {**value, "keyframes": frames}
        if value.get("property") in {"text.color", "text.stroke_color"}:
            return {
                **value,
                "keyframes": [
                    {**frame, "easing": {"kind": "hold"}}
                    if isinstance(frame, dict) and (frame.get("easing") is None or frame.get("easing") == {})
                    else frame
                    for frame in frames
                ],
            }
        if value.get("property") == "transform.position":
            return value
        copied = []
        for frame in frames:
            if isinstance(frame, dict) and isinstance(frame.get("value"), str):
                text = frame["value"].strip()
                if len(text) > 128 or re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text) is None:
                    copied.append(frame)
                    continue
                try:
                    number = float(text)
                except (ValueError, OverflowError):
                    pass
                else:
                    if math.isfinite(number):
                        frame = {**frame, "value": number}
            copied.append(frame)
        return {**value, "keyframes": copied}


class Clip(BaseModel):
    """轨道上的统一剪辑单元，包括时间、来源和对象（§4.2）。"""

    model_config = ConfigDict(extra="forbid")

    clip_id: str = _ID
    range: TimeRange = Field(description="以 settings.timebase 整数刻度表示的左闭右开成片时间范围，不使用源时间、秒数或帧数。")
    scene_id: str | None = None
    linked_group_id: str | None = None
    source: ClipSource | None = None
    object: Object
    animations: list[Animation] = Field(default_factory=list, description="动画放在这个完整 Clip 内。每个 target_object_id 都指向本 Clip 自身的对象。")

    @field_validator("animations", mode="before")
    @classmethod
    def _animations_wire(cls, value: Any) -> Any:
        return _list_wire(value)


TrackKind = Literal["visual", "audio"]
TrackRole = Literal["main", "title", "caption", "dialogue", "music", "effect"]


class Track(BaseModel):
    """每条轨道贯穿整条时间线（§4.1）。视觉轨道以 order 决定叠放顺序，值越小越先绘制，位于底层。"""

    model_config = ConfigDict(extra="forbid")

    track_id: str = _ID
    kind: TrackKind
    role: TrackRole = Field(description="语义角色。多个轨道可共享角色，同时出现的视觉对象需要独立轨道。")
    order: int = Field(ge=0)
    clips: list[Clip] = Field(default_factory=list, description="一条时序轨道内各片段的范围不得重叠。要同时展示视觉对象，使用不同轨道并指定不同 order。")

    @field_validator("clips", mode="before")
    @classmethod
    def _clips_wire(cls, value: Any) -> Any:
        return _list_wire(value)


class Scene(BaseModel):
    """成片时间线上的叙事范围，不是 Track 的容器（§3.1）。"""

    model_config = ConfigDict(extra="forbid")

    scene_id: str = _ID
    range: TimeRange = Field(description="以 settings.timebase 整数刻度表示的叙事成片范围。Scene 不持有 Track。")
    intent: str = ""
    visual_description: str | None = None
    speech_clip_ids: list[str] = []

    @field_validator("speech_clip_ids", mode="before")
    @classmethod
    def _speech_clip_ids_wire(cls, value: Any) -> Any:
        return _list_wire(value)


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transition_id: str = _ID
    from_clip_id: str = _ID
    to_clip_id: str = _ID
    kind: Literal["crossfade"] = "crossfade"
    duration: int = Field(gt=0, description="转场时长，单位为 settings.timebase 的成片刻度，不使用秒数或帧数。")
    alignment: Literal["center"] = "center"


class Timeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracks: list[Track] = []
    transitions: list[Transition] = []

    @field_validator("transitions", mode="before")
    @classmethod
    def _transitions_wire(cls, value: Any) -> Any:
        return _list_wire(value)


class EditTarget(BaseModel):
    """A stable-id target set for the shared temporal editing algebra."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["clip", "scene", "track", "selection", "timeline"]
    id: str | None = Field(default=None, min_length=1, max_length=64)
    clip_ids: list[str] = Field(default_factory=list, max_length=256)
    scene_ids: list[str] = Field(default_factory=list, max_length=256)
    track_ids: list[str] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def _address_matches_kind(self) -> EditTarget:
        if self.kind == "selection":
            if self.id is not None or not (self.clip_ids or self.scene_ids or self.track_ids):
                raise ValueError("a selection needs explicit clip/scene/track ids and no singular id")
        else:
            if self.clip_ids or self.scene_ids or self.track_ids:
                raise ValueError("selection id lists belong only to a selection target")
            if self.kind == "timeline":
                if self.id is not None:
                    raise ValueError("the timeline target takes no id")
            elif self.id is None:
                raise ValueError(f"{self.kind} target needs its stable id")
        return self


class CompositionContent(BaseModel):
    """The complete final content validated as a whole before an immutable
    CompositionVersion may be saved."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    settings: VersionSettings
    creative_state: "CreativeState | None" = None
    sources: list[SourceBinding] = []
    scenes: list[Scene] = []
    timeline: Timeline = Timeline()
