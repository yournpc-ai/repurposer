"""Pydantic models for Repurposer API."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class AssetType(StrEnum):
    """Asset types."""

    VIDEO = "video"
    AUDIO = "audio"
    TRANSCRIPT = "transcript"
    SLIDES = "slides"
    IMAGE = "image"
    VOICE_SAMPLE = "voice_sample"
    PAST_MATERIAL = "past_material"


class AssetStatus(StrEnum):
    """Asset processing statuses.

    Drives the async processing pipeline: an asset is created ``PENDING`` on
    upload, a worker flips it to ``PROCESSING`` while it runs, then to
    ``COMPLETED`` or ``FAILED``. Replaces the previous ``processed_at IS NULL``
    overload that could not distinguish "not yet processed" from "failed".
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProjectStatus(StrEnum):
    """Project statuses."""

    DRAFT = "draft"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    REVIEW = "review"
    COMPLETED = "completed"


class WorkflowStatus(StrEnum):
    """Workflow run statuses."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    COMPLETED = "completed"
    FAILED = "failed"


class SpeakerPersona(BaseModel):
    """Speaker style persona."""

    model_config = ConfigDict(extra="forbid")

    core_values: list[str] = Field(default_factory=list)
    favorite_metaphors: list[str] = Field(default_factory=list)
    sentence_style: str = ""
    emotional_tone: Literal["rational", "passionate", "gentle", "sharp", "humorous"] = "rational"
    typical_hooks: list[str] = Field(default_factory=list)
    avoid_words: list[str] = Field(default_factory=list)


class ToneSettings(BaseModel):
    """Tone settings for generation."""

    model_config = ConfigDict(extra="forbid")

    academic_vs_casual: float = Field(default=0.5, ge=0.0, le=1.0)
    rational_vs_passionate: float = Field(default=0.5, ge=0.0, le=1.0)
    concise_vs_detailed: float = Field(default=0.5, ge=0.0, le=1.0)
    audience: Literal["academic", "industry", "general", "investor"] = "industry"


class SpeakerBase(BaseModel):
    """Base speaker model."""

    name: str
    title: str | None = None
    language: str = "zh"
    avatar_url: str | None = None


class SpeakerCreate(SpeakerBase):
    """Create speaker request."""

    pass


class SpeakerUpdate(BaseModel):
    """Update speaker request."""

    name: str | None = None
    title: str | None = None
    language: str | None = None
    avatar_url: str | None = None
    persona: SpeakerPersona | None = None


class SpeakerResponse(SpeakerBase):
    """Speaker response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    persona: SpeakerPersona | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ProjectBase(BaseModel):
    """Base project model."""

    title: str
    event_name: str | None = None
    language: str = "zh"


class ProjectCreate(ProjectBase):
    """Create project request."""

    speaker_id: UUID | None = None


class ProjectUpdate(BaseModel):
    """Update project request."""

    title: str | None = None
    event_name: str | None = None
    language: str | None = None
    status: ProjectStatus | None = None
    tone_snapshot: ToneSettings | None = None


class ProjectResponse(ProjectBase):
    """Project response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    speaker_id: UUID | None
    status: ProjectStatus
    tone_snapshot: ToneSettings | None = None
    created_at: datetime
    updated_at: datetime | None = None


class AssetResponse(BaseModel):
    """Asset response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None = None
    speaker_id: UUID | None = None
    type: AssetType
    file_url: str | None = None
    transcript: str | None = None
    extracted_text: str | None = None
    processing_status: AssetStatus
    processing_error: str | None = None
    duration_seconds: int | None = None
    processed_at: datetime | None = None
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def stream_url(self) -> str | None:
        """Browser-playable URL for this asset, resolved through the storage seam."""
        from app.services.storage import stream_url

        return stream_url(self.file_url)


class Shot(BaseModel):
    """A single shot in a clip script."""

    model_config = ConfigDict(extra="forbid")

    time_range: str
    visual: str
    subtitle: str
    mood: str


