"""SQLAlchemy table definitions."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.database import Base
from app.models.schemas import (
    AssetStatus,
    AssetType,
    ChannelAccountStatus,
    ChannelPlatform,
    ProjectStatus,
    PublicationState,
    RenderStatus,
    canonical_json_hash,
)


def now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(UTC)


class User(Base):
    """User account.

    Login is passwordless: a 6-digit email code (see ``services/auth.py``) is
    exchanged for a JWT. All product data is isolated per user; the seeded
    default user only owns shared default content (personas).
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=True)
    # 用户级设置 (ADR-117 §1 — persona brand/voice JSONB 的 user 级先例):
    # confirm_execution / confirm_credits ∈ {auto, ask}; NULL = 全默认（读容忍）.
    settings = Column(JSONB, nullable=True)
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


class Persona(Base):
    """Persona table (ADR-037/038 — the identity module, the single identity
    object).

    A persona is a project-level memory of the user's voice, style, and content
    strategy. Style and content memory are stored as flat columns; the voice
    (audio) and brand (skin) blocks are JSONB — NULL means Auto / the system
    default skin. ``auto_created_at`` marks a system-bootstrap persona (in
    place of any is_default boolean); ``calibrated_at`` records the last
    calibration.
    """

    __tablename__ = "personas"

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
    # Voice block (audio meaning only): {"kind":"cloned", voice_id,
    # sample_asset_id} | {"kind":"stock", stock_id} | NULL = Auto.
    voice = Column(JSONB, nullable=True)
    # Skin block: caption font/size/color/position/preset, title toggle +
    # position, intro/outro cards, logo, keyword highlighter. NULL = the
    # system default skin (app.memory.brand.DEFAULT_BRAND_CONFIG).
    brand = Column(JSONB, nullable=True)
    # Provenance ("what it learned from") — written by the persona flows.
    learned_from = Column(JSONB, nullable=True)
    calibrated_at = Column(DateTime(timezone=True), nullable=True)
    auto_created_at = Column(DateTime(timezone=True), nullable=True)
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
    persona_id = Column(UUID(as_uuid=True), ForeignKey("personas.id"), nullable=True)
    title = Column(String(255), nullable=False)
    event_name = Column(String(255), nullable=True)
    language = Column(String(10), default="zh")
    status = Column(Enum(ProjectStatus), default=ProjectStatus.DRAFT)
    tone_snapshot = Column(JSON, nullable=True)
    # Unconfirmed plan + original prompt from /projects/{id}/intent
    # (ProjectBrief shape). Cleared when /generate starts the run; its
    # presence on a draft project is what "awaiting confirmation" means.
    pending_brief = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Asset(Base):
    """Asset table.

    Assets belong to a user and are optionally attached to a project or a
    persona. The user_id denormalisation lets the storage layer enforce
    ownership without joining projects/personas on every file read.
    """

    __tablename__ = "assets"

    __table_args__ = (
        CheckConstraint(
            "project_id IS NOT NULL OR persona_id IS NOT NULL",
            name="ck_asset_owner_set",
        ),
        CheckConstraint(
            "NOT (project_id IS NOT NULL AND persona_id IS NOT NULL)",
            name="ck_asset_owner_single",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    persona_id = Column(UUID(as_uuid=True), ForeignKey("personas.id"), nullable=True)
    type = Column(Enum(AssetType), nullable=False)
    file_url = Column(String(512), nullable=True)
    # User-facing display name (defaults to the original upload filename);
    # the storage key in file_url stays an opaque unique identifier.
    title = Column(String(255), nullable=True)
    transcript = Column(Text, nullable=True)
    extracted_text = Column(Text, nullable=True)
    # User edit overlay (ADR-113 §1 + C4): the card writes HERE only — the
    # source layer (transcript/extracted_text) and meta.words stay untouched,
    # so an edit never reverse-computes timecodes. NULL = source shown as-is.
    edited_transcript = Column(Text, nullable=True)
    slide_pages = Column(JSON, nullable=True)
    processing_status = Column(
        Enum(AssetStatus), nullable=False, default=AssetStatus.PENDING
    )
    # 休眠素材 (ADR-102 §1): NULL = dormant — uploaded but nobody has asked
    # for the content (the worker's claim loop requires non-NULL, so a
    # dormant asset is never processed: discarded/materials cost zero).
    # Stamped by the ONLY two request seats: get_understanding's read
    # attempt (chat) and the run birthplace (production prerequisite).
    processing_requested_at = Column(DateTime(timezone=True), nullable=True)
    processing_error = Column(Text, nullable=True)
    attempt = Column(Integer, nullable=False, default=0)
    claim_token = Column(UUID(as_uuid=True))
    lease_until = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer, nullable=True)
    # Processor extras (e.g. ASR word-level timestamps, detected language).
    meta = Column(JSON, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    @property
    def display_name(self) -> str | None:
        """The user- and LLM-facing name — the original upload title, NEVER
        the storage key's generated basename (2026-09-24: the plan context
        derived its filename from ``file_url``, so the router echoed
        "xy_1-1790259951-fIsRRA.mp4" back to the user; 世界自证律 — the
        model can only quote the names the context actually carries). The
        key basename survives only as the no-title fallback (legacy rows)."""
        if self.title:
            return str(self.title)
        return self.file_url.rsplit("/", 1)[-1] if self.file_url else None


class PageReading(Base):
    """页面读本 (world-seat 存储层): one stored reading per (project, url).

    Both writers land here — the chat read tool's write-through fetch and
    the web_page capture chain (process_asset) — and the world seat
    (``app/tools/world.py:page_reading_for_url``) is the ONE read point.
    Snapshot semantics: the text is a capture AS OF ``fetched_at``, never
    a live-truth claim; a re-fetch is an explicit act (the user says the
    page changed → the read tool's ``refresh`` param), never an implicit
    TTL. Discussion links never become assets — this row is the
    persistence without the canvas presence. Cascades with the project.
    """

    __tablename__ = "page_readings"

    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # The seat key — world.normalize_page_url's canonical form (scheme/host
    # lowercased, fragment dropped, bare trailing slash stripped).
    url = Column(String(512), primary_key=True)
    text = Column(Text, nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)


class SourceSnapshot(Base):
    """One immutable capture of an asset's content (ADR-145, VIDEO_PROJECT §9).

    The permission + identity anchor for CompositionVersion source bindings:
    a refresh / re-transcript / replacement produces a NEW row; existing
    versions keep pinning the old digest. Rows are content-addressed facts —
    never updated in place. ``asset_id`` is nullable provenance (SET NULL:
    deleting the asset never destroys snapshots bound into works).
    """

    __tablename__ = "source_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id = Column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    # Birth-Chat provenance also covers prepared asset-less derivatives. It is
    # not an ownership boundary and never changes when a snapshot is reused.
    origin_project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind = Column(String(20), nullable=False)  # image | audio | web | video (speech later)
    # Immutable object key; the digest is of the bytes behind it.
    storage_key = Column(String(512), nullable=False)
    digest = Column(String(64), nullable=False)
    # Real media duration in source-time ticks (editing.timing.SOURCE_TIMEBASE);
    # NULL for static sources (images) — a static snapshot HAS no duration.
    duration_ticks = Column(BigInteger, nullable=True)
    meta = Column(JSONB, nullable=False, default=dict)
    captured_at = Column(DateTime(timezone=True), default=now_utc)


class UserSkill(Base):
    """An owner-scoped external Skill identity; built-ins stay in code."""

    __tablename__ = "user_skills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_user_skills_owner_name"),
    )


