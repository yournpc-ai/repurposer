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
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.database import Base
from app.models.schemas import (
    AssetStatus,
    AssetType,
    ProjectStatus,
    RenderStatus,
    WorkflowStatus,
)


def now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class User(Base):
    """User account.

    Login is passwordless: a 6-digit email code (see ``services/auth.py``) is
    exchanged for a JWT. All product data is isolated per user; the seeded
    default user only owns shared demo content.
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class VerificationCode(Base):
    """Email verification code for passwordless login."""

    __tablename__ = "verification_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


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


class WorkflowRun(Base):
    """Workflow run table — run-level state machine only.

    Per-step state lives in plan_nodes (RunPlan); ``context`` is the task
    book (normalized intent), ``progress`` aggregates node states. The retired
    current_step string is gone (query running nodes instead).
    """

    __tablename__ = "workflow_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    status = Column(Enum(WorkflowStatus), default=WorkflowStatus.PENDING)
    context = Column(JSON, default=dict)
    progress = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class PlanNode(Base):
    """RunPlan node: one step of a run's execution plan (ADR-028).

    The plan graph is materialized at run creation by the orchestrator —
    topology is code-determined, never LLM-chosen. ``inputs`` is the edge list
    (upstream node ids); ``spec`` carries DB-opaque params (instruction,
    language, counts, target ids); ``output_refs`` lists produced outputs rows;
    ``cost`` is the per-node metering ledger (ADR-025, written by
    services/metering.py). Node status transitions are row-level writes — the
    retired run-context JSON blob + process lock is gone.
    """

    __tablename__ = "plan_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    seq = Column(Integer, nullable=False, default=0)
    # DAG edges: list of upstream node ids (str UUID).
    inputs = Column(JSONB, nullable=False, default=list)
    spec = Column(JSONB, nullable=False, default=dict)
    # Produced outputs row ids (str UUID).
    output_refs = Column(JSONB, nullable=False, default=list)
    # {prompt_tokens, completion_tokens, fixed_cost} — metering ledger.
    cost = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)
    attempt = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)

    __table_args__ = (
        Index("ix_plan_nodes_run_status", "run_id", "status"),
        Index("ix_plan_nodes_kind_status", "kind", "status"),
    )


class Output(Base):
    """Unified product row (ADR-030): clips and derivatives became types.

    A clip is the type carrying timeline semantics (``source_ref``) and the
    render pipeline (``render_spec``/``render_status``); derivatives are plain
    types. Type-specific content lives in ``payload`` guarded by
    OUTPUT_PAYLOAD_SCHEMAS; ``files`` holds produced artifacts
    (video/srt/image object keys); ``publishing`` is the distribution metadata
    home (title/description/hashtags/cover_image_url/topic); ``plan_node_id``
    is read-only lineage back to the producing node.
    """

    __tablename__ = "outputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    plan_node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("plan_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type = Column(String(50), nullable=False)
    language = Column(String(10), default="zh")
    status = Column(String(50), default="generated")
    provenance = Column(String(20), nullable=False, default="real")
    payload = Column(JSONB, nullable=False, default=dict)
    files = Column(JSONB, nullable=False, default=dict)
    source_ref = Column(JSONB, nullable=True)
    render_spec = Column(JSONB, nullable=True)
    # render_status NULL = render not requested (worker claim predicate).
    render_status = Column(Enum(RenderStatus), nullable=True)
    # render_status claim write-set companion (ADR-030 rule 2 — read together
    # with render_status everywhere; falls back into payload if review objects).
    render_error = Column(Text, nullable=True)
    score = Column(JSONB, nullable=True)
    publishing = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)

    __table_args__ = (
        Index("ix_outputs_project_type", "project_id", "type"),
        Index(
            "ix_outputs_render_status",
            "render_status",
            postgresql_where=text("render_status IS NOT NULL"),
        ),
    )


class ChatSession(Base):
    """A chat session scoped to a project or a specific result asset.

    Provides a unified conversation container for multi-turn editing. The same
    table supports project-level brainstorming and asset-level (clip/derivative)
    quick revisions.
    """

    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
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
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)  # "user" | "assistant" | "system"
    content = Column(Text, nullable=True)
    attachments = Column(JSON, default=list)
    workflow_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    intent = Column(JSON, nullable=True)  # rule-classified intent for this turn (LLM parser app/agents/intent.py is not yet wired into chat)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Music(Base):
    """Background music piece (DB-backed; audio bytes stay in object storage).

    A dedicated table — not the ``Asset`` table — because music library items are
    global/shared resources: they don't belong to a single project or speaker
    (``Asset`` enforces ``project_id IS NOT NULL OR speaker_id IS NOT NULL``).

    Binding:
    - Platform/default pieces: ``generated_by_user_id = NULL``, ``is_public = True``.
    - User-generated pieces (MiniMax): ``generated_by_user_id = <user_id>``,
      ``is_public = True`` (enter the shared library).
    - Future user uploads (Phase 3): ``generated_by_user_id = <user_id>``,
      ``is_public = False`` until reviewed.

    ``file_path`` is an object storage key (e.g. ``"music/{music_id}.mp3"``).
    Audio bytes never live in the DB.

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
