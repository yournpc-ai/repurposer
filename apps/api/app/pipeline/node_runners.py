"""Internal node crew (ADR-039 P2 objectified): the non-tool kernel nodes.

``preprocess`` / ``persona_bootstrap`` / ``understand`` /
``plan`` / ``interrupt`` / ``render`` — these never enter the
proposal space (CHAT_ARCH §4). Tool nodes live in their tool packages
(``app/tools/<pkg>/node.py``); the full ``NODE_KINDS`` table self-populates
as the registry door (``app/tools/__init__.py``) imports this module and the
packages. Every class is a ``NodeBase`` declaration whose ``run`` body moved
here verbatim from the P1 runner functions.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import MAX_CHARS_PER_TEXT
from app.agents.contexts import _generation_context
from app.agents.registry import plan, understand, persona
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    EMOTIONAL_TONES,
    Option,
    QuestionPayload,
    AssetStatus,
    AssetType,
    IntentSlot,
    MaterialUnderstanding,
    RenderStatus,
    Storyboard,
)
from app.models.tables import (
    Output,
    Persona,
    Project,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.beat_map import (
    build_source_blocks,
    image_refs_from_assets,
    word_axis_from_assets,
)
from app.pipeline.derivative_dispatch import derivative_output_types
from app.pipeline.edges import (
    _align_storyboard_slots,
    _compute_coverage,
    _interrupt_direction,
    _load_understanding,
)
from app.pipeline.graph import (
    NODE_KINDS,
    NodeBase,
    estimate_agent,
    estimate_free,
    estimate_mechanical,
    known_output_types,
    slot_default_counts,
    token_bounds,
)
from app.pipeline.step_context import (
    _asset_digest,
    _list_assets,
    _source_language,
    _truncate,
    collect_asset_media,
)
from app.pipeline.step_display import _set_summary
from app.platform.project_context import (
    collect_asset_texts,
    resolve_persona,
)

logger = structlog.get_logger()


def _display_zh(run: WorkflowRun, project: Project, assets: list) -> bool:
    """Should this step's display strings render in Chinese?

    Follows the UI locale pinned on the run (display_language chain:
    run.context.ui_language → project language → material language) — NEVER
    the material's language alone: a Chinese UI generating from an English
    video reads Chinese step lines."""
    from app.ui_locale import display_language

    return display_language(
        run.context if isinstance(run.context, dict) else None,
        project.language,
        _source_language(project, assets),
    ).startswith("zh")


def _chain_needs_material(run: WorkflowRun) -> bool:
    """True iff any chain task's node declares a material ``requires``
    (clips' ``(MEDIA, TRANSCRIPT)`` today; writers and research declare
    ``()``). Registry-native — the same declarations the birthplace
    ∀-check enforces, so the run-time gates below can never kill a chain
    ``create_run`` already admitted. This supersedes the copy-writer
    proxy (``isinstance DerivativeWriterNode``): a research+writer chain
    with no source is every bit as material-free as a pure writer chain,
    and the proxy let it die at preprocess (2026-09-05, S8). An empty or
    unknown task book returns True (we never know — be safe)."""
    ctx = run.context if isinstance(run.context, dict) else {}
    chain_tasks = ctx.get("tasks") or []
    if not chain_tasks:
        return True
    return any(
        bool(getattr(NODE_KINDS.get(t.get("tool")), "requires", ()))
        for t in chain_tasks
    )


class Preprocess(NodeBase):
    kind = "preprocess"
    task_name = "Analyze uploads"
    task_name_zh = "分析素材"
    # canvas_hidden (2026-08-19 二轮评审 R1): the prelude is plan's UPSTREAM —
    # folding it into the 过程脊 together with plan's DOWNSTREAM (select_clips)
    # made the visible graph a 2-cycle (spine⇄artifact:plan): the 任务书
    # landed at the bottom of the product column with a loop-back edge
    # sweeping the canvas. Hiding the prelude restores the clean DAG
    # (素材→任务书→脊→产物); its state still lives in the step rows and the
    # chat stepper (canvas_hidden has exactly one consumer — runFlow).
    canvas_hidden = True

    def estimate(self, ctx: dict) -> dict | None:
        """Validation only — no LLM, no priced units."""
        return estimate_free()

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Validate source material exists (texts or media), like the old inline check.

        2026-09-05 widening (supersedes the 2026-08-24 copy-writer lift):
        the gate now keys on the chain's declared ``requires``
        (``_chain_needs_material``) — any chain whose nodes all declare no
        material requirement (writers, research) ships with no source
        attached, the draft grounded by prompt + persona + research.
        Chains that DO declare (clips' MEDIA/TRANSCRIPT) keep the gate —
        and since the birthplace ∀-check already 422s those when the
        project lacks the input, this raise is the belt to its suspenders.
        """
        needs_material = _chain_needs_material(run)

        asset_texts = await collect_asset_texts(db, project.id)
        assets = await _list_assets(db, project.id)
        has_media = any(a.file_url for a in assets)
        if not asset_texts and not has_media and needs_material:
            raise ValueError("No source material to analyze")
        logger.info(
            "generation_asset_inputs_collected",
            project_id=str(project.id),
            text_count=len(asset_texts),
            media_asset_count=sum(1 for a in assets if a.file_url),
            needs_material=needs_material,
        )
        # Done summary (a finished step must never keep the progressive stage
        # copy — "正在分析…" reading on a ✓ row). Quantified by file count;
        # a material-free chain with no source says so instead of "0 assets".
        if not assets and not needs_material:
            await _set_summary(
                node.id,
                "无素材输入，直接生成"
                if _display_zh(run, project, assets)
                else "No source material — drafting directly",
            )
            return []
        n = sum(1 for a in assets if a.file_url) or len(assets)
        await _set_summary(
            node.id,
            f"分析了 {n} 个素材" if _display_zh(run, project, assets) else f"Analyzed {n} assets",
        )
        return []