class SkillVersion(Base):
    """One immutable, owner-scoped external Skill package and review policy.

    ``references`` retains source text as untrusted evidence, including scripts
    which are never executable. ``media`` retains only content-addressed gallery
    identities; bytes stay in object storage and legacy NULL reads as no media.
    ``declared_inputs`` and ``policy`` are reviewed product declarations, not
    permissions inferred from external frontmatter.
    A database trigger rejects UPDATE/DELETE; new methods require a new row.
    """

    __tablename__ = "skill_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    skill_id = Column(
        UUID(as_uuid=True), ForeignKey("user_skills.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    owner_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version = Column(Integer, nullable=False)
    instructions = Column(Text, nullable=False)
    references = Column(JSONB, nullable=False, default=list)
    # Gallery media identities only; bytes live in content-addressed object
    # storage. NULL is the immutable legacy-row representation of no media.
    media = Column(JSONB, nullable=True)
    declared_inputs = Column(JSONB, nullable=False, default=list)
    capability_report = Column(JSONB, nullable=False, default=dict)
    policy = Column(JSONB, nullable=False, default=dict)
    source_uri = Column(Text, nullable=True)
    source_revision = Column(String(128), nullable=True)
    source_hash = Column(String(64), nullable=False)
    # Full immutable draft identity (source + reviewed declarations/policy).
    # Nullable only for rows born before this companion digest existed.
    version_digest = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        UniqueConstraint("skill_id", "version", name="uq_skill_versions_version"),
        UniqueConstraint("skill_id", "version_digest", name="uq_skill_versions_version_digest"),
    )


