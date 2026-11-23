"""Native project editor turn, grounded context assembly and tool execution."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.candidate_correction import CandidateRejected, CandidateScope
from app.agents.tool_loop import (
    TerminalRefusal,
    ToolObservation,
)
from app.agents.tool_loop import (
    ToolRejected as LoopToolRejected,  # alias: app.tools.ToolRejected (the
    # chain-adjudication exception, imported below) shadows the loop event's
    # name in this module — the retract seat must match the LOOP's class
)
from app.chat.deferred_frames import DeferredFrames
from app.chat.intent import intent_router
from app.chat.perception import PERCEPTION_TOOLS, run_perception_tool
from app.chat.perception.executes import speaker_form_lines, understanding_digest_lines
from app.chat.service import (
    _ask_content,
    _bare_question,
    _cannot_do_text,
    _create_message,
    _design_no_progress_text,
    _dock_question,
    _interim_prose_callback,
    _loop_incomplete_text,
    _reminder_block,
    _sfx_import_failure_text,
    _topic_gate_question,
    _video_capability_text,
    _video_review_failure_text,
    latest_pending_question,
    merge_brief,
    resolve_suggestion_note,
)
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
    GetNarrationAlignmentArgs,
    ImportSfxArgs,
    MaterialUnderstanding,
    ProjectBrief,
    PlanAnswerArgs,
    PlanAskArgs,
    AlignRecordingArgs,
    QuestionPayload,
    QuestionProposal,
    ReviewVideoArgs,
    SearchSfxArgs,
    SelectMusicArgs,
    SelectVideoPresetArgs,
    ShowMusicCandidatesArgs,
    ShowVideoPresetsArgs,
    SkillReference,
    missing_brief_question_items,
    question_group_digest,
    resolve_recommended_id,
)
from app.models.tables import Asset, CompositionVersion, Message, Persona, Project, User
from app.pipeline.asset_processing import has_any_text_material
from app.pipeline.assets import (
    asset_text_content,
    create_transcript_asset_from_text,
    create_web_page_assets_committed_from_urls,
    prime_web_page_captures_from_text,
)
from app.platform.project_context import resolve_default_persona
from app.platform.user_settings import read_confirmation_prefs

logger = structlog.get_logger()

# The return shape the service layer's callers hold (unchanged):
# (assistant message, started run id, answered task-book question,
# cascade-bailed run ids). The assistant message is None when the turn
# closes without a row (the degrade paths land their own shape).
PlanTurnOutcome = tuple[Message | None, Message | None]


class PlanTurn:
    """Native tool dispatch and conversation facts for one project opening."""

    def __init__(
        self,
        db: AsyncSession,
        user_id: UUID,
        conversation,
        project: Project,
        request: ChatRequest,
        skill: SkillReference | None = None,
        on_phase=None,
        on_activity=None,
        on_candidates=None,
        on_row_append=None,
        turn_id: UUID | None = None,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.turn_id = turn_id
        self.conversation_id = UUID(str(conversation.id))
        self.project = project
        self.request = request
        self.skill = skill
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
        self.stored: ProjectBrief | None = None
        self.pending_q: Message | None = None
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
        self.deferred: DeferredFrames | None = None
        # 建议点选 provenance (ADR-099 §4): this turn's message IS a
        # suggestion pick → the resolution note rides into the router's
        # message (never into self.text — the gates and keyword detectors
        # read the user's own words only).
        self.suggestion_note: str | None = None

    # ---- assembly (the retired _plan_turn's pre-call block, verbatim) ------

    def _current_pending(self) -> ProjectBrief | None:
        """Read the latest ProjectBrief after independently committed writes."""
        self.stored = (
            ProjectBrief.model_validate(self.project.pending_brief)
            if isinstance(self.project.pending_brief, dict)
            else None
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
        # answer tool's reply gets the reminder tail).
        pending_q = await latest_pending_question(db, self.conversation_id)
        if pending_q is not None and (pending_q.question or {}).get("kind") != "question":
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
            from app.pipeline.understanding import (  # deferred: pipeline weight
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

        recent_lines: list[str] = []
        from app.chat.video_turn_seats import video_context_lines
        recent_lines.extend(await video_context_lines(
            db, project, request.mentions,
            skill=self.skill,
        ))
        # The presented chain (ADR-043): the panel's current task list when the
        # caller sends one (hand edits ride along), else the stored plan's. The
        # intent router sees it as a JSON chain and re-emits the WHOLE refined chain
        # — panel edits survive because the LLM preserves what the message does
        # not revise (chat revisions always win; the field-level merge machinery
        # died with the slots grammar).
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
        self.infer_kwargs = dict(
            message=self.suggestion_note or "",
            brief=brief_in,
            persona=persona,
            pending_question=pending_q,
            filename=filename,
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
            # ADR-117 D1 — the confirmation-settings fact (the system
            # template's mode-conditional close law reads it).
            confirmation=self.confirmation,
        )

    def _role_pins(self) -> dict[str, str | None]:
        """Preserve previously settled roles when serializing an existing brief."""
        return {
            "source_asset_id": self.stored.source_asset_id if self.stored else None,
            "exemplar_asset_id": self.stored.exemplar_asset_id if self.stored else None,
        }

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

    async def execute(self, name: str, params, prose: str) -> str | None | ToolObservation | TerminalRefusal | CandidateRejected:
        """The LoopExecute seat: validate → (reject: feedback, zero writes) →
        accept: writes + the outcome stashed → None (terminal stop). A
        PERCEPTION call short-circuits the seats above: reads are dispatched
        to the family registry and ride back as a ToolObservation (the loop
        iterates — 终态工具一调即停 covers the terminal tools only)."""
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
        # Require the model to address the pending question before writing.
        if (
            name == "create_video"
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

    async def _dispatch(self, name: str, params, prose: str) -> str | None | ToolObservation | TerminalRefusal | CandidateRejected:
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
        if name == "review_video":
            assert isinstance(params, ReviewVideoArgs)
            from app.chat.video_turn_seats import review_video_seat
            return await review_video_seat(turn=self, args=params)
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
        if name == "align_recording":
            assert isinstance(params, AlignRecordingArgs)
            from app.chat.video_turn_seats import align_recording_seat
            return await align_recording_seat(
                project=self.project, args=params, mentions=self.request.mentions
            )
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

    async def _emit_milestone(self, key: str, count: int) -> None:
        """Fire one work-session milestone frame (iter-2 ⑥, N-57) at a door
        success — in-session interleave only, never persisted. No-op on the
        one-shot path."""
        if self.on_activity is not None:
            await self.on_activity(key, count)


    async def _emit_candidates(self, payload: dict) -> None:
        """Candidate Surface 信道: stream over SSE when attached, and always persist
        as a candidates_log message row so select_music/import_sfx resolve reliably
        across JSON, answer-resume, and refresh paths."""
        if self.on_candidates is not None:
            await self.on_candidates(payload)
            return
        from app.chat.service import record_candidates_log
        from app.models.database import AsyncSessionLocal

        ref = (
            f"direct:{self.turn_id or self.conversation_id}:"
            f"{payload.get('candidate_set_id')}:{payload.get('event')}:{payload.get('member_index')}"
        )
        async with AsyncSessionLocal() as db:
            await record_candidates_log(
                db, self.conversation_id, [payload], ref=ref, turn_id=self.turn_id,
            )
            await db.commit()


    async def _ask_user(self, params: PlanAskArgs, prose: str) -> str | None:
        """Dock one clarification interaction through the ask_user machinery."""
        stored = self._current_pending()
        from app.chat.readiness import creative_state_for_pending, creative_state_with_brief

        merged_brief = await self._absorb(
            params.brief, params.material_text, getattr(params, "material_urls", None),
        )
        group_items = []
        group_digest = None
        if params.items:
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
                "pass the bare question or group title, or call answer "
                "instead."
            )
        # Keep the original question until the user answers or dismisses it.
        if self.pending_q is not None:
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
                f"The question about {params.slot} was already asked. Use the available facts."
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
                    "role ambiguity to ask about. Use the attached material."
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
        self.project.pending_brief = ProjectBrief(
            # The birth prompt stays frozen (stored.prompt wins) — the
            # accumulated narrative retired with the brief switch.
            prompt=stored.prompt if stored and stored.prompt else self.text,
            brief=merged_brief,
            creative_state=creative_state_with_brief(
                creative_state_for_pending(stored) or CreativeState(), merged_brief
            ),
            persona_id=(
                self.request.persona_id
                or (stored.persona_id if stored else None)
            ),
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
        assistant_message = await _dock_question(
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
            intent={"ask": ask.model_dump(mode="json")},
        )
        self.outcome = (assistant_message, self.settled_pending)
        return None


    async def _answer(self, params: PlanAnswerArgs, prose: str) -> str | None:
        """answer → a plain assistant message; the stored plan stays
        untouched. The envelope seats still absorb (an answer can carry the
        user's declared material)."""
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
        self.outcome = (assistant_message, self.settled_pending)
        return None

    # ---- the outcome mapping -------------------------------------------------

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
        if self.turn_id and (result.no_progress_tool or result.exhausted or result.ended_by):
            from app.chat.editor_recovery import partial_edit_text
            from app.chat.service import _lock_turn_for_transcript_write, _prefers_zh

            # Edits committed on separate sessions. Read the fresh opening under
            # the same fence as the final reply, including any concurrent Stop.
            opening = await _lock_turn_for_transcript_write(self.db, self.turn_id)
            zh = _prefers_zh(opening.content)
            if result.no_progress_tool:
                reason = "后续调整未完成，重复尝试已停止。" if zh else "The follow-up edit did not finish. Repeated attempts have stopped."
            elif result.ended_by:
                kind = (result.refusal_facts or {}).get("kind")
                reasons = {
                    "sfx_import_failure": ("音效导入未完成。", "The sound import did not finish."),
                    "video_review_failure": ("成片复查未完成。", "The output recheck did not finish."),
                    "video_capability": ("现有工具无法完成后续调整。", "The available tools could not complete the follow-up change."),
                }
                reason = reasons.get(kind, ("后续操作未完成。", "The follow-up operation did not finish."))[0 if zh else 1]
            else:
                reason = "已达到本轮处理上限，后续工作未完成。" if zh else "The turn reached its processing limit before the follow-up work finished."
            partial = await partial_edit_text(self.db, opening, reason)
            if partial:
                message = await _create_message(self.db, self.conversation_id, "assistant", partial, turn_id=self.turn_id)
                await self._stamp_video_presentation(message)
                return message, self.settled_pending
        if result.no_progress_tool is not None:
            video_read = self._video_presentation_pending
            assistant_message = await _create_message(
                self.db,
                self.conversation_id,
                "assistant",
                _design_no_progress_text(
                    self.text,
                    exported=(getattr(self, "_editor_export", None) or {}).get("status") == "available",
                    delivered=bool(getattr(self, "_editor_delivery", None)),
                    version_saved=bool(video_read or result.version_saved),
                    video_read=video_read,
                ),
            )
            # A direct video save is real even when its later correction stops.
            # Present those saved facts and attach the normal review receipt.
            await self._stamp_video_presentation(assistant_message)
            return assistant_message, self.settled_pending
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
            return assistant_message, self.settled_pending
        if not result.exhausted:
            # The bare final reply (no tool called) — the read-tolerant
            # answer floor: the prose IS the reply.
            content = result.prose.strip() or (
                _design_no_progress_text(
                    self.text, version_saved=True, video_read=self._video_presentation_pending,
                )
                if result.version_saved else _cannot_do_text(self.text)
            )
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
            return assistant_message, self.settled_pending
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
            self.project.pending_brief = ProjectBrief(
                prompt=stored.prompt if stored and stored.prompt else self.text,
                brief=merged_brief,
                creative_state=creative_state_with_brief(
                    creative_state_for_pending(stored) or CreativeState(), merged_brief
                ),
                persona_id=(
                    self.request.persona_id
                    or (stored.persona_id if stored else None)
                ),
                **video_carry_state(stored),
                **self._role_pins(),
            ).model_dump(mode="json")
            topic_ask = _topic_gate_question(self.text)
            assistant_message = await _dock_question(
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
                intent={"ask": topic_ask},
            )
            return assistant_message, self.settled_pending
        assistant_message = await _create_message(
            self.db,
            self.conversation_id,
            "assistant",
            _loop_incomplete_text(self.text, result),
        )
        return assistant_message, self.settled_pending


async def run_plan_turn(
    db: AsyncSession,
    user_id: UUID,
    conversation,
    project: Project,
    request: ChatRequest,
    skill: SkillReference | None = None,
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
    group_answer_submitted: bool = False,
    authorized_media: Message | None = None,
    review_pinned_export: bool = False,
) -> PlanTurnOutcome:
    """Assemble the opening and its receipts, execute native tools, and persist the reply."""
    turn = PlanTurn(
        db, user_id, conversation, project, request,
        skill=skill,
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
    await turn.assemble(recent)
    mention_target = await video_target_hint(db, project, request.mentions)
    completed_media = []
    if authorized_media is not None:
        completed_media = list(await db.scalars(select(Message.intent["media_result"]).where(
            Message.turn_id == turn_id, Message.conversation_id == conversation.id,
            Message.intent.has_key("media_job"), Message.intent.has_key("media_result"),
        ).order_by(Message.seq)))
        if authorized_media.intent.get("composition_id"):
            mention_target = {"composition_id": authorized_media.intent["composition_id"]}
            turn._inspected_version = authorized_media.intent["version_id"]
        if authorized_media.intent["media_result"].get("role") == "export":
            turn._editor_export = authorized_media.intent["media_result"]
            mention_target["version_id"] = authorized_media.intent["version_id"]
    turn._editor_output_pin = mention_target
    opening = await db.get(Message, turn_id) if turn_id is not None else None
    if opening and (getattr(turn, "_editor_export", None) or {}).get("status") == "available":
        # The resumed model receives the opening text again. Restore its actual
        # edits from immutable versions before it decides what remains to do.
        markers = {m["request"]: m["tool"] for m in (opening.intent or {}).get("editor_commits", [])}
        if markers:
            exported_version = await db.get(CompositionVersion, UUID(turn._editor_export["composition_version_id"]))
            committed = (await db.execute(select(CompositionVersion.request_id, CompositionVersion.version).where(
                CompositionVersion.composition_id == exported_version.composition_id,
                CompositionVersion.version <= exported_version.version,
                CompositionVersion.request_id.in_(markers),
            ).order_by(CompositionVersion.version))).all()
            if committed:
                turn._editor_recent = {
                    "composition_id": str(exported_version.composition_id), "version_id": str(exported_version.id),
                    "clips": {}, "applied": [{"tool": markers[key], "version": number} for key, number in committed],
                }
    confirmation = ((opening.intent or {}) if opening is not None else {}).get("video_confirmation")
    from app.chat.video_turn_seats import preceding_delivery

    turn.preceding_delivery = await preceding_delivery(db, turn.conversation_id, opening)
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
    from app.chat.turn_tools import tools_for_bound_skill, video_rejection_stop
    conversation_context = (
        ConversationContext(conversation_id=turn.conversation_id, owner_id=turn.user_id,
                            turn_id=turn_id, skill=getattr(turn, "skill", None))
        if turn_id is not None else None
    )
    turn._conversation_context = conversation_context
    context_tools = [conversation_context_tool()] if conversation_context is not None else []

    from app.chat.readiness import creative_state_for_pending, infer_task_kind
    from app.pipeline.assets import urls_in_text
    turn.infer_kwargs["pending_question"] = None

    # Carry the resolved request alongside the user's actual dock selection.
    answered_this_opening = turn_id is not None and authorized_media is None and any(
        m.turn_id == turn_id and m.question and m.answer and not (m.intent or {}).get("media_permission")
        for m in recent or ()
    )

    def assemble_round(**facts):
        target_hint = mention_target
        current_pending = turn._current_pending()
        source_text = (
            request.message if infer_task_kind(request.message) == "website_promo"
            else (current_pending.prompt if current_pending is not None else "") or request.message
        )
        assembly = assemble_video_round({
            **facts,
            "group_answer_submitted": group_answer_submitted,
            "answered_this_opening": answered_this_opening,
            "speech_language": speech_language or getattr(conversation, "ui_language", None),
            "mode": "plan",
            "skill": turn.skill,
            "user_text": request.message,
            "attachments": request.attachments,
            "asset_mentions": {m.id: m.label for m in request.mentions or [] if m.type == "asset"},
            "source_text": source_text,
            "video_confirmation": confirmation,
            "preceding_delivery": turn.preceding_delivery,
            "exported": getattr(turn, "_editor_export", None),
            "review_pinned_export": review_pinned_export,
            "reviewed_output_id": (getattr(turn, "_video_review_report", None) or {}).get("output_id"),
            "delivered": getattr(turn, "_editor_delivery", None),
            "production_requested": requested_video_production(request.message),
            "pending_question": lambda: turn.pending_q,
            "media_receipts": completed_media,
            "authorized_media": authorized_media.intent["media_result"] if authorized_media is not None else None,
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
        return assembly

    speech_language = conversation_speech_language(recent or [])
    dialogue = conversation_messages(recent or [])
    if authorized_media is not None:
        dialogue = [{"role": "user", "content": request.message}]
        if authorized_media.intent["media_result"].get("status") == "declined":
            dialogue.extend([
                {"role": "assistant", "content": authorized_media.content},
                {"role": "user", "content": (authorized_media.answer or {}).get("text") or "Decline"},
            ])
    result = await intent_router.call_loop(
        turn.execute,
        dialogue=dialogue,
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
    outcome = await turn.finish(result)
    if (
        outcome[0] is not None
        and turn_id is not None
        and outcome[0] is not outcome[1]
    ):
        # Every newly-created terminal row shape (plain reply, dock, start
        # speech) carries the opening-user association. A prose-less Start
        # returns the OLD answered plan row as its echo; that row keeps its
        # original turn instead of being re-parented.
        outcome[0].turn_id = turn_id
    return outcome



__all__ = ["run_plan_turn", "PlanTurn", "PlanTurnOutcome"]
