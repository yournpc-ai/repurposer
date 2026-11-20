"""The plan path's tool-loop runner (ADR-077 判词② — T2a 内核半边).

The retired ``_plan_turn`` dispatch, re-homed: the intent router
closes its turn with ONE terminal tool call — the four actions' mechanical
translation (draft → ``present_plan``, ask → ``ask_user``, start →
``start_run``, answer → ``answer``) — and the guardrails live INSIDE the
tool executions:

- 出书门槛 = ``present_plan``'s in-execution validation (media without
  material / rootless + topic unasked → a REJECTION whose feedback names
  the right tool; rootless after the topic was asked → an accept carrying
  the code-composed draft-from-persona declaration);
- ``start_run`` still runs through ``answer_question`` → ``create_run`` —
  the only run birthplace, zero bypass, with the outer Turn owning its commit;
- chain adjudication (``validate_task_list`` / ``check_transform_targets``)
  rejections ARE the loop's feedback — the retired funnel repair round's
  seat, now one bounded iteration each.

A rejected call writes nothing. An accepted call's writes are flush-only —
the caller commits, including ``start_run``: its deferred answer/Run/hold writes
pass the outer opening-row Stop fence before the one final commit. The envelope absorb (declared-material promotion + brief merge +
the pending-slot handshake) is idempotent per turn: it may run on several
iterations, it writes at most once, and every gate reads the ONE merged
brief (出书决策只看 brief).

Storage shapes preserved: docked rows and ``message.intent`` still carry
``InferredIntent`` dumps (built here from the accepted call's params plus
the turn's prose), and an ask turn's brief-only ``pending_brief`` row is
byte-identical. The 判词⑦ hybrid-flip machinery retired structurally — a
tool call IS one action; the impossible hybrid shapes have no wire form
anymore (their outcomes survive as rejections).

T2b 感知族 (ADR-077 判词②): the read tools (``app/chat/perception/``)
dispatch straight from ``execute`` — never a brief write, never an
outcome — and ride back as a ToolObservation the loop feeds back.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.tools.video.design import CompositionDesignVideoArgs

from app.agents.candidate_correction import CandidateRejected, CandidateScope, RestoredCandidate
from app.agents.tool_loop import (
    RoundAssembly,
    TerminalRefusal,
    ToolObservation,
)
from app.agents.tool_loop import (
    ToolRejected as LoopToolRejected,  # alias: app.tools.ToolRejected (the
    # chain-adjudication exception, imported below) shadows the loop event's
    # name in this module — the retract seat must match the LOOP's class
)
from app.agents.working_drafts import WorkingDraftRejected, WorkingDraftUpdated
from app.chat.deferred_frames import DeferredFrames
from app.chat.intent import intent_router
from app.providers.llm.base import LLMError
from app.chat.perception import PERCEPTION_TOOLS, run_perception_tool
from app.chat.perception.executes import speaker_form_lines, understanding_digest_lines
from app.chat.service import (
    _active_run_line,
    _ask_content,
    _auto_start_docked_plan,
    _bare_question,
    _cannot_do_text,
    _compute_plan_reasons,
    _create_message,
    _design_no_progress_text,
    _dock_question,
    _draft_from_persona_echo,
    _interim_prose_callback,
    _loop_incomplete_text,
    _needs_media,
    _prefers_zh,
    _reminder_block,
    _safe_task_estimate,
    _sfx_import_failure_text,
    _topic_gate_question,
    _video_capability_text,
    _video_review_failure_text,
    answer_question,
    is_pending_plan,
    latest_pending_question,
    merge_brief,
    resolve_confirmation_need,
    resolve_suggestion_note,
    sync_plan_question,
)
from app.chat.turn_tools import video_rejection_stop
from app.models.schemas import (
    AnnotateNarrationArgs,
    AnswerPayload,
    AssetStatus,
    AssetType,
    Brief,
    BriefSlot,
    BriefSlotSource,
    ChatRequest,
    CreativeState,
    EditGraphArgs,
    GetNarrationAlignmentArgs,
    ImportSfxArgs,
    InferredIntent,
    MaterialUnderstanding,
    PendingPlan,
    PlanAnswerArgs,
    PlanAskArgs,
    PrepareNarrationArgs,
    PresentPlanArgs,
    QuestionPayload,
    QuestionProposal,
    ReviewVideoArgs,
    SearchSfxArgs,
    SelectMusicArgs,
    SelectVideoPresetArgs,
    ShowMusicCandidatesArgs,
    ShowVideoPresetsArgs,
    SkillReference,
    StartAnswerRequest,
    StartRunArgs,
    missing_brief_question_items,
    question_group_digest,
    resolve_recommended_id,
)
from app.models.tables import Asset, Message, Persona, Project, User
from app.pipeline.asset_processing import has_any_text_material
from app.pipeline.assets import (
    asset_text_content,
    create_transcript_asset_from_text,
    create_web_page_assets_committed_from_urls,
    prime_web_page_captures_from_text,
)
from app.platform.project_context import resolve_default_persona
from app.platform.user_settings import read_confirmation_prefs
from app.tools import ToolRejected, validate_task_list

logger = structlog.get_logger()

# The return shape the service layer's callers hold (unchanged):
# (assistant message, started run id, answered task-book question,
# cascade-bailed run ids). The assistant message is None when the turn
# closes without a row (the degrade paths land their own shape).
PlanTurnOutcome = tuple[Message | None, UUID | None, Message | None, list[UUID]]


class PlanTurn:
    """One plan-path turn: the pre-call assembly, the four tool executions,
    and the outcome mapping. Created by ``run_plan_turn``; one instance per
    turn (the idempotency guards are its fields)."""

    def __init__(
        self,
        db: AsyncSession,
        user_id: UUID,
        conversation,
        project: Project,
        request: ChatRequest,
        skill: SkillReference | None = None,
        skill_ambiguity: list[str] | None = None,
        on_phase=None,
        on_activity=None,
        on_candidates=None,
        on_row_append=None,
        turn_id: UUID | None = None,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.turn_id = turn_id
        self.media_journey: dict | None = None
        self.media_state: dict | None = None
        self.media_visual_results: list[dict] = []
        self.media_resume_pending: PendingPlan | None = None
        self.media_resume_narration: list[dict] | None = None
        self.media_start_blocker: str | None = None
        self.media_start_rejections = 0
        self.media_image_blocked_scene: int | None = None
        self.conversation_id = UUID(str(conversation.id))
        self.project = project
        self.request = request
        self.skill = skill
        self.skill_ambiguity = skill_ambiguity or []
        self.on_phase = on_phase
        # 工作会话里程碑通道 (iter-2 ⑥): the SSE pump's projector feed —
        # called at the exploration door's successes; None = the one-shot
        # path (no stream, no frames).
        self.on_activity = on_activity
        self.on_candidates = on_candidates
        # Retired with the program-markdown publication (2026-10-18 裁决):
        # the design beat no longer lands its own row mid-turn — the
        # presenting model's ONE message carries the board. The param stays
        # for the runner's signature parity (the channel is generic).
        self.on_row_append = on_row_append
        # 视频呈现挂号 (ADR-145 phase B): a successful design_video /
        # A saved-version presentation keeps its exact read here;
        # finish stamps the receipt (pending_brief.video_presentation, with
        # the terminal row's id) and attaches the storyboard block to that
        # row — only after the row actually persists. The write door
        # committed on its own session already; this turn's transaction
        # carries only the receipt + the message block.
        self._video_presentation_pending: dict | None = None
        # Per-turn idempotency counter for the video write door's
        # request_id (a repair-loop retry of the SAME call replays; distinct
        # calls mint distinct ids).
        self._video_call_counter: int = 0
        # Turn state (filled by the assembly below and the executions):
        self.text = ""
        self.stored: PendingPlan | None = None
        self.pending_q: Message | None = None
        self.plan_pending = False
        self.assets: list[Asset] = []
        self.has_text_material = False
        self.persona: Persona | None = None
        # (execution, credits) — the turn's confirmation prefs (ADR-117 D1),
        # loaded in assemble; default ("auto", "auto") until then.
        self.confirmation: tuple[str, str] = ("auto", "auto")
        self.infer_kwargs: dict[str, Any] = {}
        # Loop state:
        self.material_asset: Asset | None = None
        self.merged_brief: Brief | None = None
        self.settled_pending: Message | None = None
        self.outcome: PlanTurnOutcome | None = None
        self.saw_rootless_rejection = False
        self.echo_override: str | None = None
        self.reasons_extra: list[str] = []
        # 资产角色 (ADR-078 判词④): this turn's mention-settled exemplar pin
        # (None = no asset mention this turn — the stored plan's pins ride).
        self.mention_exemplar_id: str | None = None
        self.deferred: DeferredFrames | None = None
        # 建议点选 provenance (ADR-099 §4): this turn's message IS a
        # suggestion pick → the resolution note rides into the router's
        # message (never into self.text — the gates and keyword detectors
        # read the user's own words only).
        self.suggestion_note: str | None = None

    # ---- assembly (the retired _plan_turn's pre-call block, verbatim) ------

    def _current_pending(self) -> PendingPlan | None:
        """The ONE current-PendingPlan seat for this turn. The plan path's
        loop is non-terminal through design_video, so a dock/re-dock seat
        reads the version that beat just persisted, never the assembly snapshot."""
        self.stored = (
            PendingPlan.model_validate(self.project.pending_brief)
            if isinstance(self.project.pending_brief, dict)
            else self.media_resume_pending
        )
        return self.stored

    async def assemble(self, recent: list[Message] | None) -> None:
        db, project, request = self.db, self.project, self.request
        text = request.message
        if not text.strip() and request.attachments:
            # Attachment-only turn (files staged in the overlay's input group,
            # sent with no text): the persisted user message stays empty (the
            # chips carry the record), but the inference needs honest words —
            # the files themselves are listed in the Assets context block.
            names = ", ".join(a.name for a in request.attachments)
            text = (
                f"(I just attached new source files: {names}. "
                "No note — treat them as material for what I asked, or ask what "
                "I'd like made from them.)"
            )
        self.text = text

        # 建议点选落地解算 (ADR-099 §4): a pick-carrying request resolves
        # its provenance NOW — the note (fresh = the control event named;
        # stale = WHAT moved + re-grounding advice) rides the router-facing
        # message below; an unresolvable ref simply yields no note.
        if request.suggestion_ref is not None:
            self.suggestion_note = await resolve_suggestion_note(
                db,
                self.conversation_id,
                UUID(str(project.id)),
                request.suggestion_ref,
            )

        stored = self._current_pending()
        # ADR-052 B2 D2-C2: the accumulated prompt narrative is retired — the
        # brief is the dialog's structured state (code-merged), and this
        # turn's message is judged on its own words. The archive already holds
        # each turn as its own user message; stored.prompt stays the birth
        # prompt, frozen at the first dock (never re-accumulated).

        # 插话支持 (ADR-053 R2): a still-open plain question rides the router's
        # context explicitly (the pending block) — a user-stated proposal for
        # ITS slot is the answer (code settles the row in the absorb below),
        # anything else is an interjection (the question stays open and the
        # answer tool's reply gets the reminder tail). A pending task_book is
        # this path's own confirmation target (G-1), never a judgment subject.
        pending_q = await latest_pending_question(db, self.conversation_id)
        # Remember a pending task_book before the null below: raising a fresh
        # plain question would supersede the plan row and orphan the
        # confirmation (S5, 2026-09-12) — the ask_user execution rejects
        # while either kind is pending.
        self.plan_pending = (
            pending_q is not None
            and pending_q.workflow_run_id is None
            and (pending_q.question or {}).get("kind") == "task_book"
        )
        if pending_q is not None and (
            pending_q.workflow_run_id is not None
            or (pending_q.question or {}).get("kind") != "question"
        ):
            pending_q = None
        self.pending_q = pending_q

        await prime_web_page_captures_from_text(
            UUID(str(project.id)), self.user_id, text, turn_id=self.turn_id
        )
        assets = list(
            (
                await db.execute(
                    select(Asset)
                    .where(
                        Asset.project_id == project.id,
                        # A captured page has no bytes by design (file_url
                        # stays NULL) yet IS attached material — the film
                        # family's whole input.
                        or_(
                            Asset.file_url.isnot(None),
                            Asset.type == AssetType.WEB_PAGE,
                        ),
                    )
                    # Deterministic "first asset" for filename/excerpt picks —
                    # the repo convention (jobs.py / projects.py).
                    .order_by(Asset.created_at)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        self.assets = assets
        first_file = next((a for a in assets if a.file_url), None)
        filename = first_file.display_name if first_file else None
        # Multi-asset block (ADR-078): with ≥2 files the router must SEE the
        # roster to judge the remix shape (which is the user's material, which
        # the reference) — the single-file filename/excerpt surface stays for
        # the common case; this lists every file in upload order.
        asset_lines: list[str] | None = None
        if len(assets) > 1:
            lines = []
            for a in assets:
                name = a.display_name or "(text)"
                kind_bits = [a.type.value]
                if a.duration_seconds:
                    kind_bits.append(f"{int(a.duration_seconds)}s")
                lang = (a.meta or {}).get("language")
                if lang:
                    kind_bits.append(str(lang))
                lines.append(f"- {name} ({' · '.join(kind_bits)})")
            asset_lines = lines
        # 资产角色 mention 结算 (判词④ — code settles, the LLM never pins):
        # an @asset mention on the PLAN path names the EXEMPLAR ("做成
        # @这个 那样" — the mentioned video is the reference whose craft the
        # run mirrors). The latest mention wins a re-pin; mentioning the
        # stored SOURCE re-points the roles (the old source seat clears —
        # one asset never holds both roles).
        for mention in request.mentions or []:
            if mention.type != "asset":
                continue
            mentioned = next(
                (a for a in assets if str(a.id) == mention.id), None
            )
            if mentioned is not None and mentioned.type == AssetType.VIDEO:
                self.mention_exemplar_id = str(mentioned.id)
        # The plan layer reads the material's opening, not just its filename
        # (track-model §7.4 折中版 — mechanical slice, zero extra LLM): the first
        # asset carrying text, capped — the ONE text seat (ADR-113) picks
        # the layer (transcript beats extracted_text).
        material_excerpt = next(
            (
                excerpt
                for a in assets
                if (excerpt := asset_text_content(a).strip())
            ),
            None,
        )
        if material_excerpt:
            material_excerpt = material_excerpt[:800]
        # 信任锚注入 (ADR-083, 2026-09-17): the READY material understanding
        # rides the context at assemble time — a plain DB read off the
        # content-addressed row (zero LLM, zero extra round), so the echo's
        # judgment duty has top-tier semantic evidence in iteration 0
        # instead of needing a get_understanding detour (which would break
        # the speak-first streaming beat with a transition filler). Not
        # ready / stale shape → absent, the grounding hierarchy falls
        # through to the excerpt / the user's own words.
        understanding_lines: list[str] | None = None
        if assets:
            from app.pipeline.node_runners import (  # deferred: pipeline weight
                find_reusable_understanding,
            )
            from app.pipeline.step_context import asset_digest

            understanding_digest = asset_digest(assets)
            understanding_row = await find_reusable_understanding(
                db, project, understanding_digest
            )
            if understanding_row is not None:
                try:
                    understanding_lines = understanding_digest_lines(
                        MaterialUnderstanding.model_validate(
                            understanding_row.payload
                        )
                    ) or None
                except Exception:  # noqa: BLE001 — a stale-shaped row reads as absent
                    understanding_lines = None

        # Readiness gate (I-PFA-07, 2026-09-18): the attached-but-unready fact
        # is CODE-stamped into the context — the router never infers readiness
        # from absent evidence (a missing excerpt/understanding used to be the
        # only signal, so the model faced the unready world alone and could
        # improvise「I can't read it」). Pasted-text material lands ready
        # (transcript at birth), so the predicate rides file assets only.
        processing_count = sum(
            1
            for a in assets
            if a.file_url
            and a.processing_status
            in (AssetStatus.PENDING, AssetStatus.PROCESSING)
        )
        failed_count = sum(
            1
            for a in assets
            if a.file_url and a.processing_status == AssetStatus.FAILED
        )
        material_pending_line: str | None = None
        if processing_count:
            # 服务员话术律 (2026-10-06 用户拍板): the pre-read speech is a
            # WAITER line only — you haven't seen the content, so no
            # proposals, no direction suggestions, no question ride it; the
            # plan talk comes after the read, never before. (The line lands
            # as its own interim_prose segment — tool_loop's iteration-0 seat.)
            material_pending_line = (
                f"素材状态：{processing_count} 个上传文件仍在处理，暂时无法读取内容。若本轮答复取决于文件内容，调用 get_understanding，它会等到素材处理完才返回，本轮即可据此回答。"
                f"调用前只用用户的语言简短说明已收到文件，将先查看，首次查看需要几分钟。尚未看到内容时不提方案、不推荐方向、不提问，读完再讨论方案。"
            )
        elif failed_count:
            material_pending_line = (
                f"素材状态：{failed_count} 个上传文件处理失败，内容将无法读取。"
            )
        from app.chat.readiness import infer_task_kind
        if material_pending_line is None and infer_task_kind(text) == "website_promo":
            web_assets = [asset for asset in assets if asset.type == AssetType.WEB_PAGE]
            if any(asset.processing_status == AssetStatus.FAILED for asset in web_assets):
                material_pending_line = (
                    "此 URL 的网站采集失败。页面尚不能用作可读证据，不要推断品牌方向或询问创意偏好。"
                )
            elif any(asset.processing_status in {AssetStatus.PENDING, AssetStatus.PROCESSING} for asset in web_assets):
                material_pending_line = (
                    "此 URL 的网站采集仍在等待，页面尚不能用作可读证据。"
                )
            else:
                material_pending_line = (
                    "此 URL 已有网站采集结果。请先准备并核实已固定的正文和所需 PNG 视图，再作为可读证据使用。"
                )

        recent_lines: list[str] = []
        from app.chat.video_turn_seats import video_context_lines
        recent_lines.extend(await video_context_lines(
            db, project, request.mentions,
            skill=self.skill, skill_ambiguity=self.skill_ambiguity,
        ))
        # The presented chain (ADR-043): the panel's current task list when the
        # caller sends one (hand edits ride along), else the stored plan's. The
        # intent router sees it as a JSON chain and re-emits the WHOLE refined chain
        # — panel edits survive because the LLM preserves what the message does
        # not revise (chat revisions always win; the field-level merge machinery
        # died with the slots grammar).
        prior = request.prior_intent or (stored.intent if stored else None)
        # The LLM revises the exact chain, not a prose digest — ship the JSON.
        presented_plan = (
            json.dumps([t.model_dump(mode="json") for t in prior.tasks], ensure_ascii=False)
            if prior is not None and prior.tasks
            else None
        )
        # The brief the router reads (ADR-052 B2): the stored brief with the
        # material state freshly code-stamped (the router reads it for the root
        # judgment, never proposes it). This turn's own proposal merges in the
        # absorb — LLM proposes, code decides.
        self.has_text_material = await has_any_text_material(db, UUID(str(project.id)))
        brief_in = (stored.brief if stored else Brief()).model_copy(deep=True)
        brief_in.material_state = BriefSlot(
            value=(
                "attached"
                if any(a.file_url for a in assets)
                else "pasted"
                if self.has_text_material
                else "none"
            ),
            source=BriefSlotSource.DEFAULT,
        )
        # Asking strategy ②'s pantry (C2): resolve the turn's persona so the
        # router can source concrete one-word option values from it (explicit
        # pick → the pending plan's → the project mount → the user default —
        # the same precedence resolve_run_persona stamps at start). Without
        # this block the "3 concrete options" rule had no material and
        # questions starved to bare text.
        persona_id = (
            request.persona_id
            or (stored.persona_id if stored else None)
            or project.persona_id
        )
        persona: Persona | None = None
        if persona_id:
            persona = (
                await db.execute(select(Persona).where(Persona.id == persona_id))
            ).scalar_one_or_none()
        if persona is None:
            persona = await resolve_default_persona(db, self.user_id)
        self.persona = persona
        # ADR-117 D1: the turn's confirmation prefs ride the assembled
        # context as a FACT line (the mode-conditional law stays in the
        # static system template — 一法一座, prefix-cache intact). The
        # server-side enforcement reads the SAME two prefs fresh at the
        # dock (resolve_confirmation_need), never this assembly.
        user_row = await db.get(User, self.user_id)
        self.confirmation = read_confirmation_prefs(
            user_row.settings if user_row is not None else None
        )
        # The docked decision package (iter-2 ⑦): when a plan-sourced dock is
        # on the table, its Content Plans render as the package block so a
        # change ask can name its plan_id (revise_plan's唯一指认面 — the LLM
        # never invents an id).
        plans_lines: list[str] | None = None
        if stored is not None and stored.plans:
            lines = []
            for p in stored.plans:
                outputs = ", ".join(
                    str(o.get("kind", "?"))
                    + (f" ({o['language']})" if o.get("language") else "")
                    for o in (p.get("outputs") or [])
                )
                lines.append(
                    f"- plan_id {p.get('plan_id')}: "
                    f"{p.get('title') or '(unnamed)'} — {outputs}"
                )
            plans_lines = lines or None
        self.infer_kwargs = dict(
            message=self.suggestion_note or "",
            brief=brief_in,
            persona=persona,
            pending_question=pending_q,
            filename=filename,
            presented_plan=presented_plan,
            plans_lines=plans_lines,
            recent=recent_lines or None,
            # The transform-target rule's authoritative signal (同源语言护栏 —
            # the plan surface's only other language hint is the filename).
            file_language=(first_file.meta or {}).get("language") if first_file else None,
            material_excerpt=material_excerpt,
            understanding_lines=understanding_lines,
            # The footage's speaker form (deterministic, off asset.meta —
            # independent of the understanding row's readiness): the framing
            # direction's evidence seat, so a vertical ask on interview /
            # single-speaker footage never silently defaults to center crop.
            speaker_form_lines=speaker_form_lines(assets) or None,
            asset_lines=asset_lines,
            material_pending_line=material_pending_line,
            # The sender's surface (2026-09-25 canvas↔chat 联动): "canvas" =
            # the plan's draft graph lives beside the conversation — the
            # review invitation may name that home; None/"chat" = the
            # surface-neutral law stands.
            surface=request.surface,
            # ADR-117 D1 — the confirmation-settings fact (the system
            # template's mode-conditional close law reads it).
            confirmation=self.confirmation,
        )

    def _role_pins(self) -> dict[str, str | None]:
        """The role pins to persist on a PendingPlan write (判词④ — the same
        preserve law as persona_id: a turn that never touched the roles must
        not clobber an earlier settle). Mention this turn > stored."""
        stored = self.stored
        source = stored.source_asset_id if stored else None
        exemplar = stored.exemplar_asset_id if stored else None
        if self.mention_exemplar_id is not None:
            exemplar = self.mention_exemplar_id
            if source == exemplar:
                source = None  # one asset never holds both roles
        return {"source_asset_id": source, "exemplar_asset_id": exemplar}

    # ---- the envelope absorb (once per turn, idempotent) -------------------

    async def _absorb(
        self,
        brief: Brief | None,
        material_text: str | None,
        material_urls: list[str] | None = None,
    ) -> Brief:
        """The turn's envelope absorb — the retired pre-branch block, run at
        the head of every tool execution that carries the seats. Idempotent:
        the material promotion writes at most once per turn, the merge is a
        pure function of the stored brief + THIS call's proposal (the last
        call's merge is what a dock persists), the slot handshake settles the
        pending row once."""
        db = self.db
        # Declared-material promotion (2026-08-05 手测决策): the user explicitly
        # said "this is my transcript/content" — the pasted text becomes a real
        # TRANSCRIPT asset (visible, named). Never inferred from text length.
        if (
            self.material_asset is None
            and material_text
            and material_text.strip()
        ):
            self.material_asset = await create_transcript_asset_from_text(
                db, UUID(str(self.project.id)), self.user_id, material_text.strip()
            )
            self.assets.append(self.material_asset)

        # Declared-URL capture (网页资产化): the router judged the link
        # MATERIAL ("make a film of https://…"), so it becomes a WEB_PAGE
        # asset through the singular creation seat — committed in its own
        # transaction so the capture worker can claim it while this chat
        # turn stays open (the dock-seat storyboard waits for that capture;
        # a flush-only row would deadlock the wait). Idempotent per page:
        # an existing project asset with the same capture_url is reused,
        # never duplicated. CaptureBlocked propagates (the creation seat's
        # SSRF gate).
        if material_urls:
            created_ids = await create_web_page_assets_committed_from_urls(
                UUID(str(self.project.id)), self.user_id, material_urls
            )
            if created_ids:
                born = list(
                    (
                        await db.execute(
                            select(Asset)
                            .where(Asset.id.in_(created_ids))
                            .execution_options(populate_existing=True)
                        )
                    )
                    .scalars()
                    .all()
                )
                born_by_id = {str(a.id): a for a in born}
                for asset_id in created_ids:
                    asset = born_by_id.get(str(asset_id))
                    if asset is not None:
                        self.assets.append(asset)

        # brief (ADR-052 B2): the call's update proposal lands by source
        # precedence, then the material state is code-stamped over it. Every
        # downstream decision — the ask-loop guard, the 出书门槛, the dock
        # write — reads this ONE merged brief (出书决策只看 brief).
        merged_brief = merge_brief(
            brief, self.stored.brief if self.stored else Brief()
        )
        merged_brief.material_state = BriefSlot(
            value=(
                "attached"
                if any(
                    a.file_url or a.type == AssetType.WEB_PAGE for a in self.assets
                )
                else "pasted"
                if self.has_text_material or self.material_asset is not None
                else "none"
            ),
            source=BriefSlotSource.DEFAULT,
        )
        self.merged_brief = merged_brief

        # 插话判定结算 (ADR-053 R2): the router saw the pending question in
        # context; a user-stated proposal for ITS OWN slot is the answer —
        # code settles the row (freeform, the user's stated value) and the
        # enriched brief drives the gates below.
        pending_q = self.pending_q
        if pending_q is not None:
            p_slot = (pending_q.question or {}).get("slot")
            proposed_slot = (
                getattr(brief, p_slot, None)
                if p_slot and brief is not None
                else None
            )
            if (
                proposed_slot is not None
                and proposed_slot.source == BriefSlotSource.USER_STATED
                and isinstance(proposed_slot.value, str)
                and proposed_slot.value.strip()
            ):
                pending_q.answer = AnswerPayload(
                    kind="freeform",
                    text=proposed_slot.value.strip(),
                    answered_at=datetime.now(UTC),
                ).model_dump(mode="json")
                await db.flush()
                self.settled_pending = pending_q
                self.pending_q = None
        return merged_brief

    # ---- the loop's execute dispatch ----------------------------------------

    async def execute(self, name: str, params, prose: str) -> str | None | ToolObservation | TerminalRefusal | CandidateRejected | WorkingDraftRejected | WorkingDraftUpdated:
        """The LoopExecute seat: validate → (reject: feedback, zero writes) →
        accept: writes + the outcome stashed → None (terminal stop). A
        PERCEPTION call short-circuits the seats above: reads are dispatched
        to the family registry and ride back as a ToolObservation (the loop
        iterates — 终态工具一调即停 covers the terminal tools only)."""
        if self.media_journey is not None and name == "design_video" and getattr(params, "save", False):
            return "This staged preparation cannot save a Composition."
        if self.media_state is not None:
            from app.chat.media_journey import media_write_rejection

            rejection = media_write_rejection(
                self.media_state["phase"], name, params, self.media_state.get("narration_resume"),
            )
            if rejection:
                return rejection
        from app.chat.editor import EDITOR_NAMES, execute_editor

        if name in EDITOR_NAMES:
            return await execute_editor(self, name, params)
        if name == "read_conversation_context":
            return await self._conversation_context.read(params)
        if name in PERCEPTION_TOOLS:
            if name == "get_video_version" and params.present:
                from app.chat.video_turn_seats import read_video_for_presentation
                read, feedback = await read_video_for_presentation(self.db, self.project, params)
                if read is not None:
                    self._video_presentation_pending = read
                return feedback
            return await run_perception_tool(
                self.db,
                self.project,
                name,
                params,
            )
        # 插话判定结算 (ADR-053 R2 — the plan-path seat, 2026-09-27 一问拍
        # 一体化): the disposition rides every terminal call's envelope, the
        # chat path's `_settle_by_disposition` mirror — judgment is the LLM's,
        # settlement is code's. "answer" settles the pending plain question
        # as freeform with the user's OWN WORDS (原话一视同仁: an answer, a
        # deferral like "你更推荐什么？", an option discussion all engage the
        # question); "skip" bails it; "none" leaves it (the reply gets the
        # reminder tail below). The slot absorb (_absorb) is the narrower
        # code fast path and composes — it sees pending_q=None after this.
        # Plan-path plain questions are never parked interrupts (prepare
        # filters workflow_run_id), so there is no wake branch here.
        if (
            name == "design_video"
            and self.pending_q is not None
            and params is not None
            and "pending_disposition" not in params.model_fields_set
        ):
            return (
                "a question is pending and this write omitted pending_disposition. "
                "Judge the current message as answer/skip/none and retry the intended call "
                "with that field; no write was executed."
            )
        disposition = (
            getattr(params, "pending_disposition", "none") if params is not None else "none"
        )
        result = await self._dispatch(name, params, prose)
        if self.media_state is not None and isinstance(result, ToolObservation):
            from app.chat.media_journey import dock_media_observation

            result = await dock_media_observation(
                self, name, result, working_draft=getattr(params, "_working_draft", None),
            )
            if result.stop_after_observation:
                await self._resolve_deferred()
        if result is None:
            await self._settle_pending_by_disposition(disposition)
        # The speech-commit resolution (言语提交协议): a terminal accept
        # closes the frame buffer (a rejection-marked turn drops — its
        # words were retracted speech). Rejections retract at the loop's
        # ToolRejected event (the runner's wrapped on_loop_event — one seat
        # catches all four rejection kinds); ToolObservations are
        # non-terminal (reads) — the queue stays armed.
        if result is None:
            await self._resolve_deferred()
        return result

    async def _dispatch(self, name: str, params, prose: str) -> str | None | ToolObservation | TerminalRefusal | CandidateRejected | WorkingDraftRejected | WorkingDraftUpdated:
        if name == "edit_graph":
            from app.pipeline.graph_store import edit_manual_graph
            assert isinstance(params, EditGraphArgs)
            error = await edit_manual_graph(self.db, self.project, params.ops)
            if error is not None:
                return error
            content = prose.strip() or (
                "已更新手动画布。" if _prefers_zh(self.text) else "Manual Canvas updated."
            )
            assistant_message = await _create_message(
                self.db, self.conversation_id, "assistant", content
            )
            self.outcome = (assistant_message, None, self.settled_pending, [])
            return None
        if name == "present_plan":
            assert isinstance(params, PresentPlanArgs)
            return await self._present_plan(params, prose)
        if name in {"list_skill_shots", "read_skill_reference", "read_skill_demo", "get_skill_preview"}:
            from app.chat.video_turn_seats import skill_read_seat
            return await skill_read_seat(
                project=self.project,
                skill=self.skill,
                package_sessions=self.__dict__.setdefault("_skill_package_sessions", {}),
                name=name,
                args=params,
            )
        if name == "analyze_brand":
            from app.chat.video_turn_seats import analyze_brand_seat
            return await analyze_brand_seat(project=self.project, args=params, user_text=self.text)
        if name == "prepare_video_materials":
            from app.chat.video_turn_seats import prepare_video_materials_seat
            return await prepare_video_materials_seat(
                project=self.project, args=params, turn_id=self.turn_id
            )
        if name == "capture_web":
            from app.chat.video_turn_seats import capture_web_seat
            return await capture_web_seat(project=self.project, args=params)
        if name == "design_video":
            from app.tools.video.design import CompositionDesignVideoArgs
            assert isinstance(params, CompositionDesignVideoArgs)
            return await self._design_video(params)
        if name == "review_working_draft":
            from app.chat.video_turn_seats import review_working_draft_seat
            return await review_working_draft_seat(project=self.project, args=params)
        if name == "review_video":
            assert isinstance(params, ReviewVideoArgs)
            from app.chat.video_turn_seats import review_video_seat
            return await review_video_seat(project=self.project, args=params)
        if name == "show_video_presets":
            assert isinstance(params, ShowVideoPresetsArgs)
            from app.chat.video_turn_seats import show_video_presets_seat
            return await show_video_presets_seat(
                project=self.project, args=params, on_candidates=self._emit_candidates
            )
        if name == "select_video_preset":
            assert isinstance(params, SelectVideoPresetArgs)
            from app.chat.video_turn_seats import select_video_preset_seat
            return await select_video_preset_seat(
                project=self.project, args=params, on_candidates=self._emit_candidates
            )
        if name == "search_sfx":
            assert isinstance(params, SearchSfxArgs)
            from app.chat.video_turn_seats import search_sfx_seat
            return await search_sfx_seat(
                project=self.project, args=params, user_text=self.text,
                on_candidates=self._emit_candidates,
            )
        if name == "import_sfx":
            assert isinstance(params, ImportSfxArgs)
            from app.chat.video_turn_seats import import_sfx_seat
            return await import_sfx_seat(
                project=self.project, args=params, on_candidates=self._emit_candidates
            )
        if name == "show_music_candidates":
            assert isinstance(params, ShowMusicCandidatesArgs)
            from app.chat.video_turn_seats import show_music_candidates_seat
            return await show_music_candidates_seat(
                project=self.project, args=params, on_candidates=self._emit_candidates
            )
        if name == "select_music":
            assert isinstance(params, SelectMusicArgs)
            from app.chat.video_turn_seats import select_music_seat
            return await select_music_seat(
                project=self.project, args=params, on_candidates=self._emit_candidates
            )
        if name == "prepare_narration":
            assert isinstance(params, PrepareNarrationArgs)
            from app.chat.video_turn_seats import prepare_narration_seat
            return await prepare_narration_seat(
                project=self.project, args=params, mentions=self.request.mentions
            )
        if name == "prepare_visual_assets":
            from app.chat.video_turn_seats import prepare_visual_assets_seat
            return await prepare_visual_assets_seat(project=self.project, args=params)
        if name == "get_narration_alignment":
            assert isinstance(params, GetNarrationAlignmentArgs)
            from app.chat.video_turn_seats import get_narration_alignment_seat
            return await get_narration_alignment_seat(project=self.project, args=params)
        if name == "annotate_narration":
            assert isinstance(params, AnnotateNarrationArgs)
            from app.chat.video_turn_seats import annotate_narration_seat
            return await annotate_narration_seat(project=self.project, args=params)
        if name == "ask_user":
            assert isinstance(params, PlanAskArgs)
            return await self._ask_user(params, prose)
        if name == "start_run":
            assert isinstance(params, StartRunArgs)
            return await self._start_run(params, prose)
        if name == "answer":
            assert isinstance(params, PlanAnswerArgs)
            return await self._answer(params, prose)
        return f"unknown tool {name!r}"  # unreachable — the driver gates names

    async def _resolve_deferred(self) -> None:
        """The accepted terminal's frame release: flush the queue in order
        and disarm, or drop it when a rejection marked the turn (retracted
        speech — the settled envelope paces out whole, the zero-delta
        path's law)."""
        deferred = self.deferred
        if deferred is None or not deferred.armed:
            return
        if deferred.rejected:
            deferred.drop()
        else:
            await deferred.flush()
            deferred.disarm()

    async def _settle_pending_by_disposition(self, disposition: str) -> None:
        """Settle the pending plain question by the accepted call's judgment
        (2026-09-27, the plan path's seat — the chat path's
        ``_settle_by_disposition`` mirror). A blank turn never settles (the
        judgable law — the chat path's ``pending_judgable`` guard's plan
        twin); the reminder tail keys off ``self.pending_q``, so a settled
        row also silences the tail."""
        pending = self.pending_q
        if pending is None or disposition == "none" or not self.text.strip():
            return
        pending.answer = AnswerPayload(
            kind="freeform" if disposition == "answer" else "bail",
            text=self.text if disposition == "answer" else None,
            answered_at=datetime.now(UTC),
        ).model_dump(mode="json")
        await self.db.flush()
        self.settled_pending = pending
        self.pending_q = None

    async def _stamp_presentation(self, message) -> None:
        """The presented-message association (2026-10-18 裁决 — LLM 唯一
        呈现): fires from ``finish`` when a design beat this turn is owed
        its presentation and a TERMINAL speech row actually persisted
        (the outcome row / the bare-reply floor). Degrade rows that do not
        present a saved version never stamp it; a no-progress row carrying
        the complete saved storyboard is a presentation row. Version-guarded by
        ``presentation_stamp_update`` (a newer draft owns its own
        presentation); the write rides the turn's one transaction, so a
        failed/cancelled turn never leaves a phantom "presented" mark."""
        await self._stamp_video_presentation(message)
    async def _stamp_video_presentation(self, message) -> None:
        """The video family's presentation association (ADR-145 phase B):
        delegates to the shared seat (video_turn_seats) — the receipt on
        pending_brief.video_presentation + the storyboard block on the
        persisted row that actually presents the saved facts."""
        pending = self._video_presentation_pending
        self._video_presentation_pending = None
        from app.chat.video_turn_seats import (  # deferred: same layer
            requested_video_production,
            stamp_video_presentation,
        )

        updated = stamp_video_presentation(
            self.project, message, pending,
            observed_ranges=self.__dict__.pop("_editor_preview_blocks", []),
            production_requested=bool(pending and pending.get("fresh_design"))
            and requested_video_production(self.text),
        )
        if updated is not None:
            self.stored = updated

    async def _design_video(self, params: "CompositionDesignVideoArgs") -> str | ToolObservation | CandidateRejected | WorkingDraftRejected | WorkingDraftUpdated:
        """design_video → the video family's design beat (ADR-145 phase B,
        非终态): the shared seat saves the version through the write door
        on its OWN session; the model's ONE next message presents the saved
        facts (finish stamps the receipt + the storyboard block). NO plan
        docks, NO run starts."""
        from app.chat.video_turn_seats import (  # deferred: same layer
            design_video_seat,
            video_request_id,
        )

        stopped = getattr(self, "_video_design_stopped", None)
        if stopped is not None:
            return stopped
        self._video_call_counter += 1
        if self.media_state is not None and self.media_state["phase"] == "audio" and params.scene:
            params._reviewed_scene_images = self.media_state["approved_images"]
        read, feedback = await design_video_seat(
            project=self.project,
            args=params,
            request_id=await video_request_id(self.db, self.conversation_id, self._video_call_counter),
            skill=self.skill,
            skill_ambiguity=self.skill_ambiguity,
            package_sessions=self.__dict__.setdefault("_skill_package_sessions", {}),
            user_text=self.text,
            pending_brief=(
                self.media_resume_pending.model_dump(mode="json")
                if self.media_resume_pending is not None else None
            ),
        )
        if self.media_state is not None and self.media_state["phase"] == "audio":
            # Keep the scene from the actual failed write. A successful retry clears it.
            self.media_image_blocked_scene = None
            if isinstance(feedback, WorkingDraftRejected) and params.scene and any(
                issue.get("loc") == ["scene", "snapshot_id"]
                for issue in feedback.errors
            ):
                scenes = (feedback.arguments.get("content") or {}).get("scenes") or []
                ordered = sorted(scenes, key=lambda scene: scene.get("range", {}).get("start", 0))
                self.media_image_blocked_scene = next((
                    index for index, scene in enumerate(ordered, start=1)
                    if scene["scene_id"] == params.scene.scene_id
                ), None)
        if (self.media_state and self.media_state["phase"] == "images"
                and isinstance(feedback, WorkingDraftUpdated) and params.scene_assets):
            opening = await self.db.get(Message, self.turn_id)
            answers = await self.db.scalars(select(Message.answer).where(
                Message.conversation_id == self.conversation_id, Message.turn_id == self.turn_id,
                Message.answer["kind"].as_string() == "group",
            ).order_by(Message.seq))
            words = [opening.content]
            for answer in answers:
                words.extend(item["text"] for item in answer.get("answers", []) if item.get("text"))
            feedback.arguments["design"]["review_user_words"] = words
            feedback = replace(feedback, visual_results=self.media_visual_results)
        if read is None:
            if isinstance(feedback, ToolObservation) and not feedback.ok:
                self._video_design_stopped = feedback
            return feedback
        await self._settle_pending_by_disposition(params.pending_disposition)
        read["fresh_design"] = True
        self._video_presentation_pending = read
        return feedback

    async def _present_plan(self, params: PresentPlanArgs, prose: str) -> str | None:
        """Validate and dock the proposed production plan."""
        if getattr(self, "video_confirmation", None) and self.video_confirmation["action"] == "produce":
            from app.chat.video_turn_seats import confirmed_video_task

            params = params.model_copy(update={
                "tasks": [confirmed_video_task(self.video_confirmation)],
                "production_intent": True,
                "material_urls": None,
            })
        db, project = self.db, self.project
        stored = self._current_pending()
        from app.chat.video_turn_seats import video_proposal_guard
        video_guard = await video_proposal_guard(db, project, params.tasks,
            pending_read=self._video_presentation_pending, production_intent=params.production_intent, mentions=self.request.mentions)
        if video_guard is not None:
            return video_guard
        if params.production_intent is None:
            return (
                "production_intent is required. Judge whether the user's current "
                "message asks for this work to be made now, set it explicitly "
                "true or false, then call present_plan again."
            )

        # 空散文护栏 (ask_user 座的同形对称): the plan card carries no title
        # — the echo IS its introduction (three duties), so a silent dock
        # leaves the user facing a canvas they cannot read. Reject into the
        # repair iteration instead of docking speech-less.
        if not prose.strip():
            return (
                "a plan never docks without its introduction speech — the "
                "card has no title of its own, your message IS the "
                "introduction. Speak what you saw, the plan in your own "
                "words, and what 'done' looks like as your message text, "
                "then call present_plan."
            )

        if not params.tasks:
            return (
                "empty task list — a plan needs at least one task. If one "
                "missing answer most decides quality, call ask_user; for a "
                "purely informational reply, call answer."
            )
        merged_brief = await self._absorb(
            params.brief,
            params.material_text,
            getattr(params, "material_urls", None),
        )
        # Chain adjudication (ADR-043): the registry validates the proposed
        # task list — the rejection rides back as the loop's feedback (the
        # retired repair round's seat), then the call retries bounded. The
        # same-language adjudication rides the same door (2026-09-13): a
        # translate/dub target that IS the faced source language is doomed by
        # construction — the feedback names the fix ("中英双语 on an en source
        # → target zh") before the user ever confirms.
        try:
            validate_task_list(params.tasks)
        except (ToolRejected, ValueError) as e:
            return f"{e} (available: {getattr(e, 'suggestions', [])})"

        # 出书门槛 (ADR-052 B2 D2-C2 — the gate reads only the merged brief +
        # the adjudicated chain):
        #  - media-needing chain with material "none" and no plan on the table →
        #    the missing root is the material itself: REJECT, the model answers
        #    with the upload guidance in its own voice (the retired code line's
        #    disclosure payload survives as the feedback's instruction);
        #  - rootless (no topic / no material / no explicit grounded recipe) →
        #    REJECT toward ask_user slot='topic' (the topic asks once);
        #  - still rootless after the topic was asked → ACCEPT and dock with
        #    the code-composed draft-from-persona declaration (提问策略③ — a
        #    code-forced dock never borrows the LLM's voice).
        plan_on_table = stored is not None and stored.intent is not None
        media_blocked = (
            not plan_on_table
            and merged_brief.material_state.value == "none"
            and any(_needs_media(t.tool) for t in params.tasks)
        )
        if media_blocked:
            return (
                "media-needing work (clips / dub / subtitles) but no source "
                "material is attached or pasted — the missing root is the "
                "material itself. Do NOT present this plan: call answer and "
                "tell the user, in their language, that clips and voice dub "
                "need a video, audio, or image upload — they can upload one "
                "or paste their transcript to unlock them, or ask for the "
                "text work only."
            )
        has_root = any(t.tool in {"produce_video", "prepare_narration", "prepare_visual_assets", "prepare_music"} for t in params.tasks) or (
            bool((merged_brief.topic.value or "").strip())
            # S2 语义缝 (2026-09-12): a topic the model INFERRED after the
            # user skipped the topic ask is not a root — the skip chose
            # the default path (draft-from-persona, reason + code echo),
            # and an inferred re-root silently bypasses both. Only the
            # user's own words re-root a skipped slot. (With material
            # attached the next clause roots the plan anyway, so the
            # infer-from-material path is untouched.)
            and (
                merged_brief.topic.source == BriefSlotSource.USER_STATED
                or "topic" not in merged_brief.asked
            )
        ) or (
            merged_brief.material_state.value != "none"
            or (
                params.tasks_explicit
                and bool((params.specific_instruction or "").strip())
            )
        )
        if not has_root and "topic" not in merged_brief.asked:
            self.saw_rootless_rejection = True
            return (
                "the brief has no root (no topic, no material, no explicitly "
                "named grounded recipe) and the topic was never asked — a "
                "rootless plan never docks. Call ask_user with slot='topic' "
                "asking the ONE topic question (options from the persona "
                "pantry; the default path = draft from the persona's style)."
            )
        if not has_root:
            # Asked once, still rootless → the default path docks: the
            # chain is the LLM's (registry-adjudicated), the declaration
            # is code.
            self.reasons_extra = ["draft_from_persona"]
            self.echo_override = _draft_from_persona_echo(self.text)

        # The intent object the storage shapes are built from (the accepted
        # call's params + the turn's echo — the same fields the action
        # union carried).
        echo = self.echo_override if self.echo_override is not None else prose
        reasons = await _compute_plan_reasons(db, project, InferredIntent(
            action="draft",
            tasks=params.tasks,
            specific_instruction=params.specific_instruction,
            tasks_explicit=params.tasks_explicit,
            brief=params.brief,
            name=params.name,
        ))
        reasons = [*reasons, *self.reasons_extra]

        # A turn that omits persona_id must not clobber the persona choice an
        # earlier turn made.
        persona_id = self.request.persona_id
        if persona_id is None and isinstance(project.pending_brief, dict):
            persona_id = project.pending_brief.get("persona_id")

        # Derived preview (ADR-043): dry-run the chain through compile_graph and
        # project what it will make — the plan card's "you'll get" section. A
        # chain that can't compile here (e.g. transform with no media anywhere)
        # still docks, flagged by its reason — the birthplace rejects for real.
        from app.pipeline.orchestrator import derive_plan_preview

        try:
            derived = await derive_plan_preview(db, project, params.tasks)
        except (ToolRejected, ValueError):
            derived = []
        # Dock 载荷的估价面 (BILLING §7): the same dry-run compile's credits
        # quotation (total + per-task marginal), degraded exactly like the
        # preview — an unquotable/uncompilable chain docks quote-less.
        task_estimate = await _safe_task_estimate(db, project, params.tasks)
        # ADR-117 §4: the confirmation need is computed ONCE here — the
        # echo's held clause (keyed on the stamped reason: the auto
        # regime's guardrail/unquotable trip carries the honest
        # correction) and the dock payload's stamp read the same object
        # (passed through below).

        need = await resolve_confirmation_need(
            db, self.user_id, task_estimate,
            production_intent=params.production_intent,  # ADR-139
            require_quote=any(task.tool == "prepare_music" for task in params.tasks),
            # 7276ef13 ③: a change refused THIS turn holds the auto start.
            # 定点收尾②复审: the drift hold reads the STANDING VERSION's
            # persisted state (world truth — a rebuilt turn never loses it),
            # never a turn-local flag.
        )

        # The late-turn guard: a concurrent Start committed while this refine
        # was in flight — docking now would raise a plan over an active
        # run (the zombie dock). Degrade to the active-run line.
        active_line = await _active_run_line(db, project, self.text)
        if active_line is not None:
            assistant_message = await _create_message(
                db,
                self.conversation_id,
                "assistant",
                active_line,
            )
            self.outcome = (assistant_message, None, self.settled_pending, [])
            return None

        # The birth prompt freezes at the first dock (stored.prompt wins on every
        # later write) — the brief is the accumulated state now, the prompt is
        # only the plan's birth narrative (Start's instruction fallback).
        birth_prompt = stored.prompt if stored and stored.prompt else self.text
        # Caption mode (ADR-099 §8 default absorption): what the call didn't
        # set rides the shared funnel — the user's own words (literal
        # bilingual keyword) > the previous dock's value > source_only when a
        # distinct second language makes the choice real. The stamped value
        # Inherit the previous dock's NAME on an identical-chain re-dock
        # (2026-09-09 取证): a bare confirmation the router misjudged as a
        # draft re-proposes the SAME chain unnamed — the inherited name IS the
        # LLM's own earlier naming of the same work, preserving it invents
        # nothing.
        name = params.name
        if (
            not (name or "").strip()
            and stored is not None
            and stored.intent is not None
            and (stored.intent.name or "").strip()
            and [t.model_dump(mode="json") for t in params.tasks]
            == [t.model_dump(mode="json") for t in stored.intent.tasks]
        ):
            name = stored.intent.name

        intent = InferredIntent(
            action="draft",
            tasks=params.tasks,
            answer=echo,
            specific_instruction=params.specific_instruction,
            tasks_explicit=params.tasks_explicit,
            brief=params.brief,
            material_text=params.material_text,
            name=name,
        )
        # Phase 3 Batch B ③: the retired "drafting" System Status label used
        # to fire here — the draft ACTIVITY frame (opened at this call's
        # name-known beat, settled at its acceptance) is the work's only
        # user-safe face now (三通道分家).
        from app.chat.readiness import creative_state_for_pending, creative_state_with_brief
        from app.editing.service import video_carry_state  # deferred: editing seam
        project.pending_brief = PendingPlan(
            prompt=birth_prompt,
            intent=intent,
            # brief (ADR-052 B2): the ONE merged brief — the call's update
            # landed by source precedence + the material state code-stamped in
            # the absorb; the gate and the ask execution read this same object.
            brief=merged_brief,
            creative_state=creative_state_with_brief(
                creative_state_for_pending(stored) or CreativeState(), merged_brief
            ),
            reasons=reasons,
            persona_id=persona_id,
            derived=derived,
            **video_carry_state(stored),
            **self._role_pins(),
        ).model_dump(mode="json")
        bailed_run_ids = await sync_plan_question(
            db, self.user_id, project, intent, birth_prompt, reasons=reasons,
            derived=derived,
            brief=merged_brief,
            echo=echo,
            estimate=task_estimate,
            need=need,
        )
        question = await latest_pending_question(db, self.conversation_id)
        assert question is not None  # sync_plan_question just docked it
        self.outcome = (question, None, self.settled_pending, bailed_run_ids)
        # ADR-117 §2 auto 开工道: when the dock owes no confirm beat, the
        # SAME start machine fires on presentation (None = the dock waits
        # for the user's beat — ask modes / guardrail / structural hold).
        auto = await _auto_start_docked_plan(
            db,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            project=project,
            turn_id=self.turn_id,
            defer_start_commit=True,
        )
        if auto is not None:
            answered_q, auto_run_id = auto
            self.outcome = (question, auto_run_id, answered_q, bailed_run_ids)
        return None

    # ---- the exploration seats (iter-2 ③/⑤ — ADR-088 旅程四 chain) -----------

    async def _emit_milestone(self, key: str, count: int) -> None:
        """Fire one work-session milestone frame (iter-2 ⑥, N-57) at a door
        success — in-session interleave only, never persisted. No-op on the
        one-shot path."""
        if self.on_activity is not None:
            await self.on_activity(key, count)


    async def _emit_candidates(self, payload: dict) -> None:
        """Candidate Surface 信道 (Workspace 合同 v4.2 C8-c, 2026-09-26):
        the candidate card's payload rides its OWN SSE frame
        (``assistant.candidates``) at the door's success — the milestone's
        count-only whitelist never carries members. The SSE route ALSO
        collects every emitted payload and persists them as ONE
        ``candidates_log`` message row at turn settle (the activity-row
        precedent), so a refresh rebuilds the surface from the archive —
        数据链全程消息载, no endpoint. No-op on the one-shot path."""
        if self.on_candidates is not None:
            await self.on_candidates(payload)


    async def _ask_user(self, params: PlanAskArgs, prose: str) -> str | None:
        """Dock one clarification interaction through the ask_user machinery."""
        stored = self._current_pending()
        from app.chat.readiness import (
            brief_with_user_constraints,
            creative_state_for_pending,
            creative_state_with_brief,
            infer_task_kind,
            website_promo_question_items,
        )
        source_text = (
            self.text if infer_task_kind(self.text) == "website_promo"
            else (stored.prompt if stored else None) or self.text
        )
        website_promo = infer_task_kind(source_text) == "website_promo"
        if website_promo and params.brief is not None:
            return "Submit the questionnaire against the current Brief. Only the user's answers settle its missing fields."
        merged_brief = await self._absorb(
            params.brief, params.material_text, getattr(params, "material_urls", None),
        )
        if website_promo:
            merged_brief = brief_with_user_constraints(self.text, merged_brief)
            current_state = creative_state_for_pending(stored)
            if current_state is None or current_state.brand_profile is None:
                return "website promo clarification requires analyze_brand before ask_user; no question was docked"
        group_items = []
        group_digest = None
        if website_promo:
            try:
                group_items = website_promo_question_items(params.items, merged_brief)
            except ValueError as exc:
                return f"{exc}. Correct the form data privately and keep the invitation to the user."
            group_digest = question_group_digest(group_items, merged_brief)
        elif params.items:
            try:
                group_items = missing_brief_question_items(params.items, merged_brief)
            except ValueError as exc:
                return str(exc)
            if not group_items:
                return "every requested Brief field is already present; do not re-ask it"
            group_digest = question_group_digest(group_items, merged_brief)
        if not params.question.strip():
            return (
                "empty question — speak the framing as your message text and "
                "pass the bare question or group title, or call present_plan / answer "
                "instead."
            )
        # 判词⑦ 扩座 (2026-09-12, S5) as a REJECTION (its structural form):
        # ANY ask while a question is still pending is an interjection, never
        # a new dock — docking supersedes the pending row, and for a
        # task_book that orphans the confirmation.
        if self.plan_pending or self.pending_q is not None:
            return (
                "a question of yours is still awaiting the user's answer — "
                "this message is an interjection, not a new question. Call "
                "answer with your reply instead (the pending question stays "
                "open and the code adds the reminder tail); never raise a "
                "second question while one is pending."
            )
        if params.slot is not None and params.slot in merged_brief.asked:
            # The ask loop is bounded (每个槽位至多询问一次, each slot asks at most
            # once): the router re-asked an already-asked slot — the turn is
            # a plan turn; the 出书门槛 docks the draft-from-persona plan
            # instead of looping the question.
            return (
                f"slot '{params.slot}' was already asked once this plan "
                "phase — each slot asks at most once. Call present_plan to "
                "dock the plan now (the gate handles rootlessness)."
            )
        # ask 一等动作 (ADR-052 B2, 案 A 双实例): the pre-run router's ONE
        # question docks through the same machinery the chat path's ask_user
        # uses — with the plan-path handshake on the payload (slot → the
        # answer backfills the brief user-stated; default_path → the dock's
        # muted second line). The brief merge lands as a brief-only row: the
        # stored plan's intent is preserved verbatim (an ask never clobbers
        # the plan), and a fresh project's row carries intent=None (never
        # startable).
        if group_items:
            merged_brief.asked = list(dict.fromkeys([
                *merged_brief.asked, *(item.slot for item in group_items)
            ]))
            params = params.model_copy(update={"slot": None})
        elif params.slot is not None:
            merged_brief.asked = [*merged_brief.asked, params.slot]
        if params.slot == "asset_role":
            # 资产角色消歧 (ADR-078 判词④): the question's options are
            # CODE-BUILT from the project's videos (option id = asset id,
            # label = filename) — the LLM frames the speech, code guarantees
            # the ids resolve at the answer's settle. Fewer than two videos =
            # nothing to disambiguate: reject back into the loop.
            from app.chat.service import _build_role_question

            role_question = _build_role_question(self.text, self.assets)
            if role_question is None:
                return (
                    "fewer than two video files are attached — there is no "
                    "role ambiguity to ask about. Call present_plan with the "
                    "chain, or answer."
                )
            params = params.model_copy(
                update={
                    "question": role_question.question,
                    "options": role_question.options,
                    "allow_freeform": role_question.allow_freeform,
                    "default_path": role_question.default_path or params.default_path,
                }
            )

        from app.editing.service import video_carry_state  # deferred: editing seam
        self.project.pending_brief = PendingPlan(
            # The birth prompt stays frozen (stored.prompt wins) — the
            # accumulated narrative retired with the brief switch.
            prompt=stored.prompt if stored and stored.prompt else self.text,
            intent=stored.intent if stored else None,
            brief=merged_brief,
            creative_state=creative_state_with_brief(
                creative_state_for_pending(stored) or CreativeState(), merged_brief
            ),
            reasons=stored.reasons if stored else [],
            persona_id=(
                self.request.persona_id
                or (stored.persona_id if stored else None)
            ),
            derived=stored.derived if stored else [],
            plans=stored.plans if stored else [],
            plan_task_map=stored.plan_task_map if stored else None,
            # The versioned storyboard survives an interjection ask verbatim
            # (review hold included — only a proposal dock releases it).
            **video_carry_state(stored),
            **self._role_pins(),
        ).model_dump(mode="json")
        # ask 三分解剖 (2026-09-08): the row's content carries the framing
        # prose (解剖 ① — it streams as the turn's echo and replays in the
        # flow); the bare question rides the payload (解剖 ② — dock title,
        # QA archive, reminder tail). Prose-less asks fall back to content =
        # the bare question, the legacy shape every consumer still reads.
        # 推荐标记 (2026-09-27 一问拍一体化): the shared validation lives in
        # resolve_recommended_id — the asset_role code-built options
        # invalidate any LLM-written id the same way.
        recommended_id = resolve_recommended_id(params.recommended_id, params.options)
        ask = QuestionProposal(
            prose=prose or "",
            question=params.question,
            options=params.options,
            allow_freeform=params.allow_freeform,
            recommended_id=recommended_id,
            slot=params.slot,
            default_path=params.default_path,
        )
        intent = InferredIntent(
            action="ask",
            ask=ask,
            brief=params.brief,
            material_text=params.material_text,
        )
        assistant_message, bailed_run_ids = await _dock_question(
            self.db,
            self.conversation_id,
            _ask_content(ask, has_dock_options=bool(group_items)),
            QuestionPayload(
                kind="question",
                question=params.question,
                options=params.options,
                allow_freeform=params.allow_freeform,
                recommended_id=recommended_id,
                slot=params.slot,
                default_path=params.default_path,
                items=group_items,
                group_digest=group_digest,
            ),
            intent=intent.model_dump(mode="json"),
        )
        self.outcome = (assistant_message, None, self.settled_pending, bailed_run_ids)
        return None


    async def _start_run(self, params: StartRunArgs, prose: str) -> str | None:
        """start → the docked plan is answered kind=start (G-1 path: the
        run comes from the only birthplace, answer_question; zero bypass).
        The turn's speech (the work-start line, ADR-093 §2) lands as a plain
        assistant row first — created before the run births, so its stamp
        orders before the task list by construction. The outer Turn's final
        Stop-fenced commit lands speech, answer and Run atomically."""
        db = self.db
        stored = self._current_pending()
        pending_question = await latest_pending_question(db, self.conversation_id)
        confirmation = getattr(self, "video_confirmation", None)
        if confirmation and confirmation["action"] == "start" and (
            pending_question is None or str(pending_question.id) != confirmation["quote_message_id"]
        ):
            return "The production quote has changed. Present its current terms before starting."
        if (
            is_pending_plan(pending_question)
            and stored is not None
            and stored.intent is not None
        ):
            assert pending_question is not None  # is_pending_plan guarantees the row
            # 旧 Start 失效 (ADR-129): the docked task_book presents a film
            # draft version — a newer design beat minted a new draft token,
            # so this Start would confirm a board the user is no longer
            # reviewing. Steer back to the current draft (re-dock, then
            # start), never a silent old-version run.
            # 起始句 = 普通 assistant 行 (ADR-093 §2): the model's own words
            # persist or nothing does — an empty prose stays an honest
            # absence (a template fill-in is prohibited speech), keeping
            # the envelope's assistant_message on the answered plan row.
            start_message = None
            if prose.strip():
                start_message = await _create_message(
                    db,
                    self.conversation_id,
                    "assistant",
                    prose.strip(),
                )
            answered, _follow_up = await answer_question(
                db, self.user_id, UUID(str(pending_question.id)),
                # The review panel's edited plan rides along (typed Start
                # parity): dropping prior_intent here would execute the
                # stored chain and silently discard the user's panel edits.
                StartAnswerRequest(
                    kind="start",
                    intent=self.request.prior_intent,
                ),
                # ④ snapshot channel (N-57): the confirmation arrived as a
                # chat reply (the start_run tool), not the dock pill.
                confirmed_via="chat_reply",
                turn_id=self.turn_id or pending_question.turn_id,
                defer_start_commit=True,
            )
            # The outer Chat Turn's final Stop fence commits the run, answer
            # and cleared pending brief in one transaction.
            self.outcome = (
                start_message or answered,
                UUID(str(answered.workflow_run_id)),
                answered,
                [],
            )
            return None
        if stored is not None and stored.intent is not None:
            # Nothing startable right now. Never overwrite a stored plan
            # with a start-call misfire: re-dock the stored plan unchanged.
            # Unless a run started concurrently — then the plan is moot and
            # re-docking would raise a plan over an active run.
            active_line = await _active_run_line(db, self.project, self.text)
            if active_line is not None:
                assistant_message = await _create_message(
                    db,
                    self.conversation_id,
                    "assistant",
                    active_line,
                )
                self.outcome = (assistant_message, None, self.settled_pending, [])
                return None
            bailed_run_ids = await sync_plan_question(
                db, self.user_id, self.project, stored.intent, stored.prompt,
                reasons=stored.reasons, derived=stored.derived,
                brief=stored.brief,
                echo=stored.intent.answer,
                estimate=await _safe_task_estimate(db, self.project, stored.intent.tasks),
                # The re-dock replays the stored echo verbatim; the film
                # version's token + number ride so the Start gate compares
                # against the CURRENT draft (ADR-129).
            )
            question = await latest_pending_question(db, self.conversation_id)
            assert question is not None  # sync_plan_question just docked it
            self.outcome = (question, None, self.settled_pending, bailed_run_ids)
            return None
        return (
            "no plan is on the table — nothing to start. If the user "
            "wants work, call present_plan with the chain; if one missing "
            "answer decides quality, call ask_user. A start call can never "
            "create a plan."
        )

    async def _answer(self, params: PlanAnswerArgs, prose: str) -> str | None:
        """answer → a plain assistant message; the stored plan stays
        untouched. The envelope seats still absorb (an answer can carry the
        user's declared material)."""
        if self.media_state is not None:
            ready = self.media_state.get("audio_timing_ready")
            message = await _create_message(
                self.db, self.conversation_id, "assistant", prose.strip() if ready else self._media_stop_text(),
                intent={"media_journey": {**self.media_journey, "state": "complete" if ready else "blocked"}},
            )
            self.outcome = (message, None, self.settled_pending, [])
            return None
        await self._absorb(
            params.brief,
            params.material_text,
            getattr(params, "material_urls", None),
        )
        if not prose.strip():
            return (
                "an empty reply says nothing — speak the answer as your "
                "message text, then call answer."
            )
        # Capability question: the reply lands as a plain assistant message
        # and the stored plan stays untouched — an answer turn never
        # overwrites the plan the user is confirming. When a question
        # survived the turn unsettled (an interjection, ADR-053 R2), the
        # code-composed reminder rides a system block after the prose.
        blocks = None
        if self.pending_q is not None:
            blocks = [_reminder_block(
                self.text,
                _bare_question(self.pending_q),
                (self.pending_q.question or {}).get("default_path"),
            )]
        assistant_message = await _create_message(
            self.db,
            self.conversation_id,
            "assistant",
            prose,
            blocks=blocks,
        )
        self.outcome = (assistant_message, None, self.settled_pending, [])
        return None

    # ---- the outcome mapping -------------------------------------------------

    def _media_stop_text(self) -> str:
        zh = str(self.project.language or "").startswith("zh")
        phase = self.media_state["phase"]
        if self.media_image_blocked_scene is not None and not self.media_start_blocker:
            scene = self.media_image_blocked_scene
            return (
                f"第 {scene} 幕的画面未能写入时间线，制作已停在这一步。"
                if zh else f"The image for scene {scene} could not be added to the timeline. Preparation stopped there."
            )
        if phase in {"images", "images_blocked"}:
            content = "分镜图片尚未全部准备并通过审阅，本次停在图片阶段。" if zh else (
                "Some scene images are still missing or unapproved. Preparation stopped at images."
            )
        else:
            content = "旁白与配乐尚未全部就绪，本次停在音频准备阶段。" if zh else (
                "Narration and music are not fully ready. Preparation stopped at audio."
            )
        if self.media_start_blocker:
            content += (
                " 准备计划未能提交，因此没有启动该步骤。"
                if zh else " The preparation plan was rejected before execution."
            )
        return content

    async def finish(self, result) -> PlanTurnOutcome:
        """LoopResult → the caller's 4-tuple. An accepted execution stashed
        its outcome already; the bare reply and the exhaustion degrade land
        here (an honest degrade, never a fabricated success)."""
        if self.outcome is not None:
            # 呈现关联 (2026-10-18 裁决): a design beat this turn owes its
            # presentation — the TERMINAL row IS the presentation message;
            # stamp its provenance now that the row persisted.
            await self._stamp_presentation(self.outcome[0])
            return self.outcome
        # The degrade paths land their own message — resolve any still-armed
        # queue FIRST so its frames precede the envelope: a clean bare reply
        # flushes (the queued prose IS the reply), a rejection-marked queue
        # drops (every queued word was rejected speech).
        await self._resolve_deferred()
        if self.media_state is not None and (
            result.exhausted or result.no_progress_tool is not None
            or result.ended_by is not None or result.tool_name is None
            or self.media_start_blocker is not None
        ):
            content = self._media_stop_text()
            message = await _create_message(
                self.db, self.conversation_id, "assistant", content,
                intent={"media_journey": {**self.media_journey, "state": "blocked"}},
            )
            return message, None, self.settled_pending, []
        if result.no_progress_tool is not None:
            video_read = self._video_presentation_pending
            assistant_message = await _create_message(
                self.db,
                self.conversation_id,
                "assistant",
                _design_no_progress_text(
                    self.text,
                    version_saved=(
                        video_read is not None
                    ),
                    video_read=video_read,
                ),
            )
            # A direct video save is real even when its later correction stops.
            # Present those saved facts and attach the normal review receipt.
            await self._stamp_video_presentation(assistant_message)
            return assistant_message, None, self.settled_pending, []
        if result.ended_by is not None:
            # A deterministic refusal ends the loop without another model
            # roll. Video capability facts have their own honest close; the
            # design begin latch retains its distinct state-conflict meaning.
            facts = result.refusal_facts or {}
            content = (
                _sfx_import_failure_text(self.text)
                if facts.get("kind") == "sfx_import_failure"
                else _video_review_failure_text(self.text, facts)
                if facts.get("kind") == "video_review_failure"
                else _video_capability_text(self.text, facts)
                if facts.get("kind") == "video_capability"
                else _loop_incomplete_text(self.text, result)
            )
            assistant_message = await _create_message(
                self.db,
                self.conversation_id,
                "assistant",
                content,
            )
            return assistant_message, None, self.settled_pending, []
        if not result.exhausted:
            # The bare final reply (no tool called) — the read-tolerant
            # answer floor: the prose IS the reply.
            content = result.prose.strip() or _cannot_do_text(self.text)
            blocks = None
            if self.pending_q is not None:
                blocks = [_reminder_block(
                    self.text,
                    _bare_question(self.pending_q),
                    (self.pending_q.question or {}).get("default_path"),
                )]
            assistant_message = await _create_message(
                self.db,
                self.conversation_id,
                "assistant",
                content,
                blocks=blocks,
            )
            # The bare reply IS the presentation when the model closed a
            # design beat without a further call — same association seat.
            await self._stamp_presentation(assistant_message)
            return assistant_message, None, self.settled_pending, []
        # Exhaustion can follow successful reads and failed submissions.
        # A latched begin refusal speaks
        # the busy/conflict line (never the capability refusal — the design
        # entry was alive, its start was blocked). When the rootless
        # rejection was among them, the code-composed topic question docks
        # (the asked roll stamped — the bound holds); anything else degrades
        # to a fact-based incomplete-work response. Never a docked broken plan.
        logger.info(
            "plan_turn_loop_exhausted",
            calls=result.calls,
            rootless=self.saw_rootless_rejection,
        )
        if self.saw_rootless_rejection:
            stored = self._current_pending()
            merged_brief = self.merged_brief or Brief()
            merged_brief.asked = [*merged_brief.asked, "topic"]

            from app.chat.readiness import creative_state_for_pending, creative_state_with_brief
            from app.editing.service import video_carry_state  # deferred: editing seam
            self.project.pending_brief = PendingPlan(
                prompt=stored.prompt if stored and stored.prompt else self.text,
                intent=stored.intent if stored else None,
                brief=merged_brief,
                creative_state=creative_state_with_brief(
                    creative_state_for_pending(stored) or CreativeState(), merged_brief
                ),
                reasons=stored.reasons if stored else [],
                persona_id=(
                    self.request.persona_id
                    or (stored.persona_id if stored else None)
                ),
                derived=stored.derived if stored else [],
                plans=stored.plans if stored else [],
                plan_task_map=stored.plan_task_map if stored else None,
                **video_carry_state(stored),
                **self._role_pins(),
            ).model_dump(mode="json")
            topic_ask = _topic_gate_question(self.text)
            topic_intent = InferredIntent(
                action="ask",
                ask=QuestionProposal(
                    question=topic_ask["question"],
                    options=[],
                    allow_freeform=True,
                    slot="topic",
                    default_path=topic_ask["default_path"],
                ),
            )
            assistant_message, bailed_run_ids = await _dock_question(
                self.db,
                self.conversation_id,
                topic_ask["question"],
                QuestionPayload(
                    kind="question",
                    question=topic_ask["question"],
                    options=[],
                    allow_freeform=True,
                    slot="topic",
                    default_path=topic_ask["default_path"],
                ),
                intent=topic_intent.model_dump(mode="json"),
            )
            return assistant_message, None, self.settled_pending, bailed_run_ids
        assistant_message = await _create_message(
            self.db,
            self.conversation_id,
            "assistant",
            _loop_incomplete_text(self.text, result),
        )
        return assistant_message, None, self.settled_pending, []


async def run_plan_turn(
    db: AsyncSession,
    user_id: UUID,
    conversation,
    project: Project,
    request: ChatRequest,
    skill: SkillReference | None = None,
    skill_ambiguity: list[str] | None = None,
    recent: list[Message] | None = None,
    on_delta=None,
    on_reasoning=None,
    on_phase=None,
    on_tool_call=None,
    on_tool_ready=None,
    on_interim_prose=None,
    on_loop_event=None,
    on_activity=None,
    on_candidates=None,
    on_row_append=None,
    turn_id: UUID | None = None,
    media_journey: dict | None = None,
    media_resume_pending: PendingPlan | None = None,
    media_resume_draft: RestoredCandidate | None = None,
    media_resume_narration: list[dict] | None = None,
    group_answer_submitted: bool = False,
) -> PlanTurnOutcome:
    """The plan path's turn: assemble → the bounded tool loop → the outcome
    mapping. ``intent_router`` provider failures propagate as LLMError — no
    fabricated default plan (2026-08-14 裁定); the route boundary turns it
    into a 502 with the localized provider line. on_delta streams the prose
    channel (it IS the reply now); on_tool_call/on_tool_ready carry the
    structure frames (the phase beat / the question preview); on_phase labels
    the real phase switches; on_interim_prose (ADR-085) is the interim_prose
    channel's SSE seat — the runner wraps it with persistence (the interim_prose
    row is this turn's own message, intent type 'interim_prose'). None = the
    one-shot path. ``on_row_append`` is the generic persisted-row channel
    (currently unused by this path — the design beat's program-markdown
    publication retired with the 2026-10-18 裁决)."""
    turn = PlanTurn(
        db, user_id, conversation, project, request,
        skill=skill, skill_ambiguity=skill_ambiguity,
        on_phase=on_phase, on_activity=on_activity, on_candidates=on_candidates,
        on_row_append=on_row_append, turn_id=turn_id,
    )
    from app.chat.context import conversation_messages
    from app.chat.prompts import assemble_video_round
    from app.chat.speech_language import conversation_speech_language
    from app.chat.video_turn_seats import (
        prepare_bound_skill_context,
        requested_video_production,
        video_target_hint,
    )
    context_reader = await prepare_bound_skill_context(
        project=project, skill=skill, message=request.message,
        package_sessions=turn.__dict__.setdefault("_skill_package_sessions", {}),
    )
    turn.media_resume_pending = media_resume_pending
    turn.media_resume_narration = media_resume_narration
    await turn.assemble(recent)
    mention_target = await video_target_hint(db, project, request.mentions)
    turn._editor_output_pin = mention_target
    opening = await db.get(Message, turn_id) if turn_id is not None else None
    from app.chat.media_journey import initial_media_journey, visual_results

    turn.media_journey = media_journey or initial_media_journey(opening)
    if turn.media_journey is not None:
        turn.media_visual_results = await visual_results(
            db, project.id, opening_id=turn.media_journey["opening_id"],
            draft_id=media_resume_draft.candidate_id if media_resume_draft else None,
        )
    confirmation = ((opening.intent or {}) if opening is not None else {}).get("video_confirmation")
    turn.video_confirmation = confirmation
    # 言语提交协议武装 (speech-commit protocol, ADR-099 §7): on the SSE path
    # every turn arms the terminal buffer — iteration 0 is the only
    # streaming iteration, so its prose / preview frames are exactly the
    # speech a terminal rejection would retract. The one-shot path streams
    # nothing and needs no buffer. The buffer holds delta + tool_ready ONLY
    # (三通道分家): on_tool_call stays LIVE — it feeds the Activity
    # projector's name_known (the read/repair work evidence + G1's
    # cancelled-frame rejection forensics ride their own undeferred
    # channel) and the phase-clear is liveness chrome, never adjudication-
    # dependent speech. The rejection seat is the wrapped on_loop_event:
    # any ToolRejected retracts the stale queue at once (RETRY re-arms by
    # construction) and marks the turn frame-silent; the interim_prose channel
    # flushes the queue FIRST (prose spoken before a read lands before the
    # read EXECUTES — the emission seat sits pre-execute, ADR-104 发射时点
    # 修订, so a waiting read never holds the waiter line hostage), then
    # streams live — the buffer stays armed through it.
    if on_delta is not None:
        deferred = DeferredFrames({"delta": on_delta, "tool_ready": on_tool_ready})
        turn.deferred = deferred
        on_delta = deferred.wrap("delta")
        on_tool_ready = deferred.wrap("tool_ready")
        base_on_loop_event = on_loop_event

        async def on_loop_event_with_retract(event) -> None:
            if isinstance(event, LoopToolRejected):
                deferred.retract()
            if base_on_loop_event is not None:
                await base_on_loop_event(event)

        on_loop_event = on_loop_event_with_retract
        base_on_interim_prose = _interim_prose_callback(db, turn.conversation_id, on_interim_prose, turn_id)

        async def on_interim_prose_after_flush(text: str) -> None:
            if deferred.armed:
                await deferred.flush()
            await base_on_interim_prose(text)

        interim_prose_hook = on_interim_prose_after_flush
    else:
        interim_prose_hook = _interim_prose_callback(db, turn.conversation_id, on_interim_prose, turn_id)
    from app.chat.conversation_context import ConversationContext, conversation_context_tool
    from app.chat.turn_tools import tools_for_bound_skill
    conversation_context = (
        ConversationContext(conversation_id=turn.conversation_id, owner_id=turn.user_id,
                            turn_id=turn_id, skill=getattr(turn, "skill", None),
                            resume_turn=media_resume_pending is not None,
                            resume_draft=media_resume_draft)
        if turn_id is not None else None
    )
    turn._conversation_context = conversation_context
    context_tools = [conversation_context_tool()] if conversation_context is not None else []

    from app.chat.readiness import creative_state_for_pending, infer_task_kind, settled_website_question
    from app.pipeline.assets import urls_in_text
    turn.infer_kwargs["pending_question"] = None
    website_question_settled = settled_website_question(recent, turn_id)

    def assemble_round(**facts):
        target_hint = mention_target
        if media_resume_draft is not None:
            from app.chat.media_journey import MediaDraftUnavailable

            if not any(draft.candidate_id == media_resume_draft.candidate_id for draft in facts["drafts"]):
                raise MediaDraftUnavailable("The settled Run's current draft failed identity verification")
            target_hint = {"draft_id": media_resume_draft.candidate_id}
        current_pending = turn._current_pending()
        source_text = (
            request.message if infer_task_kind(request.message) == "website_promo"
            else (current_pending.prompt if current_pending is not None else "") or request.message
        )
        if media_resume_pending is not None:
            source_text = media_resume_pending.prompt
        assembly = assemble_video_round({
            **facts,
            "media_journey": turn.media_journey,
            "media_visual_results": turn.media_visual_results,
            "website_question_settled": website_question_settled,
            "group_answer_submitted": group_answer_submitted,
            "speech_language": speech_language or getattr(conversation, "ui_language", None),
            "settled_narration": turn.media_resume_narration,
            "mode": "plan",
            "skill": turn.skill,
            "user_text": request.message,
            "source_text": source_text,
            "video_confirmation": confirmation,
            "production_requested": requested_video_production(request.message),
            "pending_question": lambda: turn.pending_q,
            "last_preview": getattr(turn, "_editor_last_preview", None),
            "recent_edit": getattr(turn, "_editor_recent", None),
            "editor_labels": turn.__dict__.setdefault("_editor_labels", {}),
            "target_hint": target_hint,
            "material_pending": bool(urls_in_text(request.message) or request.attachments or request.mentions),
            "creative_state": creative_state_for_pending(current_pending),
            "package_sessions": turn.__dict__.setdefault("_skill_package_sessions", {}),
        })
        turn._video_base_ref = (
            (assembly.caller_state or {}).get("video_target") or {}
        ).get("base_ref")
        turn.media_state = (assembly.caller_state or {}).get("media_state")
        if turn.media_state and turn.media_state["phase"] == "audio":
            from dataclasses import replace
            from app.chat.media_journey import finish_narration_batch
            async def finish(observations):
                result = await finish_narration_batch(turn, observations)
                if result and result.stop_after_observation:
                    await turn._resolve_deferred()
                return result
            assembly = replace(assembly, tools=[
                replace(tool, batchable=True, finish_batch=finish) if tool.name == "prepare_narration" else tool
                for tool in assembly.tools
            ])
        return assembly

    speech_language = conversation_speech_language(recent or [])
    try:
        result = await intent_router.call_loop(
            turn.execute,
            dialogue=conversation_messages(recent or []),
            speech_language_hint=speech_language,
            tools=[*tools_for_bound_skill(intent_router.tools, turn.skill), *context_tools],
            round_assembler=assemble_round,
            on_delta=on_delta,
            on_reasoning=on_reasoning,
            on_tool_call=on_tool_call,
            on_tool_ready=on_tool_ready,
            on_interim_prose=interim_prose_hook,
            on_loop_event=on_loop_event,
            should_stop_rejection=video_rejection_stop,
            refresh_context=context_reader,
            restore_context=conversation_context.restore if conversation_context else None,
            on_context_event=conversation_context.record if conversation_context else None,
            candidate_scope=CandidateScope(owner_id=str(user_id), conversation_id=str(turn.conversation_id)),
            **turn.infer_kwargs,
        )
    except LLMError:
        if turn.media_state is None:
            raise
        await turn._resolve_deferred()
        zh = (speech_language or getattr(conversation, "ui_language", None) or "").startswith("zh")
        text = ("制作助手暂时无法继续，素材准备已暂停。" if zh else
                "Media preparation paused because the editing assistant is unavailable.")
        message = await _create_message(
            db, conversation.id, "assistant", text,
            intent={"media_journey": {**turn.media_journey, "state": "blocked"}},
        )
        outcome = (message, None, turn.settled_pending, [])
    else:
        outcome = await turn.finish(result)
    if (
        outcome[0] is not None
        and turn_id is not None
        and outcome[0] is not outcome[2]
    ):
        # Every newly-created terminal row shape (plain reply, dock, start
        # speech) carries the opening-user association. A prose-less Start
        # returns the OLD answered plan row as its echo; that row keeps its
        # original turn instead of being re-parented.
        outcome[0].turn_id = turn_id
    return outcome



__all__ = ["run_plan_turn", "PlanTurn", "PlanTurnOutcome"]
