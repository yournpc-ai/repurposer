"""Pydantic models for Repurposer API."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    computed_field,
    field_validator,
)


class MediaInputType(StrEnum):
    """Media types that can be fed directly to a multimodal LLM."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class MediaInput(BaseModel):
    """A single media snippet passed to the analyzer alongside text materials.

    Uses OpenAI-compatible content parts (image_url / video_url / audio_url).
    The URL may be a base64 data URL or an HTTP URL depending on model/provider
    capabilities and deployment constraints.
    """

    model_config = ConfigDict(extra="forbid")

    type: MediaInputType
    mime: str
    data_url: str
    caption: str | None = None


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


class ChatAttachment(BaseModel):
    """File attached to a chat message."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: Literal["file", "image", "video", "audio"]
    url: str | None = None
    size: int | None = None
    status: Literal["uploading", "uploaded", "failed"] = "uploaded"


class ChatSessionResponse(BaseModel):
    """Chat session response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None = None
    asset_id: UUID | None = None
    asset_type: Literal["clip", "derivative"] | None = None
    title: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class MessageRole(StrEnum):
    """Chat message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessageResponse(BaseModel):
    """A single chat message returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    role: MessageRole
    content: str | None = None
    attachments: list[ChatAttachment] = Field(default_factory=list)
    workflow_run_id: UUID | None = None
    intent: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None


class MessageListResponse(BaseModel):
    """List of chat messages in a session."""

    items: list[ChatMessageResponse]


class ChatIntent(BaseModel):
    """Parsed intent from a user chat message.

    The chat model extracts a structured action so the backend can dispatch to
    the right reviser/translator/renderer workflow.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "revise",
        "translate",
        "regenerate",
        "render",
        "select_music",
        "generate_music",
        "toggle_music",
        "adjust_gain",
        "unknown",
    ]
    scope: Literal["clip", "derivative", "project"] | None = None
    target_id: UUID | None = None
    target_language: str | None = None
    operation: str | None = None
    instruction: str | None = None
    parameters: dict = Field(default_factory=dict)


class ChatRequest(BaseModel):
    """Send a message to a project or asset chat.

    The backend locates or creates the appropriate session, builds the right
    context (project-level vs asset-level), and dispatches any background work.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    asset_id: UUID | None = None
    asset_type: Literal["clip", "derivative"] | None = None
    message: str
    attachments: list[ChatAttachment] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Result of sending a chat message."""

    session_id: UUID
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
    job_id: UUID | None = None


class SpeakerContext(BaseModel):
    """Speaker business object returned by the API and passed to agents.

    Contains only flat fields backed by DB columns. The ``persona`` concept
    lives at the agent layer as a rendered prompt summary, not as a stored
    field.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    name: str
    title: str | None = None
    language: str = "zh"
    avatar_url: str | None = None
    core_values: list[str] = Field(default_factory=list)
    favorite_metaphors: list[str] = Field(default_factory=list)
    sentence_style: str = ""
    emotional_tone: Literal["rational", "passionate", "gentle", "sharp", "humorous"] = "rational"
    typical_hooks: list[str] = Field(default_factory=list)
    avoid_words: list[str] = Field(default_factory=list)
    voice: str | None = None
    audience: str | None = None
    guidelines: str | None = None
    cta: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SpeakerCreate(BaseModel):
    """Create speaker request."""

    name: str
    title: str | None = None
    language: str = "zh"
    avatar_url: str | None = None
    core_values: list[str] | None = None
    favorite_metaphors: list[str] | None = None
    sentence_style: str | None = None
    emotional_tone: Literal["rational", "passionate", "gentle", "sharp", "humorous"] | None = None
    typical_hooks: list[str] | None = None
    avoid_words: list[str] | None = None
    voice: str | None = None
    audience: str | None = None
    guidelines: str | None = None
    cta: str | None = None


class SpeakerUpdate(BaseModel):
    """Update speaker request."""

    name: str | None = None
    title: str | None = None
    language: str | None = None
    avatar_url: str | None = None
    core_values: list[str] | None = None
    favorite_metaphors: list[str] | None = None
    sentence_style: str | None = None
    emotional_tone: Literal["rational", "passionate", "gentle", "sharp", "humorous"] | None = None
    typical_hooks: list[str] | None = None
    avoid_words: list[str] | None = None
    voice: str | None = None
    audience: str | None = None
    guidelines: str | None = None
    cta: str | None = None


