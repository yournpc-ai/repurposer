"""Pydantic models for Repurposer API."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AssetType(StrEnum):
    """Asset types."""

    VIDEO = "video"
    AUDIO = "audio"
    TRANSCRIPT = "transcript"
    SLIDES = "slides"
    IMAGE = "image"
    VOICE_SAMPLE = "voice_sample"
    PAST_MATERIAL = "past_material"


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
    emotional_tone: Literal["理性", "激情", "温和", "犀利", "幽默"] = "理性"
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

    speaker_id: UUID


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
    speaker_id: UUID
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
    processed_at: datetime | None = None
    created_at: datetime


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
    music_mood: str = "沉稳"
    virality_score: int | None = Field(default=None, ge=1, le=100)


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


class DerivativeType(StrEnum):
    """Derivative content types."""

    LINKEDIN_POST = "linkedin_post"
    QUOTE_CARD = "quote_card"
    CAROUSEL = "carousel"
    MULTILINGUAL_SCRIPT = "multilingual_script"


class GenerateRequest(BaseModel):
    """Generate content request."""

    clip_count: int = Field(default=3, ge=1, le=10)
    outputs: list[Literal["clips", "linkedin", "quote_cards"]] = Field(
        default_factory=lambda: ["clips", "linkedin", "quote_cards"]
    )
    tone_settings: ToneSettings | None = None


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
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    error: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