class Composition(Base):
    """A work's durable identity (ADR-145): one continuously-edited film.

    ``origin_project_id`` records the birth Chat but is NOT a permission or
    editing boundary (SET NULL: deleting the origin Chat never cascades into
    a work other Chats may still reference). ``current_version_id`` points at
    the head CompositionVersion; the FK is added post-hoc (circular with
    composition_versions) and the write door maintains it under the row lock.
    Composition deletion is a future explicit op — nothing in this slice
    deletes or cascades these rows.
    """

    __tablename__ = "compositions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    origin_project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = Column(String(255), nullable=False, default="")
    current_version_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class CompositionVersion(Base):
    """One immutable content version of a Composition (§2.1).

    Content lives in the four JSONB columns (settings/sources/scenes/
    timeline — shapes = app.editing.schemas.CompositionContent). Versions are
    append-only: ``version`` increments monotonically within a Composition,
    rows are never rewritten. ``request_id``+``request_digest`` are the write
    door's idempotency pair: a retry of the same request returns THIS row; the
    same key under a different payload is rejected (request_id is globally
    unique when present, so a create retry can never double-birth a work).
    """

    __tablename__ = "composition_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    composition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("compositions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    base_version_id = Column(UUID(as_uuid=True), nullable=True)
    schema_version = Column(Integer, nullable=False, default=1)
    settings = Column(JSONB, nullable=False, default=dict)
    creative_state = Column(JSONB, nullable=True)
    sources = Column(JSONB, nullable=False, default=list)
    scenes = Column(JSONB, nullable=False, default=list)
    timeline = Column(JSONB, nullable=False, default=dict)
    skill_provenance = Column(JSONB, nullable=True)
    content_digest = Column(String(64), nullable=False)
    request_id = Column(String(64), nullable=True)
    request_digest = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        UniqueConstraint("composition_id", "version", name="uq_composition_versions_version"),
        Index(
            "uq_composition_versions_request_id",
            "request_id",
            unique=True,
            postgresql_where=text("request_id IS NOT NULL"),
        ),
    )


class Output(Base):
    """Unified product row (ADR-030): clips and derivatives became types.

    A clip is the type carrying timeline semantics (``source_ref``) and the
    render pipeline (``render_spec``/``render_status``); derivatives are plain
    types. Type-specific content lives in ``payload`` guarded by
    OUTPUT_PAYLOAD_SCHEMAS; ``files`` holds produced artifacts
    (video/srt/image object keys); ``publishing`` is the distribution metadata
    home (title/description/hashtags/cover_image_url/topic).
    """

    __tablename__ = "outputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    type = Column(String(50), nullable=False)
    language = Column(String(10), default="zh")
    status = Column(String(50), default="generated")
    provenance = Column(String(20), nullable=False, default="real")
    payload = Column(JSONB, nullable=False, default=dict)
    files = Column(JSONB, nullable=False, default=dict)
    source_ref = Column(JSONB, nullable=True)
    render_spec = Column(JSONB, nullable=True)
    # ExportJob commits a completed video Output in its success transaction.
    render_status = Column(Enum(RenderStatus), nullable=True)
    score = Column(JSONB, nullable=True)
    # 质检裁决 (产物质量线期 3): the verify node's verdict —
    # {status: passed|needs_human, checks: [{id, ok, detail, cls}], attempt,
    # checked_at}. NULL = never verified (legacy rows / verify-less graphs).
    quality = Column(JSONB, nullable=True)
    publishing = Column(JSONB, nullable=False, default=dict)
    # work/version 两身份 (ADR-091, N-59): work_id = the work's physical
    # anchor — born fresh at first birth (the column default), INHERITED by
    # every recreation of the same logical product (wipe successors /
    # verify snapshot restores); publication + operations queries anchor
    # here, so a rerun never orphans them. Legacy rows backfilled work_id=id
    # (singleton works — their pre-ADR history already evaporated, honest).
    work_id = Column(UUID(as_uuid=True), nullable=False, default=uuid4, index=True)
    # Composition lineage (ADR-145): a video-family output pins the exact
    # CompositionVersion it was produced from (work_id = Composition.id).
    # NULL on every non-video row. Version rows are immutable and never
    # deleted, so the pins need no ondelete behavior; composition deletion is
    # a future explicit op that must reckon with delivered Outputs first.
    composition_id = Column(
        UUID(as_uuid=True), ForeignKey("compositions.id"), nullable=True, index=True
    )
    composition_version_id = Column(
        UUID(as_uuid=True), ForeignKey("composition_versions.id"), nullable=True
    )
    # 归档不变量 (ADR-091 §2, 可空时间戳律): NULL = active; stamped = archived
    # (read faces default-filter it; the row + its files + its journal chain
    # survive — 交付后的产物历史不可销毁，只可归档). Physical delete survives
    # ONLY for mid-production self-correction (verify bounce rounds — never
    # delivered, no history rights) and project deletion.
    archived_at = Column(DateTime(timezone=True), nullable=True)
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

    @property
    def spec_hash(self) -> str | None:
        """Chain-integrity hash of render_spec (ADR-032) — serialized into
        OutputResponse as the client's base_hash for operation batches."""
        if self.render_spec is None:
            return None
        return canonical_json_hash(self.render_spec)