class ClipScript(BaseModel):
    """Generated clip script."""

    model_config = ConfigDict(extra="forbid")

    hook: str
    duration_seconds: int = Field(default=30, ge=15, le=60)
    shots: list[Shot] = Field(default_factory=list)
    title_options: list[str] = Field(default_factory=list)
    music_mood: str = "calm"
    virality_score: int | None = Field(default=None, ge=1, le=100)


class Segment(BaseModel):
    """A high-potential segment extracted from project materials."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for this segment")
    source_text: str = Field(description="Original text of the segment")
    start_marker: str = Field(description="Approximate start location in source")
    end_marker: str = Field(description="Approximate end location in source")
    summary: str = ""
    hook: str = ""
    virality_score: int = Field(default=50, ge=1, le=100)
    golden_quote: str = ""
    duration_seconds: int = Field(default=30, ge=15, le=120)


class ContentAnalysis(BaseModel):
    """Analysis result for project materials."""

    model_config = ConfigDict(extra="forbid")

    overall_summary: str = ""
    core_arguments: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    target_audience: str = ""
    segments: list[Segment] = Field(default_factory=list)


class LinkedInPost(BaseModel):
    """Generated LinkedIn post."""

    model_config = ConfigDict(extra="forbid")

    content: str
    hashtags: list[str] = Field(default_factory=list)


class QuoteCard(BaseModel):
    """Generated quote card."""

    model_config = ConfigDict(extra="forbid")

    quote: str
    attribution: str


class QuoteCardsResponse(BaseModel):
    """Multiple quote cards response."""

    model_config = ConfigDict(extra="forbid")

    quotes: list[QuoteCard] = Field(default_factory=list)


class CarouselSlide(BaseModel):
    """One slide of a LinkedIn/social carousel (a swipeable narrative)."""

    model_config = ConfigDict(extra="forbid")

    title: str  # short heading
    body: str = ""  # 1-3 short lines; may be empty on a pure-title cover/CTA


class CarouselResponse(BaseModel):
    """A carousel = ordered slides (cover/hook -> points -> CTA)."""

    model_config = ConfigDict(extra="forbid")

    slides: list[CarouselSlide] = Field(default_factory=list)


class Summary(BaseModel):
    """Generated multi-language summary."""

    model_config = ConfigDict(extra="forbid")

    tldr: str
    key_points: list[str] = Field(default_factory=list)
    full: str


class BlogPost(BaseModel):
    """Generated blog post."""

    model_config = ConfigDict(extra="forbid")

    title: str
    content: str


class DerivativeType(StrEnum):
    """Derivative content types."""

    LINKEDIN_POST = "linkedin_post"
    QUOTE_CARD = "quote_card"
    CAROUSEL = "carousel"
    MULTILINGUAL_SCRIPT = "multilingual_script"
    SUMMARY = "summary"
    BLOG = "blog"


class RenderStatus(StrEnum):
    """Vertical-clip render job statuses (NULL on a Clip = render not requested)."""

    PENDING = "pending"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# clip-spec: the renderer-agnostic contract for the vertical-clip editor.
# See docs/VIDEO_EDITOR.md §4. Describes WHAT to render, never HOW — contains no
# Remotion/React/FFmpeg concepts, so the renderer behind it stays swappable.
# ---------------------------------------------------------------------------


class ClipSource(BaseModel):
    """Source backing a clip: an on-camera video, or a "stills" audiogram."""

    model_config = ConfigDict(extra="forbid")

    asset_id: UUID
    kind: Literal["video", "stills"] = "video"
    # browser-playable URL via storage.stream_url() (storage seam).
    # video: the video file. stills: the optional speech audio ("" when none).
    url: str = ""
    # stills only: ordered backing images (0 -> solid bg, 1 -> full-frame,
    # N -> even hard-cut slideshow across the duration).
    image_urls: list[str] = Field(default_factory=list)
    fps: int = 30
    duration: float | None = None  # source length (seconds) — trim slider bound


class ClipSegment(BaseModel):
    """A kept span of the source. ``hidden=True`` is a non-destructive delete."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    hidden: bool = False


