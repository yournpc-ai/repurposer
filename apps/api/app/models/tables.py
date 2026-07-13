"""SQLAlchemy table definitions."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.models.database import Base
from app.models.schemas import (
    AssetStatus,
    AssetType,
    DerivativeType,
    ProjectStatus,
    RenderStatus,
    WorkflowStatus,
)


def now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class User(Base):
    """User account.

    The MVP ships without a login UI: a seeded default user owns all data.
    When real authentication is added, ``email`` becomes unique and a password
    hash / OAuth fields can be appended without changing the public API.
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Speaker(Base):
    """Speaker table.

    A speaker is a project-level memory of a talk's voice, style, and content
    strategy. Style and content memory are stored as flat columns; the
    ``persona`` summary is rendered at the agent layer when needed.
    """

    __tablename__ = "speakers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    title = Column(String(255), nullable=True)
    language = Column(String(10), default="zh")
    avatar_url = Column(String(512), nullable=True)
    core_values = Column(JSON, nullable=True, default=list)
    favorite_metaphors = Column(JSON, nullable=True, default=list)
    sentence_style = Column(String(255), nullable=True)
    emotional_tone = Column(String(20), nullable=True)
    typical_hooks = Column(JSON, nullable=True, default=list)
    avoid_words = Column(JSON, nullable=True, default=list)
    voice = Column(String(255), nullable=True)
    audience = Column(String(255), nullable=True)
    guidelines = Column(Text, nullable=True)
    cta = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Project(Base):
    """Project table."""

    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    speaker_id = Column(UUID(as_uuid=True), ForeignKey("speakers.id"), nullable=True)
    title = Column(String(255), nullable=False)
    event_name = Column(String(255), nullable=True)
    language = Column(String(10), default="zh")
    status = Column(Enum(ProjectStatus), default=ProjectStatus.DRAFT)
    tone_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Asset(Base):
    """Asset table.

    Assets belong to a user and are optionally attached to a project or a
    speaker. The user_id denormalisation lets the storage layer enforce
    ownership without joining projects/speakers on every file read.
    """

    __tablename__ = "assets"

    __table_args__ = (
        CheckConstraint(
            "project_id IS NOT NULL OR speaker_id IS NOT NULL",
            name="ck_asset_owner_set",
        ),
        CheckConstraint(
            "NOT (project_id IS NOT NULL AND speaker_id IS NOT NULL)",
            name="ck_asset_owner_single",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    speaker_id = Column(UUID(as_uuid=True), ForeignKey("speakers.id"), nullable=True)
    type = Column(Enum(AssetType), nullable=False)
    file_url = Column(String(512), nullable=True)
    transcript = Column(Text, nullable=True)
    extracted_text = Column(Text, nullable=True)
    slide_pages = Column(JSON, nullable=True)
    processing_status = Column(
        Enum(AssetStatus), nullable=False, default=AssetStatus.PENDING
    )
    processing_error = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    # Processor extras (e.g. ASR word-level timestamps, detected language).
    meta = Column(JSON, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class BrandTemplate(Base):
    """Brand / video template configuration."""

    __tablename__ = "brand_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    config = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Clip(Base):
    """Generated clip table."""

    __tablename__ = "clips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    hook = Column(String(500), nullable=False)
    title_options = Column(JSON, default=list)
    music_mood = Column(String(50), default="calm")
    status = Column(String(50), default="generated")
    video_url = Column(String(512), nullable=True)
    duration = Column(Integer, default=30)
    language = Column(String(10), default="zh")
    source_segment = Column(JSON, nullable=True)
    # Vertical-clip render contract + job state (see docs/VIDEO_EDITOR.md).
    # render_status NULL = render not requested.
    render_spec = Column(JSON, nullable=True)
    render_status = Column(Enum(RenderStatus), nullable=True)
    render_error = Column(Text, nullable=True)
    srt_url = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Derivative(Base):
    """Derivative content table."""

    __tablename__ = "derivatives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    type = Column(Enum(DerivativeType), nullable=False)
    content = Column(JSON, nullable=False)
    language = Column(String(10), default="zh")
    image_url = Column(String(512), nullable=True)
    status = Column(String(50), default="generated")
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class WorkflowRun(Base):
    """Workflow run table."""

    __tablename__ = "workflow_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    status = Column(Enum(WorkflowStatus), default=WorkflowStatus.PENDING)
    current_step = Column(String(100), nullable=True)
    context = Column(JSON, default=dict)
    progress = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class ChatSession(Base):
    """A chat session scoped to a project or a specific result asset.

    Provides a unified conversation container for multi-turn editing. The same
    table supports project-level brainstorming and asset-level (clip/derivative)
    quick revisions.
    """

    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    asset_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    asset_type = Column(String(50), nullable=True)  # "clip" | "derivative"
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Message(Base):
    """A single message inside a chat session.

    Keeps chat history minimal: role, content, optional attachments, and a
    link to the workflow run that was triggered by this message (if any).
    Generation progress/status lives on WorkflowRun, not duplicated here.
    """

    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = Column(String(20), nullable=False)  # "user" | "assistant" | "system"
    content = Column(Text, nullable=True)
    attachments = Column(JSON, default=list)
    workflow_run_id = Column(UUID(as_uuid=True), ForeignKey("workflow_runs.id"), nullable=True)
    intent = Column(JSON, nullable=True)  # parsed LLM intent for this turn
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Music(Base):
    """Background music piece (DB-backed; audio bytes stay under ``assets/``).

    A dedicated table — not the ``Asset`` table — because music library items are
    global/shared resources: they don't belong to a single project or speaker
    (``Asset`` enforces ``project_id IS NOT NULL OR speaker_id IS NOT NULL``).

    Binding:
    - Platform/default pieces: ``generated_by_user_id = NULL``, ``is_public = True``.
    - User-generated pieces (MiniMax): ``generated_by_user_id = <user_id>``,
      ``is_public = True`` (enter the shared library).
    - Future user uploads (Phase 3): ``generated_by_user_id = <user_id>``,
      ``is_public = False`` until reviewed.

    ``file_path`` is relative to ``settings.asset_dir`` (e.g.
    ``"music/{music_id}.mp3"``). Audio bytes never live in the DB (ADR-011).

    ``mood`` is a unique natural key (``calm`` / ``uplifting`` / ``corporate``)
    kept for legacy compatibility — new code references pieces by ``id``.
    """

    __tablename__ = "music"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    mood = Column(String(50), nullable=False, unique=True)
    title = Column(String(255), nullable=False)
    ext = Column(String(8), nullable=False)
    file_path = Column(String(512), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    prompt = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)
    generation_id = Column(String(255), nullable=True)
    license = Column(String(100), nullable=True)
    source_url = Column(String(512), nullable=True)
    attribution = Column(Text, nullable=True)
    is_public = Column(Boolean, default=True, nullable=False)
    generated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)