class ToneSettings(BaseModel):
    """Tone settings for generation."""

    model_config = ConfigDict(extra="forbid")

    academic_vs_casual: float = Field(default=0.5, ge=0.0, le=1.0)
    rational_vs_passionate: float = Field(default=0.5, ge=0.0, le=1.0)
    concise_vs_detailed: float = Field(default=0.5, ge=0.0, le=1.0)
    audience: Literal["academic", "industry", "general", "investor"] = "industry"


class InferredIntent(BaseModel):
    """AI-recognized user intent from a prompt and optional file metadata.

    Returned by ``/infer-intent`` so the frontend can present a confirmation
    layer before generation. All fields have sensible defaults; the user can
    edit any of them.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal["generate", "answer"] = Field(
        default="generate",
        description=(
            "Whether the user wants to generate content or is asking a question "
            "about the tool's capabilities."
        ),
    )
    answer: str | None = Field(
        default=None,
        description="Direct answer text when action is 'answer'. Null for generate.",
    )
    language: str = Field(
        default="en",
        description="ISO language code for generated outputs (en/fr/de/es/it/zh).",
    )
    outputs: list[
        Literal[
            "clips", "linkedin", "quote_cards", "carousel", "summary", "blog"
        ]
    ] = Field(
        default_factory=lambda: [
            "clips",
            "linkedin",
            "quote_cards",
            "carousel",
            "summary",
            "blog",
        ],
        description="Which asset types the user wants to generate.",
    )
    clip_count: int | None = Field(
        default=None,
        description=(
            "Requested number of clips when 'clips' is in outputs. "
            "None means the caller should use its own default."
        ),
    )
    tone: Literal["professional", "thoughtLeadership", "conversational", "academic"] = (
        Field(default="professional", description="Detected tone preset.")
    )
    specific_instruction: str | None = Field(
        default=None,
        description="Free-form instruction distilled from the prompt.",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class InferIntentRequest(BaseModel):
    """Request body for intent inference."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(default="", description="User prompt or transcript paste.")
    filename: str | None = Field(
        default=None, description="Optional uploaded filename for extra context."
    )


class InferIntentResponse(BaseModel):
    """Response from intent inference."""

    intent: InferredIntent


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
    content_plan: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None


class AssetResponse(BaseModel):
    """Asset response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
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


class ClipRevision(BaseModel):
    """Revised clip metadata returned by the reviser agent.

    Replaces the old ``ClipScript`` / ``Shot`` model: the renderer now drives
    from ``render_spec`` and ASR captions, so revision only needs the hook,
    duration, titles, and music mood.
    """

    model_config = ConfigDict(extra="forbid")

    hook: str
    duration_seconds: int = Field(default=30, ge=5, le=120)
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
    start_seconds: float | None = Field(
        default=None,
        description="Exact start time in seconds (preferred over text markers)",
    )
    end_seconds: float | None = Field(
        default=None,
        description="Exact end time in seconds (preferred over text markers)",
    )
    summary: str = ""
    hook: str = ""
    virality_score: int = Field(default=50, ge=1, le=100)
    golden_quote: str = ""
    duration_seconds: int = Field(default=30, ge=5, le=120)


class ClipPlan(BaseModel):
    """A complete clip plan produced by the clip agent.

    Combines segment selection and script writing into one structure so that a
    single multimodal call can produce everything needed for ``Clip`` creation
    and ``render_spec`` building. ``to_segment`` keeps the existing segment
    path unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable identifier for this clip plan")
    source_text: str = Field(description="Original segment text from the talk")
    start_marker: str = Field(description="Approximate start location in source")
    end_marker: str = Field(description="Approximate end location in source")
    start_seconds: float | None = Field(
        default=None,
        description="Exact start time in seconds (preferred over text markers)",
    )
    end_seconds: float | None = Field(
        default=None,
        description="Exact end time in seconds (preferred over text markers)",
    )
    summary: str = ""
    hook: str = ""
    title: str = ""
    golden_quote: str = ""
    virality_score: int = Field(default=50, ge=1, le=100)
    duration_seconds: int = Field(default=30, ge=5, le=120)
    music_mood: str = "calm"
    # Music selection (see docs/MUSIC_ARCHITECTURE.md §8.3): the Clip Agent picks
    # one piece per clip. ``music_id`` is the Music row's UUID (string) — or, as a
    # robust fallback, a mood key (calm/uplifting/corporate) the orchestrator
    # resolves server-side. ``music_enabled``/``music_gain_db`` are per-clip
    # overrides; when ``music_id`` is unset the brand template default is used.
    music_id: str | None = None
    music_enabled: bool = True
    music_gain_db: float = -18.0
    visual_notes: str = ""
    title_options: list[str] = Field(default_factory=list)

    def to_segment(self) -> "Segment":
        return Segment(
            id=self.id,
            source_text=self.source_text,
            start_marker=self.start_marker,
            end_marker=self.end_marker,
            start_seconds=self.start_seconds,
            end_seconds=self.end_seconds,
            summary=self.summary,
            hook=self.hook,
            virality_score=self.virality_score,
            golden_quote=self.golden_quote,
            duration_seconds=self.duration_seconds,
        )