class Conversation(Base):
    """A conversation scoped to a project or a specific result asset.

    Provides a unified conversation container for multi-turn editing. The same
    table supports project-level brainstorming and asset-level (clip/derivative)
    quick revisions.
    """

    __tablename__ = "conversations"

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
    # Server-owned tool history, not a second work model or client input.
    context = Column(JSONB, nullable=False, default=lambda: {"schema_version": 1, "items": []},
                     server_default='{"schema_version":1,"items":[]}')
    # Stamped from Accept-Language for worker-born speech and deterministic
    # chrome; plan/chat infer speech from user messages and history instead.
    ui_language = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class Message(Base):
    """A single message inside a conversation.

    Keeps chat history minimal: role, content, optional attachments, and a
    link to the workflow run that was triggered by this message (if any).
    MediaJob and ExportJob own their native execution status.
    """

    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)  # "user" | "assistant" | "system"
    content = Column(Text, nullable=True)
    attachments = Column(JSON, default=list)
    # Entity references selected in the composer.
    mentions = Column(JSONB, nullable=False, default=list, server_default="[]")
    # The canvas product this turn was pointed at ({id, label}, denormalized
    # like mentions): persisted so the rebuilt history honestly shows the
    # focus prefix row on the user message after a refresh.
    focus_output = Column(JSONB, nullable=True)
    # The opening user row's id for facts born inside that user turn. NULL on
    # legacy rows and independent trigger/material facts; no relationship is
    # inferred from transcript adjacency.
    turn_id = Column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    intent = Column(JSONB(none_as_null=True), nullable=True)  # Durable activity, tool receipt or delivery facts.
    # Turn identity (交互完整性批 A, 2026-09-17 — the minimal in-flight
    # contract): set ONLY on the user row that opens a chat turn — durable
    # from the turn's first beat (prepare's own commit), so "the message is
    # received" never again dies with the turn's outcome. NULL everywhere
    # else (assistant rows, legacy rows, non-turn seats). Values:
    # in_flight (the turn owns it — the trigger admission gate's read) →
    # settled (the turn's final commit stamps it) | failed (best-effort
    # failure/disconnect stamp) | cancelled (explicit Stop after a visible
    # reply/fact). A Stop with no visible reply deletes the whole Turn instead
    # of leaving a retracted tombstone.
    # A crashed turn's row AGES OUT of in_flight via the stale bound, never
    # holds the gate forever.
    turn_state = Column(String(20), nullable=True)
    # A question and its answer retain the same message identity.
    # none_as_null: Python None must persist as SQL NULL — the pending
    # predicate (question IS NOT NULL / answer IS NULL) depends on it.
    question = Column(JSONB(none_as_null=True), nullable=True)
    answer = Column(JSONB(none_as_null=True), nullable=True)
    # 建议谱系交互块 (ADR-099 §4, messages JSONB 模式同 intent/mentions):
    # non-blocking next-step options this assistant row offered —
    # [{id, label, description, recommended, source_turn, source_state}];
    # source_state is the stale-check snapshot (the grounded asset ids at
    # stamp time — directed validation, zero version counters). NEVER a
    # question (blocking = the question payload); lifecycle = the row's.
    suggestions = Column(JSONB, nullable=False, default=list, server_default="[]")
    # Server-generated structured additions: domain component references and
    # system notices, dispatched by kind. Never model prose or a spec dump.
    # Read-tolerant default [] on legacy rows.
    blocks = Column(JSONB, nullable=False, default=list, server_default="[]")
    # 点选引用 (ADR-099 §4): a user row that IS a suggestion pick carries
    # its structured ref {source_turn, suggestion_id} — the visible content
    # stays the picked label, the ref rides structured (mentions 模式同构).
    suggestion_ref = Column(JSONB(none_as_null=True), nullable=True)
    # Transcript 数组位置 (ADR-108): per-conversation monotonic, assigned by
    # alloc_message_seq at append time. 渲染序 = seq 序; created_at 只用于
    # 显示（时刻/耗时），永不参与排序。NULL = 数组化前的存量行（迁移已回填）。
    seq = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class MessageSeqCounter(Base):
    """Per-conversation transcript 数组序计数器 (ADR-108).

    Lives in its OWN table, never on the conversations row: a chat turn's
    transaction holds the conversations row lock from prepare on
    (ui_language stamping + first flush) for minutes, so an allocator
    UPDATE on that row from a fresh short session would self-deadlock
    against the very turn awaiting it. This table is touched ONLY by
    alloc_message_seq's short dedicated transactions.
    """

    __tablename__ = "message_seq_counters"

    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_seq = Column(BigInteger, nullable=False, default=0, server_default="0")