class ClipCrop(BaseModel):
    """9:16/1:1 reframe as a normalized center + scale (applied via transform)."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(default=0.5, ge=0.0, le=1.0)
    y: float = Field(default=0.5, ge=0.0, le=1.0)
    scale: float = Field(default=1.0, gt=0.0)


class CaptionCue(BaseModel):
    """One caption cue (word/line) from ASR word-level timestamps; text editable."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    lang: str = "en"


class Point(BaseModel):
    """Normalized center point in [0,1] (CSS translate / libass \\pos)."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class ClipTitle(BaseModel):
    """Optional title/hook card overlay."""

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    enabled: bool = False
    size: int | None = None  # composition px; None -> renderer default
    position: Point | None = None  # normalized center; None -> default (top)


class ClipMusic(BaseModel):
    """Optional background music."""

    model_config = ConfigDict(extra="forbid")

    track_id: str | None = None  # mood key / provenance (e.g. "calm")
    url: str | None = None  # resolved track URL (storage seam); None = no track
    enabled: bool = False
    gain_db: float = -18.0


class ClipDub(BaseModel):
    """Cloned-voice dubbed speech; when enabled, replaces the source's audio."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = None  # resolved dub audio URL (storage seam)
    enabled: bool = False
    gain_db: float = 0.0


class ClipBrand(BaseModel):
    """Resolved brand values baked into the spec at generation time.

    Renderer-agnostic data (no DB ref): the API resolves the latest
    ``BrandTemplate`` config into these fields so the render service / preview
    never need DB access. ``None`` = renderer falls back to its default look.
    """

    model_config = ConfigDict(extra="forbid")

    logo_url: str | None = None  # corner logo overlay (absolute or storage URL)
    cta: str | None = None  # call-to-action text shown near the bottom
    cta_position: Point | None = None  # normalized center; None -> default (bottom)
    caption_color: str | None = None  # hex; overrides the default white caption
    caption_size: int | None = None  # px; overrides the default caption size
    caption_font: str | None = None  # font key: lilita/inter/playfair/source-serif
    intro_text: str | None = None  # opening title card (None = no intro)
    outro_text: str | None = None  # closing title card (None = no outro)
    fill_mode: Literal["fill", "fit"] = "fill"  # video objectFit: cover / contain


class ClipSpec(BaseModel):
    """Renderer-agnostic clip render contract (see docs/VIDEO_EDITOR.md §4)."""

    model_config = ConfigDict(extra="forbid")

    source: ClipSource
    aspect: Literal["9:16", "1:1"] = "9:16"
    segments: list[ClipSegment] = Field(default_factory=list)
    crop: ClipCrop = Field(default_factory=ClipCrop)
    caption_track: list[CaptionCue] = Field(default_factory=list)
    # Preset enum, NOT free styling — keeps preview=render parity and the
    # future hand-rolled-FFmpeg swap cheap (CSS ∩ libass subset).
    caption_style_preset: Literal["clean-bottom", "karaoke-highlight"] = "clean-bottom"
    caption_position: Point | None = None  # normalized center; None -> default (bottom)
    title: ClipTitle = Field(default_factory=ClipTitle)
    music: ClipMusic = Field(default_factory=ClipMusic)
    dub: ClipDub | None = None  # cloned-voice dub; replaces source audio when enabled
    brand: ClipBrand | None = None  # resolved brand values (None = default look)
    brand_ref: UUID | None = None
    target_language: str = "en"