class PersonaBootstrap(NodeBase):
    kind = "persona_bootstrap"
    task_name = "Prepare persona"
    task_name_zh = "准备人设"
    agents = (persona,)
    # canvas_hidden — same prelude rule as Preprocess (2026-08-19 二轮评审
    # R1: the spine must never hold steps from both sides of the 任务书).
    canvas_hidden = True

    def estimate(self, ctx: dict) -> dict | None:
        """The one extraction call — free when a persona is already mounted
        (the run's early-exit, knowable at compile)."""
        if ctx["persona_exists"]:
            return estimate_free()
        chars = min(ctx["text_chars"], 20_000 * ctx["text_count"])
        return estimate_agent(token_bounds(chars + 300), [200, 800])

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Return the project's persona, or auto-create one from source texts.

        Moved verbatim out of run_generation: the homepage no longer forces the
        user to pick/create a persona, so the first run derives a default persona
        from the transcript. Now addressable + metered as its own node.

        Every exit bakes a done summary — a finished step must never keep the
        progressive stage copy (the ✓ "正在准备你的人设…" bug class).
        """
        zh = _display_zh(run, project, await _list_assets(db, project.id))
        if project.persona_id:
            mounted = await db.get(Persona, project.persona_id)
            name = mounted.name if mounted is not None else None
            await _set_summary(
                node.id,
                f"人设就位：{name}" if zh and name else f"Persona ready: {name}" if name else "人设就位" if zh else "Persona ready",
            )
            return []

        asset_texts = await collect_asset_texts(db, project.id)
        trimmed = [t[:20_000] for t in asset_texts if t and t.strip()]
        if not trimmed:
            await _set_summary(
                node.id,
                "没有文字素材，未建人设" if zh else "No text material — persona skipped",
            )
            return []

        try:
            memory = await persona.call(
                persona_name=project.title or "Persona",
                persona_title=None,
                language=project.language or "en",
                asset_texts=trimmed,
            )
        except Exception as e:  # noqa: BLE001 — persona bootstrap never fails the run
            logger.warning(
                "auto_persona_extraction_failed",
                project_id=str(project.id),
                error=str(e),
            )
            await _set_summary(
                node.id,
                "人设提取失败，继续生成" if zh else "Persona extraction failed — continuing",
            )
            return []

        persona_row = Persona(
            user_id=project.user_id,
            # LLM-synthesized persona label — project.title is the first uploaded
            # file's name (see HomeComposer), which must not become the persona name.
            name=_truncate(memory.name, 255) or project.title or "Auto Persona",
            title=None,
            language=project.language or "en",
            core_values=memory.core_values or [],
            favorite_metaphors=memory.favorite_metaphors or [],
            sentence_style=_truncate(memory.sentence_style, 255) or "",
            # Bare str from the LLM — normalize out-of-enum values, or the
            # row poisons every PersonaContext serialization that reads it.
            emotional_tone=(
                memory.emotional_tone
                if memory.emotional_tone in EMOTIONAL_TONES
                else "rational"
            ),
            typical_hooks=memory.typical_hooks or [],
            avoid_words=memory.avoid_words or [],
            audience=_truncate(memory.audience, 255),
            guidelines=memory.guidelines,
            cta=_truncate(memory.cta, 512),
            # System-bootstrap marker (the is_default replacement, ADR-038 §6).
            auto_created_at=datetime.now(UTC),
        )
        db.add(persona_row)
        await db.flush()

        project.persona_id = persona_row.id
        await db.flush()

        logger.info(
            "auto_created_persona",
            project_id=str(project.id),
            persona_id=str(persona_row.id),
        )
        await _set_summary(
            node.id,
            f"创建了人设「{persona_row.name}」" if zh else f"Created persona “{persona_row.name}”",
        )
        return []


async def _find_reusable_understanding(
    db: AsyncSession, project: Project, digest: str
) -> Output | None:
    """The latest same-user understanding row matching the asset hash.

    Cross-project by design (期 1 素材理解前移): the digest is
    content-addressed, so any earlier materialization — a run's node or an
    upload-time warm row — in ANY of the user's projects satisfies the
    reuse. The row is referenced, never copied (no duplicate understanding
    rows accumulate); a stale-shaped payload fails validation at the call
    site and regenerates.
    """
    rows = (
        (
            await db.execute(
                select(Output)
                .join(Project, Output.project_id == Project.id)
                .where(
                    Project.user_id == project.user_id,
                    Output.type == "material_understanding",
                )
                .order_by(Output.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        if (row.source_ref or {}).get("asset_hash") == digest:
            return row
    return None


async def _materialize_understanding(
    project: Project, assets: list
) -> MaterialUnderstanding:
    """The one understand LLM call — the run's node and the upload-time warm
    share it (same blocks / word axis / image refs, same postprocess snapping)."""
    asset_media = await collect_asset_media(assets)
    return await understand.call(
        source_blocks=build_source_blocks(assets),
        asset_media=asset_media,
        word_axis=word_axis_from_assets(assets),
        image_refs=image_refs_from_assets(assets),
    )


async def warm_understanding(project_id: UUID) -> None:
    """Upload-time materialization (期 1 素材理解前移): once every project
    asset has completed processing, build the understanding before any run
    asks, so the first run's understand node reuses it at zero LLM cost.

    Runs outside a workflow step — metering's bind-less no-op is the
    documented request-path precedent (the per-call ledger lands with the
    agent_calls 台账, PROGRESS 需求池); the row carries
    ``source_ref.warmed=true``. Never raises: a warm failure only means the
    run path pays the call later.
    """
    try:
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, project_id)
            if project is None:
                return
            assets = await _list_assets(db, project_id)
            if not assets or any(
                a.processing_status != AssetStatus.COMPLETED for a in assets
            ):
                return  # a later asset's completion re-triggers the warm
            asset_texts = [
                t for a in assets if (t := (a.extracted_text or a.transcript))
            ]
            has_media = any(
                (a.type == AssetType.IMAGE and a.file_url)
                or (a.type == AssetType.SLIDES and a.slide_pages)
                or (a.type == AssetType.VIDEO and a.file_url)
                for a in assets
            )
            if not asset_texts and not has_media:
                return
            digest = _asset_digest(assets)
            if await _find_reusable_understanding(db, project, digest) is not None:
                logger.info("understanding_warm_reuse_hit", project_id=str(project_id))
                return
            understanding = await _materialize_understanding(project, assets)
            row = Output(
                project_id=project.id,
                workflow_step_id=None,
                type="material_understanding",
                language=_source_language(project, assets),
                provenance="generated",
                payload=understanding.model_dump(mode="json"),
                source_ref={"asset_hash": digest, "warmed": True},
            )
            db.add(row)
            await db.commit()
            logger.info(
                "understanding_warmed",
                project_id=str(project_id),
                arguments=len(understanding.key_arguments),
                quotes=len(understanding.quotable_lines),
                beats=len(understanding.topic_boundaries),
            )
    except Exception as e:  # noqa: BLE001 — warm is best-effort, the run path pays later
        logger.warning(
            "understanding_warm_failed", project_id=str(project_id), error=str(e)
        )


class Understand(NodeBase):
    kind = "understand"
    task_name = "Understand material"
    task_name_zh = "看懂素材"
    agents = (understand,)

    def canvas_group(self, node):
        return "plan"

    def estimate(self, ctx: dict) -> dict | None:
        """One multimodal call: texts trimmed to MAX_CHARS_PER_TEXT each plus
        a per-item media bound. An asset-hash reuse zeroes the ACTUAL — the
        quote stays the fresh-call cost (reuse is the ledger-side saving)."""
        chars = min(ctx["text_chars"], MAX_CHARS_PER_TEXT * ctx["text_count"])
        prompt = token_bounds(chars)
        prompt[0] += 800 * ctx["media_count"]
        prompt[1] += 4000 * ctx["media_count"]
        return estimate_agent(prompt, [400, 2500])

    async def reuse(
        self,
        db: AsyncSession,
        run: WorkflowRun,
        node: WorkflowStep,
        project: Project,
        assets: list,
    ) -> UUID | None:
        """Idempotent reuse (asset-hash) — the ``reuse()`` protocol's first case.

        The reuse predicate is the content-addressed asset hash: media
        downloads and the (expensive, multimodal) LLM call only happen when
        no same-user understanding row matches — whether the hit was
        materialized by an earlier run or by the upload-time warm (期 1 前移).
        A reuse returns the earlier row's id, so no duplicate understanding
        rows accumulate and the node costs nothing.
        """
        digest = _asset_digest(assets)
        latest = await _find_reusable_understanding(db, project, digest)
        if latest is not None:
            try:
                cached = MaterialUnderstanding.model_validate(latest.payload)
            except Exception:  # noqa: BLE001 — stale shape: fall through, regenerate
                logger.warning(
                    "understanding_reuse_payload_invalid", output_id=str(latest.id)
                )
            else:
                # Step lines follow the UI locale pinned on the run, never
                # the material's language (display_language chain).
                zh = _display_zh(run, project, assets)
                await _set_summary(
                    node.id,
                    f"复用素材理解 · {len(cached.key_arguments)} 个论点"
                    if zh
                    else f"Reused understanding · {len(cached.key_arguments)} arguments",
                )
                logger.info(
                    "understand_reused",
                    project_id=str(project.id),
                    output_id=str(latest.id),
                )
                return latest.id
        return None

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Understand node: material-scoped understanding, reused across runs.

        2026-09-05 widening (supersedes the 2026-08-25 copy-writer carve-out):
        when the chain declares no material ``requires`` the material is
        optional — the understanding would only re-summarize an absent
        source, so we materialize a STUB row (core_thesis="" + every list
        field empty) and write it as a fresh non-reusable Output. The
        downstream ``plan`` and the four writer agents all handle the
        empty-shape understanding gracefully (their prompts' ``{% for %}``
        loops degrade to nothing rendered, and the slot-level fallback
        copy lights up). plan writes its own matching stub on the same
        gate, so the executor's _load_plan_prelude_outputs always returns
        a paired (understanding, storyboard) tuple."""
        assets = await _list_assets(db, project.id)

        if not _chain_needs_material(run):
            asset_texts = await collect_asset_texts(db, project.id)
            has_media = any(a.file_url for a in assets)
            if not asset_texts and not has_media:
                zh = _display_zh(run, project, assets)
                understanding = MaterialUnderstanding(
                    core_thesis="",
                    overall_summary=(
                        "本轮无素材输入，draft 由 persona + 用户指令生成。"
                        if zh
                        else "No source material — this run drafts from "
                        "persona + user instruction (research grounding when "
                        "chained)."
                    ),
                )
                row = Output(
                    project_id=project.id,
                    workflow_step_id=node.id,
                    type="material_understanding",
                    language=_source_language(project, assets),
                    provenance="generated",
                    payload=understanding.model_dump(mode="json"),
                    source_ref={"asset_hash": None, "copy_writer_stub": True},
                )
                db.add(row)
                await db.flush()
                await _set_summary(
                    node.id,
                    "无素材输入，跳过素材理解" if _display_zh(run, project, assets)
                    else "No source material — understanding skipped",
                )
                logger.info(
                    "understand_copy_writer_stub",
                    project_id=str(project.id),
                )
                return [row.id]

        reused = await self.reuse(db, run, node, project, assets)
        if reused is not None:
            return [reused]

        understanding = await _materialize_understanding(project, assets)

        row = Output(
            project_id=project.id,
            workflow_step_id=node.id,
            type="material_understanding",
            language=_source_language(project, assets),
            provenance="generated",
            payload=understanding.model_dump(mode="json"),
            source_ref={"asset_hash": _asset_digest(assets)},
        )
        db.add(row)
        await db.flush()
        zh = _display_zh(run, project, assets)
        await _set_summary(
            node.id,
            f"理解了 {len(understanding.key_arguments)} 个论点 · "
            f"{len(understanding.quotable_lines)} 条金句 · "
            f"{len(understanding.topic_boundaries)} 个节拍"
            if zh
            else f"Understood {len(understanding.key_arguments)} arguments · "
            f"{len(understanding.quotable_lines)} quotes · "
            f"{len(understanding.topic_boundaries)} beats",
        )
        return [row.id]