class ClipPlans(BaseModel):
    """Clip agent output: analysis + a list of ready-to-render clip plans."""

    model_config = ConfigDict(extra="forbid")

    overall_summary: str = ""
    core_arguments: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    target_audience: str = ""
    clips: list[ClipPlan] = Field(default_factory=list)


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
    SUMMARY = "summary"
    BLOG = "blog"


DerivativeContent = LinkedInPost | QuoteCardsResponse | CarouselResponse | Summary | BlogPost


def validate_derivative_content(
    derivative_type: DerivativeType,
    content: dict,
) -> dict:
    """Validate and normalize derivative content against its type schema.

    Returns a plain dict so it can be stored in the JSON column, but raises
    ``ValueError`` if the shape does not match the declared type.
    """
    mapping: dict[DerivativeType, type[BaseModel]] = {
        DerivativeType.LINKEDIN_POST: LinkedInPost,
        DerivativeType.QUOTE_CARD: QuoteCardsResponse,
        DerivativeType.CAROUSEL: CarouselResponse,
        DerivativeType.SUMMARY: Summary,
        DerivativeType.BLOG: BlogPost,
    }
    model = mapping.get(derivative_type)
    if model is None:
        return content
    return model.model_validate(content).model_dump(mode="json")


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

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # The Music row's UUID (string). Accepts a legacy ``track_id`` key on input so
    # existing render_spec JSON (pre-rename) still deserializes, but the init
    # param and serialized field are both ``music_id`` (see docs/MUSIC_ARCHITECTURE.md).
    music_id: str | None = Field(
        default=None, validation_alias=AliasChoices("music_id", "track_id")
    )
    url: str | None = None  # resolved track URL (storage seam); None = no track
    enabled: bool = False
    gain_db: float = -18.0


class GenerationContext(BaseModel):
    """Shared context passed to every content generation agent.

    Assembled once per generation run from the resolved speaker, brand
    template, tone settings, project metadata, and user instruction.
    """

    model_config = ConfigDict(extra="forbid")

    speaker: SpeakerContext | None = None
    event_name: str | None = None
    tone_settings: ToneSettings | None = None
    target_language: str = "en"
    instruction: str | None = None
    # Brand template's default music piece (Music.id as string); the Clip Agent
    # uses this as the default unless a clip's content suggests otherwise.
    brand_music_id: str | None = None


class DerivativePlan(BaseModel):
    """Per-output guidance produced by the Content Director."""

    model_config = ConfigDict(extra="forbid")

    derivative_type: DerivativeType
    focus: str = ""
    cta: str | None = None
    quote_candidates: list[str] = Field(default_factory=list)
    tone_override: str | None = None
    count: int | None = None


class ContentPlan(BaseModel):
    """Top-level content plan shared across all agent executors."""

    model_config = ConfigDict(extra="forbid")

    core_thesis: str
    themes: list[str] = Field(default_factory=list)
    target_audience: str = ""
    key_arguments: list[str] = Field(default_factory=list)
    derivatives: list[DerivativePlan] = Field(default_factory=list)
    quote_candidates: list[str] = Field(default_factory=list)
    overall_summary: str = ""


class ClipDub(BaseModel):
    """Cloned-voice dubbed speech; when enabled, replaces the source's audio."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = None  # resolved dub audio URL (storage seam)
    enabled: bool = False
    gain_db: float = 0.0


class IntroOutroCard(BaseModel):
    """Intro/outro brand card: text, image, or a short video."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text", "image", "video"] = "text"
    text: str | None = None  # kind == "text"
    media_url: str | None = None  # kind == "image" | "video" (storage-seam URL)