class ClipResponse(BaseModel):
    """Generated clip response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    hook: str
    script: ClipScript
    title_options: list[str]
    music_mood: str
    status: str
    video_url: str | None = None
    duration: int
    language: str
    source_segment: Segment | None = None
    render_spec: ClipSpec | None = None
    render_status: RenderStatus | None = None
    render_error: str | None = None
    srt_url: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ClipUpdate(BaseModel):
    """Partial update for a clip."""

    hook: str | None = None
    script: ClipScript | None = None
    title_options: list[str] | None = None
    music_mood: str | None = None
    status: str | None = None
    render_spec: ClipSpec | None = None


class CaptionTranslation(BaseModel):
    """LLM caption-translation result: translated lines, parallel to the input."""

    model_config = ConfigDict(extra="forbid")

    lines: list[str] = Field(default_factory=list)


class TranslateCaptionsRequest(BaseModel):
    """Re-translate a clip's caption track into ``target_language``."""

    target_language: str = Field(description="Target language code, e.g. en/fr/de/es/it")


class DubRequest(BaseModel):
    """Voice-clone dub a clip into ``target_language`` (speaker's own voice)."""

    target_language: str = Field(description="Target language code, e.g. en/fr/de/es/it")


class DerivativeResponse(BaseModel):
    """Generated derivative (LinkedIn post, quote cards, …)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    type: DerivativeType
    content: dict
    language: str
    image_url: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime | None = None


class DerivativeUpdate(BaseModel):
    """Partial update for a derivative."""

    content: dict | None = None
    status: str | None = None


class GenerateRequest(BaseModel):
    """Generate content request."""

    clip_count: int = Field(default=3, ge=1, le=10)
    outputs: list[
        Literal["clips", "linkedin", "quote_cards", "carousel", "summary", "blog"]
    ] = Field(default_factory=lambda: ["clips", "linkedin", "quote_cards"])
    tone_settings: ToneSettings | None = None
    target_language: str = Field(
        default="en",
        description="Target language code, e.g. en/zh/fr/de/es/it",
    )
    brand_template_id: UUID | None = Field(
        default=None,
        description="Brand template to bake into clips; None = most recent.",
    )
    instruction: str | None = Field(
        default=None,
        description="User steering prompt: what to focus on / produce.",
    )


class ExportRequest(BaseModel):
    """Export project content request."""

    formats: list[Literal["text", "images"]] = Field(
        default_factory=lambda: ["text"]
    )


class FeedbackScope(StrEnum):
    """Feedback scope."""

    HOOK = "hook"
    FULL_SCRIPT = "full_script"
    TONE = "tone"
    TRANSLATION = "translation"


class FeedbackReason(StrEnum):
    """Feedback reason."""

    HOOK_NOT_CATCHY = "hook_not_catchy"
    NOT_LIKE_SPEAKER = "not_like_speaker"
    TOO_COMPLEX = "too_complex"
    TOO_SIMPLE = "too_simple"
    FACTUALLY_INACCURATE = "factually_inaccurate"
    DIFFERENT_EXPRESSION = "different_expression"
    OTHER = "other"


class FeedbackRequest(BaseModel):
    """Feedback request."""

    scope: FeedbackScope
    reason: FeedbackReason
    detail: str | None = None


class ReviewResult(BaseModel):
    """Review result for a generated clip script."""

    model_config = ConfigDict(extra="forbid")

    persona_match_score: int = Field(default=70, ge=1, le=100)
    hook_score: int = Field(default=70, ge=1, le=100)
    clarity_score: int = Field(default=70, ge=1, le=100)
    viral_potential_score: int = Field(default=70, ge=1, le=100)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    overall_verdict: Literal["pass", "revise", "reject"] = "pass"


class WorkflowRunResponse(BaseModel):
    """Workflow run response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: WorkflowStatus
    current_step: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    error: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class BrandTemplateBase(BaseModel):
    """Shared brand template fields."""

    name: str
    config: dict = Field(default_factory=dict)


class BrandTemplateCreate(BrandTemplateBase):
    """Create a brand template."""


class BrandTemplateUpdate(BaseModel):
    """Partial update of a brand template."""

    name: str | None = None
    config: dict | None = None


class BrandTemplateResponse(BrandTemplateBase):
    """Brand template response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime | None = None
