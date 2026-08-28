"""Writer tools' shared node base (ADR-039 P2).

One body serves the four copy-writer nodes (post/quotes/carousel/article):
resolve the node's slot + language, load the director artifacts, call the
package's writer declaration, persist the output row. Each package's
``node.py`` declares a thin subclass (kind / output_type / slot_label /
``writer``) — the DerivativeType → writer map died with the outputs-registry
derivation. A schema rejection is answered by the harness's one bounded
repair round inside ``Agent.call`` (ADR-039 P3) — no blind retries here.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Agent, MAX_CHARS_PER_TEXT
from app.agents.contexts import _generation_context
from app.models.schemas import (
    DerivativeType,
    GenerationContext,
    MaterialUnderstanding,
    Storyboard,
    validate_derivative_content,
    validate_output_payload,
)
from app.models.tables import Output, Project, WorkflowStep, WorkflowRun
from app.pipeline.graph import NODE_KINDS, NodeBase, TRANSCRIPT, estimate_mechanical, token_bounds
from app.pipeline.images import _save_quote_card_image
from app.pipeline.step_context import _count_words
from app.pipeline.step_display import (
    _fill_summary,
    _node_slot,
    _set_stage,
    slot_tag,
    ui_lang_of,
)
from app.pipeline.edges import _load_director_outputs
from app.platform.project_context import collect_asset_texts, resolve_persona

logger = structlog.get_logger()


def derivative_output_types() -> frozenset[str]:
    """Output types owned by the copy-writer nodes (node-derived — the retired
    ``_OUTPUT_TO_DERIVATIVE_TYPE`` map has no parallel home)."""
    return frozenset(
        n.output_type
        for n in NODE_KINDS.values()
        if isinstance(n, DerivativeWriterNode) and n.output_type
    )


class CopyWriterParams(BaseModel):
    """The four copy-writer tools' shared adjudication document (outputs-
    derive, ADR-043): the writers share one node body, so their params are
    one model — quotes/carousel subclass it to add ``count`` in their own
    packages. Field descriptions ARE the LLM's parameter documentation
    (injected into the intent prompt): write them as "when to use / what
    null means", not as type restatements. Multi-version requests are
    multi-task (an English and a German post = two write_post tasks, each
    with its own language)."""

    language: str = Field(
        description="ISO code this output is WRITTEN in (e.g. 'a German "
        "post' → 'de'). Infer from the request; default to the prompt's "
        "language when the user names none."
    )
    focus: str | None = Field(
        default=None,
        description="A short angle phrase when the user assigns this output "
        "a specific angle (e.g. 'the post should cover the pricing debate' "
        "→ 'pricing debate'). null = the director picks the angle.",
    )
    tone_override: str | None = Field(
        default=None,
        description="A short tone note when the user asks for a per-output "
        "tone (e.g. '帖子正式一点' → 'formal'). null = the persona's tone.",
    )


async def _build_stacked_quote_spec(
    project: Project,
    source_video: Asset,
    chain: list[dict[str, Any]],
    needs_speaker_frame: bool,
    *,
    target_language: str,
    brand: Any,
    brand_ref: Any,
    duration_s: float = _QUOTE_CARD_CHAIN_DURATION_S,
) -> tuple[Any | None, str | None]:
    """Chain-variant materializer (RECIPES §4.6.2 chain variant, 2026-08-25).

    The writer emits a chain of N quote entries (N=3..7) plus a
    ``needs_speaker_frame`` flag. This builds the 9:16 cascade PNG:

    1. Build ``ChainCaption`` list — primary text from
       ``quote_source`` (verbatim) + secondary text from ``quote_alt``
       (alt translation, only when ``caption_mode="bilingual"``).
    2. Stream the source video from TOS.
    3. PyAV-grab frames: one per chain entry at its ``frame_at``
       midpoint + one extra speaker frame (the chain's first entry's
       frame) when ``needs_speaker_frame``.
    4. PIL composite (``composite_chain_quote_card``).
    5. Upload to PROJECT storage (``save_output`` — user products live in
       the project scope; ``demo/`` is the recipe-display bake reserve,
       D3 2026-08-27).
    6. ``build_stacked_quote_card_spec`` wraps the URL in a stills
       ClipSpec.

    Returns ``(spec, error_or_None)`` — graceful-degrade: any missing
    input returns ``(None, reason)``. The chain with all entries
    missing ``frame_at`` (no source video material) renders as a pure
    text chain (no speaker frame, all caption strips on dark canvas).
    """
    if not chain:
        return None, "stacked: empty chain"

    # Build ChainCaption list — primary from quote_source (verbatim),
    # secondary from quote_alt (when present). caption_mode="bilingual"
    # is the path where quote_alt gets populated; for source_only /
    # target_only the runner doesn't fill alt, so secondary stays None.
    captions: list[ChainCaption] = []
    frame_at_seconds: list[float] = []
    for q in chain:
        primary = (q.get("quote_source") or q.get("quote") or "").strip()
        secondary = (q.get("quote_alt") or "").strip() or None
        captions.append(ChainCaption(primary=primary, secondary=secondary))
        frame_at = q.get("frame_at")
        try:
            frame_at_seconds.append(float(frame_at) if frame_at is not None else -1.0)
        except (TypeError, ValueError):
            frame_at_seconds.append(-1.0)

    # Stream the source video from TOS via the storage seam (one
    # download — the chain entries may share or span the whole video).
    video_url = stream_url(source_video.file_url)
    if not video_url:
        # No video: render the chain as text-only (no speaker frame,
        # no chain frames — just the caption strips). The chain
        # compositor handles missing frames by skipping the speaker
        # frame entirely.
        video_bytes: bytes | None = None
    else:
        import httpx  # local — heavy import only on this path

        try:
            async with httpx.AsyncClient(timeout=300) as c:
                r = await c.get(video_url, follow_redirects=True)
                if r.status_code != 200:
                    video_bytes = None
                else:
                    video_bytes = r.content
        except Exception:  # noqa: BLE001
            video_bytes = None

    speaker_frame_img = None
    chain_frames: list[Any] = []
    if video_bytes and any(t >= 0 for t in frame_at_seconds):
        # Each chain entry's body = a VIDEO FRAME grabbed at the entry's
        # ``frame_at`` midpoint (RECIPES §4.6.2: "这几句话的帧截图下来
        # 做字幕"). The first entry's frame is ALSO the speaker face
        # when needs_speaker_frame is true — same visual, two roles.
        valid_ts = [t if t >= 0 else 0.0 for t in frame_at_seconds]
        try:
            chain_frames = extract_video_frames(video_bytes, valid_ts)
        except Exception:  # noqa: BLE001
            chain_frames = []
        if needs_speaker_frame and chain_frames:
            speaker_frame_img = chain_frames[0]

    # Composite — speaker frame optional (top half), each chain entry
    # becomes one frame card stacked with overlap (image #37 visual
    # reference: "下条被上条压住一段，露出底下一条"). When the chain
    # has more entries than frames, the back-of-stack strips fall
    # back to dark fill (graceful degrade).
    png = composite_chain_quote_card(
        speaker_frame=speaker_frame_img,
        chain=captions,
        chain_frames=chain_frames,
    )

    # Upload to project storage under a content-hashed key (D3: project
    # scope, never the demo/ display reserve).
    digest = hashlib.md5(png).hexdigest()[:8]
    try:
        key = await save_output(
            project.id, project.user_id, f"quote-chain-{digest}.png", png
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"stacked: composite upload failed ({type(exc).__name__}: {exc})"
    composite_url = output_url(key)
    if not composite_url:
        return None, "stacked: output_url returned None"

    spec = build_stacked_quote_card_spec(
        composite_image_url=composite_url,
        asset_id=source_video.id,
        duration_s=duration_s,
        target_language=target_language,
        brand=brand,
        brand_ref=brand_ref,
    )
    return spec, None


async def _materialize_quote_card_outputs(
    *,
    db: AsyncSession,
    run: WorkflowRun,
    node: WorkflowStep,
    project: Project,
    persona,
    quotes: list[dict],
    target_language: str,
    source_language: str | None,
    caption_mode: str | None,
    needs_speaker_frame: bool = False,
    core_idea: str | None = None,
) -> list[UUID]:
    """Quote-cards → sibling "clip" Outputs (RECIPES §4.6.2).

    叠卡 = 金句卡本体 (v3, 2026-08-27, ADR-048 第 7 条): the writer emits
    ONE chain of N quote entries (N=3..7, setup → payoff) — ``len >= 2``
    builds ONE composite cascade PNG (one clip Output + one render step).
    A chain of 1 builds the single quote card via ``build_quote_card_spec``
    (the same dish, N=1). The legacy per-quote fan-out is retired — the
    chain is one argument; splitting it into single cards was argument
    confetti.

    Returns the list of new Output ids. Drops silently when the source
    video is missing or the picked quote has no time-bind (graceful
    degrade — recipe registry gates these upstream, but the runner never
    fails on a single bad card).
    """
    # Phase 4 recipe wiring lands the language on run.context; chat may also
    # have stamped it. The ASR-detected source lang lives on the video's
    # asset.meta["language"] (set by the ASR processor) — fall back through
    # the chain when upstream didn't expose it.
    assets = await _list_assets(db, project.id)
    source_video: Asset | None = next(
        (
            a for a in assets
            if a.type == AssetType.VIDEO
            and a.file_url
            and (a.meta or {}).get("words")
        ),
        None,
    )
    if source_video is None:
        logger.warning(
            "quote_card_no_video_source",
            project_id=str(project.id),
            workflow_step_id=str(node.id),
        )
        return []

    # Source language: prefer the explicit arg (chat may have stamped it on
    # run.context), else the ASR-detected language on the source asset's
    # meta block, else the project's default language.
    resolved_source_lang = (
        source_language
        or (source_video.meta or {}).get("language")
        or project.language
        or "en"
    )

    brand_cfg, _ = await resolve_brand_block(db, persona)
    brand = brand_from_block(brand_cfg)
    brand_ref = persona.id if persona is not None else None
    # Quote cards share the caption catalog with talking-head clips (RENDERING
    # §3 / RECIPES §3) — preset + position come from the persona's brand
    # block, same path select_clips uses (clip_spec never overrides persona
    # choice). The persona skin can opt into "stacking" for the bilingual
    # layout or "clean-bottom" for the simple single-line look.
    cap_style_raw = brand_cfg.get("captionStylePreset")
    cap_style = cap_style_raw if isinstance(cap_style_raw, str) else "clean-bottom"
    cap_pos = brand_cfg.get("captionPosition")
    # Music mood rides the persona skin block (its default is "calm" — the
    # system default skin's value, never a per-call-site hardcode).
    music_mood = str(brand_cfg.get("musicMood") or "calm")

    created_ids: list[UUID] = []
    max_seq = int(node.seq)
    # Localized label via the runtime registry (matches select_clips / morph
    # paths — the label follows the run's pinned UI language). None when no
    # render_cls is registered or no project is attached (spec["summary"]
    # becomes optional in that case).
    label = await _render_step_label(db, run)

    if not quotes:
        return []

    # ----- 叠卡本体 (chain length >= 2, RECIPES §4.6.2 v3) ------------
    # The whole chain is ONE card: ONE composite PNG, ONE clip Output,
    # ONE render step.
    if len(quotes) >= 2:
        spec, err = await _build_stacked_quote_spec(
            project,
            source_video,
            chain=quotes,
            needs_speaker_frame=needs_speaker_frame,
            target_language=target_language,
            brand=brand,
            brand_ref=brand_ref,
        )
        if spec is None:
            logger.warning(
                "quote_card_chain_drop",
                project_id=str(project.id),
                workflow_step_id=str(node.id),
                reason=err,
            )
            await db.flush()
            return []
        # Build the canonical hook/attribution for the chain — the first
        # entry is the anchor (the writer picked it as setup → payoff; we
        # keep the first sentence as the canonical line for the canvas
        # card heading).
        anchor = quotes[0]
        spec_dict = spec.model_dump(mode="json")
        clip_output = Output(
            project_id=project.id,
            workflow_step_id=node.id,
            type="clip",
            language=target_language,
            provenance="real",
            payload=ClipPayload(
                hook=str(anchor.get("quote", "")),
                title_options=(
                    [str(anchor.get("attribution", ""))]
                    if anchor.get("attribution")
                    else []
                ),
                music_mood=music_mood,
                duration=int(_QUOTE_CARD_CHAIN_DURATION_S),
            ).model_dump(mode="json"),
            source_ref={
                "quote_card": True,
                "quote_chain": True,
                "chain_length": len(quotes),
                "needs_speaker_frame": needs_speaker_frame,
                "core_idea": core_idea,
                "asset_id": str(source_video.id),
                "quotable_line_ids": [
                    q.get("quotable_line_id") for q in quotes
                ],
            },
            render_spec=spec_dict,
            render_status=RenderStatus.PENDING,
        )
        db.add(clip_output)
        await db.flush()
        created_ids.append(clip_output.id)

        db.add(
            WorkflowStep(
                run_id=run.id,
                kind="render",
                status="pending",
                seq=max_seq + 1,
                inputs=[str(node.id)],
                spec={
                    "output_id": str(clip_output.id),
                    **({"summary": label} if label else {}),
                },
            )
        )
        await db.flush()
        return created_ids

    # ----- N=1: the same dish as a single card -------------------------
    quote = quotes[0]
    spec = build_quote_card_spec(
        source_video,
        quote,
        target_language=target_language,
        source_language=str(resolved_source_lang),
        caption_mode=caption_mode,
        brand=brand,
        brand_ref=brand_ref,
        aspect="9:16",
        caption_style_preset=cap_style,
        caption_position=cap_pos,
    )
    if spec is None:
        # Quote lacks a time-bind (image-source fallback path) — the quotes
        # output row still carries the writer's text; the canvas shows the
        # text without a video card sibling.
        return []
    spec_dict = spec.model_dump(mode="json")
    clip_output = Output(
        project_id=project.id,
        workflow_step_id=node.id,
        type="clip",
        language=target_language,
        # Real — the kept video span IS the user's real footage. The
        # caption text overlay is text, not synthesized visual; matches
        # select_clips's provenance="real" semantics (slice-of-real).
        provenance="real",
        payload=ClipPayload(
            hook=str(quote.get("quote", "")),
            title_options=[str(quote.get("attribution", ""))] if quote.get("attribution") else [],
            music_mood=music_mood,
            duration=int(quote.get("source_end", 0) - quote.get("source_start", 0)) or 0,
        ).model_dump(mode="json"),
        source_ref={
            "quote_card": True,
            "quote_index": 1,
            "asset_id": str(source_video.id),
            "start_seconds": quote.get("source_start"),
            "end_seconds": quote.get("source_end"),
            "quotable_line_id": quote.get("quotable_line_id"),
        },
        render_spec=spec_dict,
        render_status=RenderStatus.PENDING,
    )
    db.add(clip_output)
    await db.flush()
    created_ids.append(clip_output.id)

    # Render fan-out: the render worker picks the output row by
    # render_status=PENDING; the WorkflowStep is the UI progress mirror
    # (mirrors select_clips's contract verbatim).
    db.add(
        WorkflowStep(
            run_id=run.id,
            kind="render",
            status="pending",
            seq=max_seq + 1,
            inputs=[str(node.id)],
            spec={
                "output_id": str(clip_output.id),
                **({"summary": label} if label else {}),
            },
        )
    )
    await db.flush()
    return created_ids


class DerivativeWriterNode(NodeBase):
    """Shared body for the four copy-writer nodes; each package declares a
    thin subclass with its own ``writer`` (the tool-private agent)."""

    writer: Agent
    needs_director = True
    # 2026-08-24 lift: copy-writers (write_post / write_quotes /
    # write_carousel / write_article) draft from the user prompt + persona
    # style alone when no source material is attached — the prior
    # ``(TRANSCRIPT,)`` gate hard-422ed "I have no material, write me a
    # post" requests, which was hostile to the common "just topic X" case.
    # The gate moves to the prompt layer: PlanAgent recognizes the
    # no-material case and tells the user (in echo prose + soft reason)
    # that the draft comes from prompt + persona; if material shows up
    # later, the next turn re-docks a richer book. needs_director stays
    # True so the director's persona/style hand-off survives the empty
    # material_excerpt path.
    requires = ()
    produces_outputs = True
    # Per-writer quotation declarations (P4): completion bounds grounded in
    # the output schema's size class; ``images_per_run`` = exact image
    # generations (the quote card's 1, skipped on targeted regeneration).
    completion_bounds: tuple[int, int] = (400, 1500)
    images_per_run: int = 0

    @property
    def derivative_type(self) -> DerivativeType:
        """The DerivativeType IS the output type (N-32 single source)."""
        return DerivativeType(self.output_type)

    def estimate(self, ctx: dict) -> dict | None:
        """One writer call: prompt = trimmed asset texts + understanding /
        storyboard / persona context overhead; completion per the writer's
        size class."""
        chars = min(ctx["text_chars"], MAX_CHARS_PER_TEXT * ctx["text_count"])
        prompt = token_bounds(chars)
        prompt[0] += 800
        prompt[1] += 3000
        units: dict[str, float] = {}
        if self.images_per_run and not (ctx["spec"] or {}).get("target_id"):
            units["images"] = float(self.images_per_run)
        return estimate_mechanical(
            units, prompt=prompt, completion=list(self.completion_bounds)
        )

    async def _generate(
        self,
        asset_texts: list[str],
        context: GenerationContext,
        understanding: MaterialUnderstanding,
        storyboard: Storyboard,
        feedback: str | None = None,
    ) -> dict:
        """Generate a single derivative via the package's writer declaration.

        Returns the agent's generated content as a plain dict. Callers are
        responsible for persisting it. ``feedback`` (期 3 质检打回) rides the
        funnel's repair echo — the writer sees the failed checks verbatim.
        """
        result = await self.writer.call(
            asset_texts=asset_texts,
            context=context,
            understanding=understanding,
            storyboard=storyboard,
            repair_feedback=feedback,
        )
        return validate_derivative_content(self.derivative_type, result.model_dump())

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        """Generate one derivative output (post/quotes/carousel/article).

        With ``spec.target_id`` set this is a targeted regeneration: the existing
        row is updated in place (its storyboard now comes from a real upstream
        director_plan node — the fabricated-plan path is gone).
        """
        derivative_type = self.derivative_type
        ctx = run.context or {}
        # 质检打回 (期 3): a bounced round's feedback rides the spec exactly
        # once — pop it (reassign = SQLAlchemy-tracked) so a later targeted
        # regen never eats stale feedback.
        spec = dict(node.spec or {})
        feedback = spec.pop("feedback", None)
        if feedback is not None:
            node.spec = spec
        slot = _node_slot(node, ctx, derivative_type.value)
        target_id = node.spec.get("target_id")
        # Language resolves per slot first, then the node's targeted language,
        # then the task-book language.
        target_language = (
            (slot.language if slot else None)
            or node.spec.get("target_language")
            or ctx.get("target_language", "en")
        )

        await _set_stage(node.id, "writing_copy")

        asset_texts = await collect_asset_texts(db, project.id)
        persona = await resolve_persona(db, project)
        generation_context = _generation_context(run, project, persona)
        generation_context.target_language = target_language
        # 2026-08-25 Phase 2: caption_mode rides run.context verbatim —
        # write_quotes (Phase 2 / RECIPES §4.6.2) reads it to know whether
        # to call the translator for quote_alt. None for chains that don't
        # produce captions (write_post / write_carousel / write_article).
        generation_context.caption_mode = ctx.get("caption_mode")
        understanding, storyboard = await _load_director_outputs(db, node)

        # Narrow the storyboard to THIS slot: same-type sibling slots (e.g. an
        # English and a German post) are addressed by the slot's ordinal, which
        # compile_graph and director_plan both derive from the canonical order.
        same_type = [s for s in storyboard.slots if s.slot == derivative_type.value]
        if same_type:
            slot_index = int((node.spec or {}).get("slot_index") or 0)
            my_slot = same_type[min(slot_index, len(same_type) - 1)]
            storyboard = storyboard.model_copy(update={"slots": [my_slot]})

        content = await self._generate(
            asset_texts=asset_texts,
            context=generation_context,
            understanding=understanding,
            storyboard=storyboard,
            feedback=feedback,
        )

        if target_id:
            output = await db.get(Output, UUID(str(target_id)))
            if output is None or output.project_id != project.id:
                raise ValueError("Target output not found")
            output.payload = validate_output_payload(output.type, content)
            output.language = target_language
            output.status = "generated"
            output.updated_at = datetime.now(UTC)
            output.workflow_step_id = node.id
            await db.flush()
            await _fill_summary(
                node.id, self.kind, tag=slot_tag(slot),
                ui_language=ui_lang_of(run, project), word_count=_count_words(content),
            )
            return [output.id]

        # Idempotency, sibling-safe (per-slot fan-out): same-type outputs produced
        # by THIS run's same-kind nodes are their own slots' products — only prior
        # products (other runs' steps, or step-less rows) are cleared. Two sibling
        # write_post nodes can therefore never delete each other's output.
        sibling_step_ids = (
            select(WorkflowStep.id)
            .where(WorkflowStep.run_id == run.id, WorkflowStep.kind == node.kind)
            .scalar_subquery()
        )
        await db.execute(
            delete(Output).where(
                Output.project_id == project.id,
                Output.type == derivative_type.value,
                or_(
                    Output.workflow_step_id.is_(None),
                    Output.workflow_step_id.notin_(sibling_step_ids),
                ),
            )
        )

        output = Output(
            project_id=project.id,
            workflow_step_id=node.id,
            type=derivative_type.value,
            language=target_language,
            provenance="generated",
            payload=validate_output_payload(derivative_type.value, content),
        )
        db.add(output)
        await db.flush()

        # Quote cards: build a 9:16 clip-spec per quote and persist it as a
        # sibling "clip" Output so the render worker (PENDING claim) picks it
        # up. 叠卡 = 卡本体 (v3): the chain materializes as ONE composite
        # cascade PNG; a chain of 1 builds the single video card
        # (RECIPES §4.6.2).
        if derivative_type == DerivativeType.QUOTES:
            quotes = content.get("quotes", []) if isinstance(content, dict) else []
            if quotes:
                await _set_stage(node.id, "building_specs")
                # The writer's verdict on whether the cascade needs a speaker
                # frame on top, plus the core-idea thesis sentence that drove
                # the chain selection. Both ride on the writer content —
                # never re-derive.
                needs_speaker_frame = bool(
                    (content.get("needs_speaker_frame") if isinstance(content, dict) else False)
                )
                await _materialize_quote_card_outputs(
                    db=db,
                    run=run,
                    node=node,
                    project=project,
                    persona=persona,
                    quotes=quotes,
                    target_language=target_language,
                    source_language=(ctx.get("source_language") or None),
                    caption_mode=ctx.get("caption_mode"),
                    needs_speaker_frame=needs_speaker_frame,
                    core_idea=(
                        content.get("core_idea") if isinstance(content, dict) else None
                    ),
                )

        await _fill_summary(
            node.id, self.kind, tag=slot_tag(slot),
            ui_language=ui_lang_of(run, project), word_count=_count_words(content),
        )
        return [output.id]