class ClipBrand(BaseModel):
    """Resolved brand values baked into the spec at generation time.

    Renderer-agnostic data (no DB ref): the API resolves the latest
    ``BrandTemplate`` config into these fields so the render service / preview
    never need DB access. ``None`` = renderer falls back to its default look.
    """

    model_config = ConfigDict(extra="forbid")

    caption_color: str | None = None  # hex; overrides the default white caption
    caption_size: int | None = None  # px; overrides the default caption size
    caption_font: str | None = None  # font key: lilita/inter/playfair/source-serif
    intro: IntroOutroCard | None = None  # opening card (None = no intro)
    outro: IntroOutroCard | None = None  # closing card (None = no outro)
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

    @field_validator("content", mode="before")
    @classmethod
    def _validate_content(cls, value: Any, info: ValidationInfo) -> Any:
        derivative_type = info.data.get("type")
        if derivative_type is None or not isinstance(value, dict):
            return value
        return validate_derivative_content(derivative_type, value)


class DerivativeUpdate(BaseModel):
    """Partial update for a derivative."""

    content: dict | None = None
    status: str | None = None


class GenerateRequest(BaseModel):
    """Generate content request."""

    clip_count: int = Field(default=5, ge=1, le=10)
    outputs: list[
        Literal["clips", "linkedin", "quote_cards", "carousel", "summary", "blog"]
    ] = Field(
        default_factory=lambda: [
            "clips",
            "linkedin",
            "quote_cards",
            "carousel",
            "summary",
            "blog",
        ]
    )
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
    scope: Literal[
        "full", "hook", "clip", "linkedin", "quote_card", "translation", "render"
    ] = Field(
        default="full",
        description="Scope of the generation: full project or targeted revision.",
    )
    target_id: UUID | None = Field(
        default=None,
        description="Clip or derivative ID when scope is not 'full'.",
    )
    operation: Literal[
        "regenerate", "shorten", "lengthen", "translate", "render"
    ] = Field(
        default="regenerate",
        description="Operation to apply when scope is targeted.",
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


class WorkflowRunResponse(BaseModel):
    """Workflow run response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: WorkflowStatus
    current_step: str | None = None
    progress: int = Field(default=0, ge=0, le=100)
    error: str | None = None
    context: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ProjectResultsResponse(BaseModel):
    """Aggregated results for the project detail/results page."""

    model_config = ConfigDict(from_attributes=True)

    project: ProjectResponse
    prompt: str | None = None
    clips: list[ClipResponse] = Field(default_factory=list)
    derivatives: list[DerivativeResponse] = Field(default_factory=list)
    latest_job: WorkflowRunResponse | None = None


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


class LibraryItemType(StrEnum):
    """Asset types exposed by the library endpoint."""

    UPLOAD = "upload"
    CLIP = "clip"
    LINKEDIN = "linkedin"
    QUOTE = "quote"
    SUMMARY = "summary"


class LibraryItemResponse(BaseModel):
    """A single item in the asset library."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: LibraryItemType
    title: str
    project_id: UUID
    created_at: datetime
    preview: str | None = None
    download_url: str | None = None


# ---------------------------------------------------------------------------
# Music library (DB-backed AI-generated pieces; see docs/MUSIC_ARCHITECTURE.md).
# Audio bytes stay on disk under assets/music/{id}.<ext>; these schemas cover
# the metadata API surface only.
# ---------------------------------------------------------------------------


class MusicResponse(BaseModel):
    """A music library piece (metadata + stream URL; no audio bytes)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mood: str
    title: str
    ext: str
    url: str
    size_bytes: int
    duration_seconds: int | None = None
    prompt: str | None = None
    model: str | None = None
    license: str | None = None
    source_url: str | None = None
    attribution: str | None = None
    is_public: bool
    created_at: datetime


class MusicGenerateRequest(BaseModel):
    """Request body for on-demand music generation from a prompt."""

    model_config = ConfigDict(extra="forbid")

    prompt: str
    mood: str | None = None
    title: str | None = None
    is_instrumental: bool = True


class MusicMetadataUpdate(BaseModel):
    """Editable metadata fields for a music piece (PUT)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    license: str | None = None
    source_url: str | None = None
    attribution: str | None = None
    is_public: bool | None = None
