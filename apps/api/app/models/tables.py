"""SQLAlchemy table definitions."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
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


class Speaker(Base):
    """Speaker table."""

    __tablename__ = "speakers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    title = Column(String(255), nullable=True)
    language = Column(String(10), default="zh")
    avatar_url = Column(String(512), nullable=True)
    persona = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Project(Base):
    """Project table."""

    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    speaker_id = Column(UUID(as_uuid=True), ForeignKey("speakers.id"), nullable=True)
    title = Column(String(255), nullable=False)
    event_name = Column(String(255), nullable=True)
    language = Column(String(10), default="zh")
    status = Column(Enum(ProjectStatus), default=ProjectStatus.DRAFT)
    tone_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Asset(Base):
    """Asset table."""

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


class Clip(Base):
    """Generated clip table."""

    __tablename__ = "clips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    hook = Column(String(500), nullable=False)
    script = Column(JSON, nullable=False)
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


class HumanFeedback(Base):
    """Human feedback table."""

    __tablename__ = "human_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    clip_id = Column(UUID(as_uuid=True), ForeignKey("clips.id"), nullable=False)
    scope = Column(String(50), nullable=False)
    reason = Column(String(50), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class BrandTemplate(Base):
    """Brand / video template configuration."""

    __tablename__ = "brand_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    config = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)