class MessageFeedback(Base):
    """Per-user evaluation (good / bad) on an assistant reply with frozen turn context."""

    __tablename__ = "message_feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_feedback_msg_user"),
        Index("ix_message_feedback_rating_created", "rating", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id = Column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rating = Column(String(8), nullable=False)  # "good" | "bad"
    reason = Column(Text, nullable=True)
    tags = Column(JSONB, nullable=False, default=list, server_default="[]")
    context_snapshot = Column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class Music(Base):
    """Background music piece (DB-backed; audio bytes stay in object storage).

    A dedicated table — not the ``Asset`` table — because music library items are
    global/shared resources: they don't belong to a single project or persona
    (``Asset`` enforces ``project_id IS NOT NULL OR persona_id IS NOT NULL``).

    Binding:
    - Platform/default pieces: ``generated_by_user_id = NULL``, ``is_public = True``.
    - Legacy user-generated pieces (MiniMax): ``generated_by_user_id = <user_id>``,
      ``is_public = True`` (enter the shared library).
    - Programmatic scores prepared for a user's work: ``generated_by_user_id = <user_id>``,
      ``is_public = False``.
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
    # ADR-121 B3: beat grid for film-cut snapping — {"bpm": …, "beats": [s…]},
    # computed once at seed/reconcile (tools/music/beats.py); NULL = never
    # analyzed → the spec builder skips the beat snap honestly.
    meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)




class VideoNarration(Base):
    """User-scoped speed-1.0 narration original and its measured alignment.

    A pre-submit occupancy row prevents duplicate calls across Chats. Fixed
    audio and subtitle facts commit independently of a Run transaction; an
    outcome-unknown row never replays the provider request automatically.
    """

    __tablename__ = "video_narrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content_hash = Column(String(64), nullable=False)
    voice_id = Column(String(255), nullable=False)
    language = Column(String(16), nullable=False)
    config_hash = Column(String(64), nullable=False)
    text = Column(Text, nullable=False)
    storage_key = Column(String(512), nullable=True)
    audio_digest = Column(String(64), nullable=True)
    duration_s = Column(Float, nullable=True)
    subtitle_file = Column(Text, nullable=True)
    subtitles = Column(JSONB, nullable=True)
    alignment_digest = Column(String(64), nullable=True)
    usage_characters = Column(Integer, nullable=True)
    trace_id = Column(String(255), nullable=True)
    status = Column(String(24), nullable=False, default="synthesizing")
    synthesis_execution_id = Column(String(128), nullable=True)
    owner_token = Column(String(128), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)

    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_video_narrations_user_hash"),
    )


class NarrationAlignment(Base):
    """One deterministic alignment of an immutable audio snapshot and exact script.

    READY rows are immutable facts referenced by CompositionVersions. Only the
    PENDING preparation state enters the worker; semantic annotation is a
    separate ALIGNED → READY write through the Chat tool.
    """

    __tablename__ = "narration_alignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    audio_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("source_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    text = Column(Text, nullable=False)
    text_digest = Column(String(64), nullable=False)
    audio_digest = Column(String(64), nullable=False)
    algorithm = Column(String(64), nullable=False)
    normalization_version = Column(String(64), nullable=False)
    provider = Column(String(64), nullable=False)
    model = Column(String(255), nullable=False)
    source_timebase = Column(Integer, nullable=False)
    timing_digest = Column(String(64), nullable=True)
    content_digest = Column(String(64), nullable=True)
    payload = Column(JSONB, nullable=False, default=dict)
    status = Column(String(16), nullable=False, default="PENDING", index=True)
    claim_token = Column(UUID(as_uuid=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "audio_snapshot_id",
            "text_digest",
            "algorithm",
            "normalization_version",
            "provider",
            "model",
            name="uq_narration_alignments_source_script_algorithm",
        ),
    )


class ChannelAccount(Base):
    """OAuth-connected social account (Distribution module — DISTRIBUTION.md §3.1).

    One row per (user, platform, platform_user_id). ``credentials_enc`` holds
    the token bundle with sensitive values Fernet-encrypted (ADR-031); only the
    Distribution service touches it. P1 exposes one account per platform in the
    UI; the schema already allows multiple.
    """

    __tablename__ = "channel_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(Enum(ChannelPlatform), nullable=False)
    platform_user_id = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False, default="")
    avatar_url = Column(String(1024), nullable=True)
    scopes = Column(JSONB, nullable=False, default=list)
    credentials_enc = Column(JSONB, nullable=False, default=dict)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(Enum(ChannelAccountStatus), nullable=False, default=ChannelAccountStatus.ACTIVE)
    last_refreshed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)

    __table_args__ = (
        UniqueConstraint("user_id", "platform", "platform_user_id", name="uq_channel_account_per_user"),
    )


class Publication(Base):
    """Publish order = state machine + idempotency + metrics headroom (§3.2).

    Single FK to ``outputs`` (ADR-030). ``payload`` is a frozen snapshot taken
    at creation — post-disconnect history stays readable and later output
    edits never sync into it. ``due_at`` is the worker's sole claim predicate
    (backoff rewrites it). ``ai_disclosure`` is derived by the publication
    classifier (ADR-026), never user-ticked. State moves only via
    ``services.distribution._transition``; the institutional audit table
    (``publication_events``) is deferred to P2.
    """

    __tablename__ = "publications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    output_id = Column(
        UUID(as_uuid=True),
        ForeignKey("outputs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    channel_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("channel_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    payload = Column(JSONB, nullable=False, default=dict)
    ai_disclosure = Column(Boolean, nullable=False, default=False)
    state = Column(Enum(PublicationState), nullable=False, default=PublicationState.SCHEDULED)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    claim_token = Column(UUID(as_uuid=True), nullable=True)
    dispatch_started_at = Column(DateTime(timezone=True), nullable=True)
    reconciliation = Column(JSONB, nullable=True)
    platform_job_id = Column(String(512), nullable=True)
    platform_post_id = Column(String(512), nullable=True)
    platform_post_url = Column(String(1024), nullable=True)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    metrics = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)

    __table_args__ = (
        Index(
            "ix_publications_claim",
            "state",
            "due_at",
            postgresql_where=text("state IN ('SCHEDULED', 'PUBLISHING')"),
        ),
        Index("ix_publications_user_state", "user_id", "state"),
    )


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_agent = Column(String(512), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True))


class Notification(Base):
    """User-facing notification (platform-layer table, MODULE_ARCHITECTURE §4).

    The bell dropdown is the event stream's presentation layer — thin events
    (publish succeeded/failed, channel expired; feature announcements later)
    surface here instead of growing dedicated pages. ``type`` is a plain
    string (not an enum) so new sources don't need migrations; ``payload``
    carries whatever the renderer needs (ids, platform, urls, error).
    """

    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    email_due_at = Column(DateTime(timezone=True))
    email_attempts = Column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        Index("ix_notifications_email_due", "email_due_at", postgresql_where=text("email_due_at IS NOT NULL")),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )


class Wallet(Base):
    """Credit wallet — one row per user (ADR-055, docs/BILLING.md §2).

    The wallet is its own aggregate root (deliberately no column on
    ``users``): lazy-opened on first login with the signup grant. ``balance``
    is only the materialized cache of the append-only ``credit_transactions``
    ledger — negative values are allowed by design (BILLING §5, no CHECK).
    ``version`` is the optimistic lock that keeps concurrent holds from
    over-drawing.
    """

    __tablename__ = "wallets"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    balance = Column(BigInteger, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class CreditTransaction(Base):
    """Credit ledger row (ADR-055) — append-only, the sole source of truth for
    every balance change; ``wallets.balance`` is only its materialized cache.

    ``kind`` is a plain string (Notification.type precedent — the payment
    adapter's ``purchase`` joins without a migration): grant | purchase | hold |
    capture | release | refund | adjust. ``amount`` is signed (hold/capture
    negative); ``balance_after`` chains each row to the balance it produced,
    so ledger drift is a one-query audit. ``idempotency_key`` is a
    first-class UNIQUE column. Job retries and payment webhook replays share
    the same ledger. The ref records the operation that caused the entry.
    """

    __tablename__ = "credit_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    amount = Column(BigInteger, nullable=False)
    balance_after = Column(BigInteger, nullable=False)
    ref = Column(JSONB, nullable=False, default=dict)
    idempotency_key = Column(String(128), nullable=False, unique=True)
    note = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc)


class PaymentOrder(Base):
    """One fiat credit-package purchase (PAYMENTS §4).

    Stripe owns the payment fact; this row owns the internal order snapshot
    and its exactly-once link to the credits ledger. Money stays in minor
    units here and never leaks into ``credit_transactions``.
    """

    __tablename__ = "payment_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    package_key = Column(String(40), nullable=False)
    provider = Column(String(20), nullable=False, default="stripe")
    livemode = Column(Boolean, nullable=False)
    amount_minor = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False)
    credits = Column(BigInteger, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    provider_checkout_session_id = Column(String(255), nullable=True)
    provider_payment_intent_id = Column(String(255), nullable=True)
    credit_transaction_id = Column(
        UUID(as_uuid=True), ForeignKey("credit_transactions.id"), nullable=True
    )
    paid_at = Column(DateTime(timezone=True), nullable=True)
    credited_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)

    __table_args__ = (
        CheckConstraint("amount_minor >= 0", name="ck_payment_orders_amount_nonnegative"),
        CheckConstraint("credits > 0", name="ck_payment_orders_credits_positive"),
        UniqueConstraint(
            "provider_checkout_session_id", name="uq_payment_orders_checkout_session"
        ),
        UniqueConstraint(
            "credit_transaction_id", name="uq_payment_orders_credit_transaction"
        ),
        Index("ix_payment_orders_user_created_at", "user_id", "created_at"),
    )


class PaymentWebhookEvent(Base):
    """Durable payment-provider delivery receipt and asynchronous alert outbox.

    Verified provider events have one row per event id; rejected public calls
    use hourly aggregate rows with NULL event_id to bound unauthenticated
    writes. This table never grants credits and is not a financial ledger.
    """

    __tablename__ = "payment_webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider = Column(String(20), nullable=False, default="stripe")
    dedupe_key = Column(String(255), nullable=False, unique=True)
    event_id = Column(String(255), nullable=True, unique=True)
    event_type = Column(String(100), nullable=True)
    livemode = Column(Boolean, nullable=True)
    # Audit identifiers intentionally survive unknown or deleted orders.
    order_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    checkout_session_id = Column(String(255), nullable=True, index=True)
    payload_hash = Column(String(64), nullable=False)
    signature_valid = Column(Boolean, nullable=False)
    status = Column(String(20), nullable=False)  # processing | processed | ignored | failed
    reason_code = Column(String(100), nullable=True)
    response_status = Column(Integer, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=1)
    first_received_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    last_received_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    alert_status = Column(String(20), nullable=True)  # NULL | pending | sending | sent | failed
    alert_attempt_count = Column(Integer, nullable=False, default=0)
    alert_next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    alert_claim_token = Column(UUID(as_uuid=True), nullable=True)
    alert_started_at = Column(DateTime(timezone=True), nullable=True)
    alerted_at = Column(DateTime(timezone=True), nullable=True)
    alert_last_error = Column(String(500), nullable=True)

    __table_args__ = (
        CheckConstraint("attempt_count >= 1", name="ck_payment_webhook_attempts_positive"),
        CheckConstraint("alert_attempt_count >= 0", name="ck_payment_webhook_alert_attempts"),
        Index(
            "ix_payment_webhook_events_alert_due",
            "alert_status",
            "alert_next_attempt_at",
        ),
        Index(
            "ix_payment_webhook_events_first_received_at",
            "first_received_at",
        ),
    )


class ConversationUsage(Base):
    """One conversation turn's LLM token usage (ADR-117 D3) — the COGS
    ledger for the conversation layer: metered, NEVER billed (the
    conversation layer is free to the user), never on any bill or UI.

    One row per turn — the tool loop's iterations aggregate in memory
    (``app.metering.bind_conversation_turn``) and fold into this row with
    the turn's assistant message in ONE commit (the billing write
    discipline). ``cost_usd`` uses accumulated per-call actual cost when the
    provider has cache/time-dependent pricing, otherwise the owning provider's
    token price at fold time; it never drifts after the row is written.
    ``cached_tokens`` records the provider's prefix-cache hit report when
    it returns one (NULL = the provider said nothing). ``project_id`` is
    nullable for project-less conversation surfaces. Uses: COGS visibility
    (per-user conversation/production cost ratio), the W11 fair-use quota
    data base, and the context-budget calibration source (token
    distribution per turn family).
    """

    __tablename__ = "conversation_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    prompt_tokens = Column(BigInteger, nullable=False)
    completion_tokens = Column(BigInteger, nullable=False)
    cached_tokens = Column(BigInteger, nullable=True)
    cost_usd = Column(Float, nullable=False)
    model = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("ix_conversation_usage_user_created", "user_id", "created_at"),
        Index("ix_conversation_usage_project_created", "project_id", "created_at"),
    )


class Config(Base):
    """Public operating parameter (ADR-055) — the ``configs`` table.

    ``CONFIG_REGISTRY`` (app/platform/configs.py) is the sole source of truth
    for the key set / defaults / types / descriptions; rows here are only the
    override carrier, reconciled at startup. Keys use dotted namespaces
    (``credits.per_cost_usd``). All reads funnel through ``get_config()`` —
    modules never query this table directly. Boundary rule: operating
    parameters (changing them must not require a deploy) live here;
    engineering parameters (a wrong value breaks the deployment — DSNs,
    secrets, DB fuses) stay in env ``app/config.py``.
    """

    __tablename__ = "configs"

    key = Column(String(128), primary_key=True)
    value = Column(JSONB, nullable=False)
    description = Column(String(512), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=now_utc)


class ExportJob(Base):
    """One native export of one observed version. The job id is also the reserved Output id."""

    __tablename__ = "export_jobs"
    id = Column(UUID(as_uuid=True), primary_key=True)
    receipt_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), unique=True, nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    version_id = Column(UUID(as_uuid=True), ForeignKey("composition_versions.id"), nullable=False)
    render_spec = Column(JSONB, nullable=False)
    authorized_credits = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False)
    attempt = Column(Integer, nullable=False, default=0)
    claim_token = Column(UUID(as_uuid=True))
    lease_until = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (Index("ix_export_jobs_queue", "status", "created_at"),)


class MediaJob(Base):
    """One authorized generation. The native receipt holds its opening and final media facts."""

    __tablename__ = "media_jobs"
    id = Column(UUID(as_uuid=True), primary_key=True)
    receipt_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), unique=True, nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    kind = Column(String(24), nullable=False)
    request = Column(JSONB, nullable=False)
    authorized_credits = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False)
    attempt = Column(Integer, nullable=False)
    claim_token = Column(UUID(as_uuid=True))
    lease_until = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    __table_args__ = (Index("ix_media_jobs_queue", "kind", "status", "created_at"),)