class Interrupt(NodeBase):
    kind = "interrupt"
    task_name = "Pick a direction"
    task_name_zh = "选定方向"

    def canvas_group(self, node):
        return "plan"

    def canvas_text(self, node):
        # The plan card's body = the direction the user picked, in full (the
        # spec summary is truncated to a line).
        answer = (node.spec or {}).get("answer") or {}
        return answer.get("text") or None

    def estimate(self, ctx: dict) -> dict | None:
        """Zero by ruling (P4): thin node, no LLM — the options are
        code-derived from the understanding."""
        return estimate_free()

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Direction interrupt (期 4): the run's one HITL pause, review tier only.

        Thin-node rule — no heavy work before asking, and zero LLM (prohibited-
        behavior #4): the options are code-derived from the understanding's key
        arguments. First entry derives options → docks the question (committed in
        its own session; ``workflow_run_id`` marks the interrupt dispatch) →
        raises Suspend, and execute_step parks the node in ``waiting`` with the
        options in ``spec.suspend_payload`` and the run in WAITING_HUMAN.

        Re-entry is queue-based: the answer endpoint writes ``spec.answer`` and
        flips the node back to pending; this runner then re-runs from the top,
        takes the answer branch below, and goes straight to done (its summary is
        the chosen direction). plan reads the answer off this node's
        spec — see ``_interrupt_direction``.
        """
        from app.chat.service import (  # deferred: import cycle
            dock_interrupt_question,
            finalize_bailed_runs,
        )
        from app.pipeline.orchestrator import Suspend  # deferred: import cycle

        spec = node.spec or {}
        answer = spec.get("answer")
        if answer is not None:
            # Re-entry after the human answer — record the decision as the done
            # summary. The option's label from suspend_payload wins over
            # answer.text, which may be a machine marker ("expired" — the expiry
            # sweep's auto-answer) rather than a human label. The default option
            # and freeform carry no argument id; plan re-derives the
            # semantics from spec.answer itself.
            options = (spec.get("suspend_payload") or {}).get("options") or []
            label: str | None = None
            if answer.get("kind") == "option":
                by_id = {o.get("id"): o for o in options}
                chosen = by_id.get(answer.get("option_id")) or {}
                label = chosen.get("label")
            label = label or answer.get("text")
            assets = await _list_assets(db, project.id)
            zh = _display_zh(run, project, assets)
            # The option label already carries the "Focus: "/"聚焦：" prefix —
            # strip it before wrapping with the direction word (no "方向：聚焦：").
            for prefix in ("聚焦：", "Focus: "):
                if label and label.startswith(prefix):
                    label = label[len(prefix):]
                    break
            picked = _truncate(label, 60) or ("默认" if zh else "default")
            await _set_summary(node.id, f"方向：{picked}" if zh else f"Direction: {picked}")
            return []

        understanding = await _load_understanding(db, node)
        assets = await _list_assets(db, project.id)
        zh = _display_zh(run, project, assets)

        # Options (code-derived, zero LLM): up to 3 "Focus: {argument}" + the
        # full-talk default; freeform rides via allow_freeform. The option's
        # argument id rides only in suspend_payload (the message payload stays a
        # plain Option list, same shape as a chat options question). The
        # argument TEXT renders in the UI language (text_zh/text_en display
        # alternates, legacy payloads fall back to the material's text).
        focus_word = "聚焦：" if zh else "Focus: "
        default_label = "全场高光" if zh else "Full-talk highlights"
        arguments = understanding.key_arguments[:3]
        if not arguments:
            # 准入 (2026-09-02 用户拍板): zero key arguments → the option list
            # is the default alone, and a one-option question has no branch —
            # parking for it is pure friction (the writer-only stub
            # understanding lands here: "Full-talk highlights" is clips
            # vocabulary on a post book). Auto-resolve as the default option —
            # the same spec.answer shape a human pick writes; with no
            # suspend_payload the plan read falls through to None =
            # the default direction (edges.py `_interrupt_direction`).
            node.spec = {
                **(node.spec or {}),
                "answer": {"kind": "option", "option_id": "a"},
            }
            await _set_summary(
                node.id, f"方向：{default_label}" if zh else f"Direction: {default_label}"
            )
            return []
        options = [
            Option(
                id=chr(ord("a") + i),
                label=f"{focus_word}{(arg.text_zh if zh else arg.text_en) or arg.text}",
            )
            for i, arg in enumerate(arguments)
        ]
        options.append(Option(id=chr(ord("a") + len(arguments)), label=default_label))

        question_text = (
            "这次生成想聚焦哪个方向？" if zh else "Which direction should this run focus on?"
        )
        # allow_freeform=true means ANY free text lands as the direction
        # answer and wakes the run — even "how much longer?" small talk.
        # Accepted tradeoff (2026-08-20 ruling): no intent screen on the
        # answer path; a mis-fired direction is correctable in the next turn.
        payload = QuestionPayload(kind="question", options=options, allow_freeform=True)
        async with AsyncSessionLocal() as s:
            message, bailed_run_ids = await dock_interrupt_question(
                s,
                UUID(str(project.user_id)),
                UUID(str(project.id)),
                UUID(str(run.id)),
                question_text,
                payload,
            )
            # Commit expires the ORM instance — capture the id first.
            question_message_id = str(message.id)
            await s.commit()
        # Docking superseded an older parked interrupt (single-pending
        # invariant) — its run was cascade-bailed in the same stroke; settle it.
        await finalize_bailed_runs(bailed_run_ids)
        raise Suspend(
            {
                "question_message_id": question_message_id,
                "options": [
                    {
                        "id": option.id,
                        "label": option.label,
                        "argument_id": (
                            arguments[i].id if i < len(arguments) else None
                        ),
                    }
                    for i, option in enumerate(options)
                ],
            }
        )


class Plan(NodeBase):
    kind = "plan"
    task_name = "Plan content"
    task_name_zh = "规划内容"
    agents = (plan,)

    def canvas_group(self, node):
        return "plan"

    def canvas_text(self, node):
        """Plan 卡正文 = 人话任务书摘要（不是内部工序 summary）。"""
        spec = node.spec or {}
        if spec.get("book_summary"):
            return spec["book_summary"]
        task_book = spec.get("task_book") or {}
        slots = [IntentSlot.model_validate(s) for s in task_book.get("slots", [])]
        return self._book_summary(slots, task_book.get("target_language", "en"))

    @staticmethod
    def _book_summary(slots: list[IntentSlot], target_language: str) -> str | None:
        if not slots:
            return None
        from collections import Counter

        counts = Counter(s.type for s in slots)
        zh = target_language.startswith("zh")
        type_labels = {
            "post": "LinkedIn 帖子" if zh else "LinkedIn post",
            "quotes": "名言卡" if zh else "quotes card",
            "carousel": "轮播图" if zh else "carousel",
            "article": "文章" if zh else "article",
            "clip": "片段" if zh else "clip",
        }
        lang_labels = {
            "en": "English",
            "zh": "中文",
            "de": "Deutsch",
            "fr": "Français",
            "es": "Español",
            "it": "Italiano",
        }
        parts = []
        for slot_type, count in counts.items():
            label = type_labels.get(slot_type, slot_type)
            parts.append(f"{count} {label}" if count > 1 else f"1 {label}")
        parts.append(lang_labels.get(target_language, target_language.upper()))
        return " · ".join(parts)

    def estimate(self, ctx: dict) -> dict | None:
        """One call: prompt = the upstream understanding (≤ 2500 completion
        tokens) + task book + persona/tone context; completion = the
        storyboard (per-slot fields, bounded by the slot schema)."""
        return estimate_agent([800, 4500], [300, 2500])

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Plan node: request-scoped storyboard, re-planned every run.

        Reads ONLY the upstream understanding (self-sufficiency contract) plus the
        task book and persona/tone context; coverage accountability is computed by
        code and persisted with the storyboard. The task book is passed slot by
        slot (per-slot count/focus/language); explicit slot fields are enforced
        by code after the LLM returns.

        2026-09-05 widening (supersedes the 2026-08-25 copy-writer lift fifth
        gate): when the chain declares no material ``requires`` and
        understand wrote a stub understanding, the storyboard LLM has
        nothing to plan from either — same skip rule, paired stub
        Storyboard (empty slots, empty coverage). Executors handle the
        empty storyboard: ``find_slot`` returns ``{}`` and the prompt's
        ``{{ slot.focus or default }}`` fallback fires."""
        ctx = run.context or {}
        understanding = await _load_understanding(db, node)

        if (
            not _chain_needs_material(run)
            and (understanding.core_thesis == "")
            and not understanding.key_arguments
            and not understanding.quotable_lines
        ):
            assets = await _list_assets(db, project.id)
            row = Output(
                project_id=project.id,
                workflow_step_id=node.id,
                type="storyboard",
                language=ctx.get("target_language", "en"),
                provenance="generated",
                payload=Storyboard().model_dump(mode="json"),
            )
            db.add(row)
            await db.flush()
            await _set_summary(
                node.id,
                "无素材输入，跳过分镜规划" if _display_zh(run, project, assets)
                else "No source material — storyboard skipped",
            )
            logger.info(
                "plan_copy_writer_stub",
                project_id=str(project.id),
            )
            return [row.id]

        # The storyboard's intent slots come from THIS RUN'S COMPILED GRAPH
        # (ADR-043 item 6): each generation sibling carries its task's params
        # as spec.slot — the graph the user confirmed IS the dispatch input,
        # so panel-edited chains and multi-version chains plan exactly as
        # compiled. Per-type order = seq order = the compile's slot_index
        # assignment (executors pick their slot by that same ordinal).
        siblings = (
            await db.execute(
                select(WorkflowStep)
                .where(WorkflowStep.run_id == run.id)
                .order_by(WorkflowStep.seq)
            )
        ).scalars().all()
        parsed = [
            IntentSlot.model_validate(s.spec["slot"])
            for s in siblings
            if (s.spec or {}).get("slot")
        ]
        intent_slots = [s for s in parsed if s.type in known_output_types()]
        # Targeted derivative runs: the storyboard plans only for the target type.
        target_type = node.spec.get("target_type")
        if target_type in derivative_output_types():
            intent_slots = [IntentSlot(type=target_type)]
        if not intent_slots:
            intent_slots = [IntentSlot(type="clips")]
        # count_default rides per slot (registry-derived — the template never
        # hardcodes a number; the retired inline mirror drifted once already).
        count_defaults = slot_default_counts()
        task_book = {
            "slots": [
                {**s.model_dump(mode="json"), "count_default": count_defaults.get(s.type)}
                for s in intent_slots
            ],
            "target_language": ctx.get("target_language", "en"),
        }
        # Direction interrupt (期 4): the user's pick steers the prompt — option
        # → priority argument, freeform → guidance text, default → absent (the
        # current behavior). Explicit slot focus still wins (code-enforced below).
        direction = await _interrupt_direction(db, node)
        if direction:
            task_book["direction"] = direction

        persona_row = await resolve_persona(db, project)
        generation_context = _generation_context(run, project, persona_row)

        storyboard = await plan.call(
            understanding=understanding,
            context=generation_context,
            task_book=task_book,
            # Registry-derived (N-32): per-type count defaults ride the prompt
            # as data, never restated by hand in the template.
            count_defaults_text=", ".join(
                f"{t} → {d}" for t, d in slot_default_counts().items()
            ),
        )
        storyboard.slots = _align_storyboard_slots(storyboard.slots, intent_slots)
        storyboard.coverage = _compute_coverage(storyboard, understanding)

        row = Output(
            project_id=project.id,
            workflow_step_id=node.id,
            type="storyboard",
            language=ctx.get("target_language", "en"),
            provenance="generated",
            payload=storyboard.model_dump(mode="json"),
        )
        db.add(row)
        await db.flush()
        assets = await _list_assets(db, project.id)
        zh = _display_zh(run, project, assets)
        # 任务书摘要落 spec，供 canvas_text 投影到 plan 节点。
        book_summary = self._book_summary(intent_slots, ctx.get("target_language", "en"))
        if book_summary:
            node.spec = {**(node.spec or {}), "book_summary": book_summary, "task_book": task_book}
        await _set_summary(
            node.id,
            f"规划了 {len(storyboard.slots)} 个槽位 · "
            f"{len(storyboard.coverage.unused_arguments)} 个论点未使用"
            if zh
            else f"Planned {len(storyboard.slots)} slots · "
            f"{len(storyboard.coverage.unused_arguments)} arguments unused",
        )
        return [row.id]


class RenderRequest(NodeBase):
    kind = "render"
    task_name = "Render video"
    task_name_zh = "渲染视频"
    # Render nodes materialize at runtime (D2 fan-out from producer nodes) as
    # well as at compile time (targeted re-render) — the recipe-flow
    # reconciliation treats them as present in every producer graph.
    runtime_fanout = True
    # Render is 1:1 with its clip product — never a canvas node; its state
    # projects onto the product card in place (ADR-041 D6 修订).
    canvas_hidden = True

    def estimate(self, ctx: dict) -> dict | None:
        """Render 按秒 (mechanical exact): the target clip's payload duration,
        knowable for a compile-time targeted re-render. Runtime fan-out
        renders never reach this — they are born mid-run and stay NULL
        (unquoted this week, P4 NULL semantics)."""
        target_id = str((ctx["spec"] or {}).get("target_id") or "")
        seconds = ctx["output_seconds"].get(target_id)
        if seconds is None:
            return None
        return estimate_mechanical({"render_seconds": float(seconds)})

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Targeted re-render: flip render_status back to PENDING (scope=render).

        The render chain (outputs.render_status claim) picks it up and mirrors
        terminal state back onto this node — the runner only enqueues.
        """
        target_id = node.spec.get("target_id")
        if not target_id:
            raise ValueError("target_id is required for render")

        output = await db.get(Output, UUID(str(target_id)))
        if output is None or output.project_id != project.id:
            raise ValueError("Target clip not found")
        if not output.render_spec:
            raise ValueError("Clip has no render_spec")

        output.render_status = RenderStatus.PENDING
        output.render_error = None
        await db.flush()
        return []
