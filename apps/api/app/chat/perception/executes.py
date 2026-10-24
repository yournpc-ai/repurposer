"""The perception family's read implementations (ADR-077 判词②, T2b).

只读纪律: this module holds ZERO write functions — every execute below only
reads (a SELECT, or the web pair's read-only fetch) and renders compact
model-facing text (the observation). The world's
READINGS live here; the world's WRITINGS stay behind the three doors
(edit ops / wiring ops / ``create_run``) — a read tool is never a doorbell
for a write (简报 §3).

Every execute is tenant-scoped to the turn's project (the same ownership
check as the edit verbs' doors — a client-pinned id resolves only inside its
own project) and answers a MISS honestly (an empty observation the model
adapts to), never raises on content. Infrastructure failures (the DB
itself) propagate — the turn's honest terminal failure, never a fabricated
read (静默降级禁令).

Output budget: observations are model context, not user copy — each is
capped (see the per-tool caps) so a read never floods the loop.
"""

from typing import Any, get_args
from uuid import UUID

import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict, Field

from app.models.schemas import (
    AssetStatus,
    AssetType,
    ClipSpec,
    CraftSkeleton,
    MaterialUnderstanding,
    MediaInput,
    PendingPlan,
)
from app.models.tables import (
    Asset,
    ExplorationRow,
    GraphEdge,
    GraphNode,
    Output,
    Project,
    WorkflowRun,
    WorkflowStep,
)
from app.tools.clips.transcript import (
    build_anchored_transcript,
    group_cues,
    search_cues,
    speaker_at,
    words_in_range,
)
from app.tools.research.web import FETCH_TEXT_CAP, fetch_text, web_search
from app.tools.world import page_reading_for_url, write_page_reading
from app.pipeline.assets import asset_text_content
from app.pipeline.exploration_store import (
    KIND_CANDIDATE_SET,
    KIND_CONTENT_PLAN,
    KIND_SELECT,
    output_fact,
)


# ---- params models (package-local, like tools/<pkg>/params.py) --------------
#
# Default pydantic config on purpose (no extra="forbid"): the loop boundary
# already pops the retired habit keys (type/kind/prose), and ignoring unknown
# extras here is the read-tolerant posture — a read call never dies on an
# extra key. Field descriptions ARE the model's parameter documentation
# (they compile into the tool's JSON schema).


class ViewSelector(BaseModel):
    """One captured page view a film read attaches the screenshot of."""

    model_config = ConfigDict(extra="forbid")

    page: int = Field(
        description="0-based page index (the read's candidate view catalog)."
    )
    shot: int = Field(
        description="0-based shot index within the page (0 = the fold)."
    )


class GetOutputSpecParams(BaseModel):
    output_id: UUID | None = Field(
        default=None,
        description=(
            "The output's id (from the context's Current outputs list or an "
            "@-mention). Omit to read the film's CURRENT storyboard version "
            "(the live draft when one stands, else the latest delivered "
            "film) — the re-read seat before continuing a targeted edit in "
            "a later turn."
        ),
    )
    views: list[ViewSelector] | None = Field(
        default=None,
        description=(
            "Film reads only: name specific captured views (page/shot pairs "
            "from the read's candidate view catalog) to attach their "
            "screenshots AND camera-target inventories (the legal element "
            "ids an update_scene focus may name — never guess one) — at "
            "most 12 per read; naming exactly ONE view reads it back in "
            "high resolution. Omit to attach every candidate view; an "
            "over-budget read answers with an explicit error (never a "
            "silently partial set, never an implied-complete element list)."
        ),
    )


class GetNodeParams(BaseModel):
    node_id: UUID = Field(
        description="The graph node's id (from the context's Graph section)."
    )


class GetAssetParams(BaseModel):
    asset_id: UUID | None = Field(
        default=None,
        description=(
            "The asset's id (from an @-mention or a previous get_asset "
            "roster reply); null = the project's only file asset — with "
            "several, the call returns the roster with their ids."
        ),
    )


class ListProjectMediaParams(BaseModel):
    ids: list[str] | None = Field(
        default=None,
        description=(
            "Read only these assets by id (the user's explicit picks — "
            "from @-mentions or an earlier listing; an id past the printed "
            "listing's cap is still readable here); null = the paged "
            "listing, newest first."
        ),
    )
    offset: int = Field(
        default=0,
        description=(
            "Skip this many assets (newest first) — page to older rows "
            "when the listing says more exist (e.g. offset=40 for the "
            "second page of 40)."
        ),
        ge=0,
    )


class SearchMusicParams(BaseModel):
    query: str | None = Field(
        default=None,
        description="A mood or keyword to match against track mood/title (e.g. 'calm', 'upbeat'); null/empty = the full catalog.",
    )


class GetCraftSkeletonParams(BaseModel):
    asset_id: UUID | None = Field(
        default=None,
        description="The reference video's asset id (from the context's Assets list or an @-mention); null = the conversation's pinned reference (the role question's / mention's exemplar).",
    )


class GetArtifactParams(BaseModel):
    artifact_id: UUID = Field(
        description="The exploration artifact's id (a candidate collection / a pick / a plan card — from the Graph section's exploration rows or a discovery-chain observation)."
    )


class GetWebPageParams(BaseModel):
    url: str = Field(
        description="The page's full URL, verbatim from the conversation "
        "(this turn or an earlier one). "
        "The readable text comes back capped; an empty read means the page "
        "could not be read (unreachable / refused / no readable text)."
    )
    refresh: bool = Field(
        default=False,
        description="False = answer from the project's stored reading when "
        "one exists (the same page is never re-fetched). True ONLY when the "
        "user says the page has changed — it fetches fresh and replaces the "
        "stored reading.",
    )


class SearchWebParams(BaseModel):
    query: str = Field(
        description="The web search question — specific and self-contained "
        "(names the topic, never 'the above')."
    )


# ---- shared rendering helpers ------------------------------------------------

_RUN_STEP_PROGRESS_LIMIT = 12


def _format_step_progress(steps: list[WorkflowStep]) -> list[str]:
    """One quantified line per step of a run (G-2): ``kind: status —
    summary``. Moved from ``agents/contexts.py`` (T2b digest slimming): the
    per-step detail is no longer pre-injected into the fixed context — this
    is ``get_run_status``'s rendering, called on demand. Capped — when a run
    outgrows the budget the tail (current + upcoming work) is what a progress
    question is about."""
    rows = []
    for step in steps:
        row = f"- {step.kind}: {step.status}"
        summary = (step.spec or {}).get("summary")
        if summary:
            row += f" — {summary}"
        rows.append(row)
    if len(rows) > _RUN_STEP_PROGRESS_LIMIT:
        omitted = len(rows) - _RUN_STEP_PROGRESS_LIMIT
        rows = [f"- … ({omitted} earlier steps omitted)"] + rows[
            -_RUN_STEP_PROGRESS_LIMIT:
        ]
    return rows


def _stamp(dt) -> str:
    """Compact UTC timestamp for observation headers."""
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt is not None else "?"


# ---- the reads -----------------------------------------------------------------


def _fmt_ts(seconds: float) -> str:
    """M:SS digest anchor (hours flatten into minutes — digest lines stay
    short)."""
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def understanding_digest_lines(u: MaterialUnderstanding) -> list[str]:
    """The understanding row's compact digest (ONE formatting law, two
    consumers — 两镜像互引): the perception read ``get_understanding``
    renders it under its own header, and the plan turn's assemble
    (ADR-083 信任锚注入) renders it into the router's context block.
    Caps keep the digest prompt-sized; an empty stub shape returns [].
    节拍锚 (2026-09-27 批「信号源」): the counts-only beat line is retired —
    a review can only ground "which span" when it can SEE where segments
    live (reply-quality baseline D1: zero time anchors without this).
    Resolved spans render M:SS-M:SS + label; unresolved keep the bare label
    (never invent a time); label-less beats drop."""
    lines: list[str] = []
    if u.overall_summary:
        lines.append(f"- Summary: {u.overall_summary[:300]}")
    if u.core_thesis:
        lines.append(f"- Core thesis: {u.core_thesis[:200]}")
    if u.themes:
        lines.append(f"- Themes: {', '.join(u.themes[:8])}")
    if u.target_audience:
        lines.append(f"- Audience: {u.target_audience[:120]}")
    if u.quotable_lines:
        quotes = "; ".join(f"“{q.text[:100]}”" for q in u.quotable_lines[:3])
        lines.append(
            f"- Quotable lines: {len(u.quotable_lines)} — e.g. {quotes}"
        )
    if u.topic_boundaries:
        # Label-less beats drop BEFORE the cap, so "(+N more)" counts only
        # what the reader could have seen (test-locked semantics).
        labeled = [b for b in u.topic_boundaries if (b.label or "").strip()]
        beats: list[str] = []
        for b in labeled[:8]:
            label = (b.label or "").strip()[:40]
            if b.start is not None and b.end is not None:
                beats.append(f"{_fmt_ts(b.start)}-{_fmt_ts(b.end)} {label}")
            else:
                beats.append(label)
        if beats:
            more = len(labeled) - 8
            lines.append(
                "- Beats: "
                + "; ".join(beats)
                + (f" (+{more} more)" if more > 0 else "")
            )
    if u.climax_spans:
        climaxes: list[str] = []
        for c in u.climax_spans[:3]:
            text = (c.text or "").strip()[:60]
            if not text:
                continue
            anchor = (
                f"{_fmt_ts(c.start)}-{_fmt_ts(c.end)} "
                if c.start is not None and c.end is not None
                else ""
            )
            climaxes.append(f"{anchor}“{text}”")
        if climaxes:
            lines.append("- Climaxes: " + "; ".join(climaxes))
    return lines


def speaker_form_lines(assets: list[Asset]) -> list[str]:
    """The footage's speaker form as deterministic fact lines (one per
    form-bearing VIDEO asset): the speaker_map's form + turn count, read
    straight off ``asset.meta`` (zero LLM). Two consumers, one formatting
    law — the ``get_understanding`` read and the plan turn's assemble — so
    the speaker-framing direction (the camera on whoever talks) is SAYABLE
    on every surface that reads the material. Only the attributed forms
    render (interview / single — the forms the reframe capability keys its
    modes on); an absent map or an unattributed form (multi / unknown) is
    NO line, never a guess. The gate's reusable scan (``meta.face_scan``)
    adds one footage-facts line when it holds editing-relevant spans —
    extra-people stretches (cutaway candidates) and face-free stretches
    (B-roll candidates) — on ANY form, the scan's honesty independent of
    the form verdict."""
    out: list[str] = []
    for a in assets:
        speaker_map = (a.meta or {}).get("speaker_map") or {}
        form = speaker_map.get("form")
        turns = len(speaker_map.get("turns") or [])
        name = a.display_name or a.title or "(video)"
        if form == "interview":
            out.append(
                f"- Speaker form: {name} is a two-speaker interview — "
                f"{turns} attributed turns (who speaks when is known)"
            )
        elif form == "single":
            out.append(
                f"- Speaker form: {name} is a single-speaker recording — "
                f"{turns} turns, all attributed to the one speaker"
            )
        scan = (a.meta or {}).get("face_scan") or {}
        extra = len(scan.get("extra_people_spans") or [])
        free = len(scan.get("face_free_spans") or [])
        if extra or free:
            parts: list[str] = []
            if extra:
                parts.append(
                    f"{extra} stretch(es) with extra people in frame "
                    "(audience/reaction shots — cutaway candidates)"
                )
            if free:
                parts.append(f"{free} face-free stretch(es) (B-roll candidates)")
            out.append(f"- Footage scan: {name} has " + " and ".join(parts))
    return out


_READINESS_POLL_SECONDS = 2.5


_STALE_UNDERSTANDING_TEXT = (
    "A material understanding exists but its stored shape is stale — "
    "it will be regenerated on the next run."
)


def _render_understanding(row: Output, assets: list[Asset]) -> str | None:
    """The understanding row's model-facing digest (one rendering, two read
    seats — the immediate hit and the wait's landed poll). None = the stored
    shape is stale — the content did NOT land."""
    try:
        u = MaterialUnderstanding.model_validate(row.payload)
    except Exception:  # noqa: BLE001 — a stale-shaped row reads honestly
        return None
    lines = ["Material understanding (the current asset set):"]
    lines.extend(understanding_digest_lines(u))
    lines.extend(speaker_form_lines(assets))
    lines.extend(_anchored_transcript_lines(assets))
    if len(lines) == 1:
        # The stub shape (a no-material chain's placeholder row) — say so.
        lines.append("- (empty stub — the chain ran without material)")
    return "\n".join(lines)


# Per-asset inline budget for the anchored transcript (ADR-107): below it
# the understanding read carries the asset's whole [start-end] transcript —
# the discovery chain's ranges come straight from these anchors, no search
# round-trip. Above it the honest pointer keeps the long-asset path on
# search_transcript / get_segment.
_TRANSCRIPT_INLINE_LIMIT = 8000


def _anchored_transcript_lines(assets: list[Asset]) -> list[str]:
    """The discovery chain's substrate (ADR-107): each timeline-ready
    asset's anchored transcript, inline when it fits the prompt budget.
    The asset_id rides every header — propose_candidates requires it
    downstream, and a roster-less id forced the model to invent one
    (the search_transcript header's live-gate lesson, same seat)."""
    out: list[str] = []
    for a in assets:
        words = (a.meta or {}).get("words") or []
        if not words:
            continue
        anchored = build_anchored_transcript(words)
        if not anchored.strip():
            continue
        header = f"Transcript of {_asset_label(a)} (asset_id: {a.id})"
        if len(anchored) <= _TRANSCRIPT_INLINE_LIMIT:
            out.append(f"{header}:")
            out.append(anchored)
        else:
            out.append(
                f"{header} is too long to show ({len(anchored)} chars) — "
                "find passages with search_transcript and read their ranges "
                "with get_segment."
            )
    return out


def _failed_text(failed_count: int) -> str:
    """The failure observation: WORLD FACTS ONLY (一法一座 — the failure's
    speech law lives in the system prompt's material-readiness line; the
    observation carries facts, never a phrasable draft)."""
    return (
        f"{failed_count} asset(s) FAILED processing — their content is "
        "unreadable."
    )


_WARM_DEAD_TEXT = (
    "The material finished processing but its understanding could not be "
    "built — the content is unreadable."
)


async def _stamp_processing_requested(project_id) -> None:
    """The chat path's ONLY request seat (ADR-102 §3): the read attempt
    itself wakes the dormant assets. Own session + commit (H7) — the turn's
    session may hold uncommitted writes, and the worker's claim loop must
    see the stamp NOW."""
    from app.models.database import AsyncSessionLocal  # deferred: worker seat
    from sqlalchemy import update

    from app.models.tables import now_utc

    async with AsyncSessionLocal() as s:
        await s.execute(
            update(Asset)
            .where(
                Asset.project_id == project_id,
                Asset.processing_status == AssetStatus.PENDING,
                Asset.processing_requested_at.is_(None),
            )
            .values(processing_requested_at=now_utc())
        )
        await s.commit()


async def understanding_observation(db: AsyncSession, project: Project) -> tuple[str, bool]:
    """The read's full result: (observation text, landed flag).

    ADR-102 §3 — the read is the turn's PRECONDITION, and this tool call is
    the worker event's ONLY chat-side creation point: a pending asset set +
    a provider deaf to video audio (``capabilities.understands_video_audio
    == False``) gets stamped HERE — never at upload, never at send. The
    wait runs to the TERMINAL state with no time cap: the understanding row
    lands (content), or the set ends unreadable (assets failed / the warm
    ran and built nothing). The observation the model ever sees is one of
    two shapes — content, or failure facts; a pending world never reaches
    the model.

    landed=False marks the read's activity frame failed (「素材没能读出来」)
    — the honest counterweight to the settled frame, never a silent lie."""
    import asyncio

    from app.models.database import AsyncSessionLocal  # deferred: worker seat
    from app.pipeline.node_runners import (  # deferred: pipeline weight
        find_reusable_understanding,
        kick_warm_inline,
    )
    from app.pipeline.step_context import asset_digest, list_assets
    from app.providers.llm.minimax import minimax_client

    assets = await list_assets(db, project.id)
    if not assets:
        return (
            "No assets in this project yet — there is no material to read. "
            "If the user means to work from material, they need to upload or "
            "paste it first.",
            False,
        )
    row = await find_reusable_understanding(db, project, asset_digest(assets))
    if row is not None:
        rendered = _render_understanding(row, assets)
        return (
            rendered if rendered is not None else _STALE_UNDERSTANDING_TEXT,
            rendered is not None,
        )

    stamped = False
    warm_kicked = False
    while True:
        if not stamped:
            pending = [
                a
                for a in assets
                if a.processing_status
                in (AssetStatus.PENDING, AssetStatus.PROCESSING)
            ]
            if pending and not minimax_client.capabilities.understands_video_audio:
                await _stamp_processing_requested(project.id)
            stamped = True
        await asyncio.sleep(_READINESS_POLL_SECONDS)
        async with AsyncSessionLocal() as poll:
            assets = await list_assets(poll, project.id)
            row = await find_reusable_understanding(poll, project, asset_digest(assets))
            if row is not None:
                # Render inside the poll session — the ORM rows stay attached.
                rendered = _render_understanding(row, assets)
                return (
                    rendered if rendered is not None else _STALE_UNDERSTANDING_TEXT,
                    rendered is not None,
                )
            pending = [
                a
                for a in assets
                if a.processing_status
                in (AssetStatus.PENDING, AssetStatus.PROCESSING)
            ]
            if pending:
                continue
            failed = [
                a for a in assets if a.processing_status == AssetStatus.FAILED
            ]
            if failed:
                return _failed_text(len(failed)), False
            # All completed but no row: the warm is in flight or died (it is
            # best-effort). Kick it inline — the pile-up guard collapses
            # concurrent kicks; a completed kick with no row = definitively
            # dead for this digest.
            if warm_kicked:
                return _WARM_DEAD_TEXT, False
            if not await kick_warm_inline(project.id):
                continue  # another warm is in flight — keep polling
            warm_kicked = True


async def get_understanding(db: AsyncSession, project: Project, params) -> str:
    """The project's material understanding — what the material SAYS (the
    warm/run materialized row, content-addressed by the current asset set).
    Journeys: 「我看了——你在讲 X」的读法 + 推荐配乐/样式前的氛围匹配.

    Registry-compatible wrapper (text only); the turn dispatch seat reads
    :func:`understanding_observation` for the landed flag."""
    text, _ = await understanding_observation(db, project)
    return text


async def get_output_spec(db: AsyncSession, project: Project, params: GetOutputSpecParams) -> str:
    """One output's current state — the read-before-write seat for relative
    revisions (「字幕调小一点」「声音小一点不」: compose the op from the CURRENT
    settings, never invent them).

    Registry-compatible wrapper (text only); the turn dispatch seat reads
    :func:`output_spec_observation` for the attached view images."""
    text, _ = await output_spec_observation(db, project, params, with_images=False)
    return text


async def output_spec_observation(
    db: AsyncSession,
    project: Project,
    params: GetOutputSpecParams,
    *,
    with_images: bool = True,
) -> tuple[str, list["MediaInput"]]:
    """The read's full result: (observation text, attached view images).

    A film read reads back its storyboard VERSION facts (the edit model's
    eyes, film 读取座) — either one output's version (``output_id`` named)
    or the CURRENT version (``output_id`` omitted: the live draft when one
    stands, else the latest delivered film — 待产稿可重读, so a later edit
    turn never forms against a stale delivered read). The facts: the
    version/digest identity, the per-scene facts (view reference + camera
    text + narration), the timeline's PROVENANCE (executed spec / frozen
    kept cut / planned draft / unreadable — planned values are never
    labeled executed), the version's material-identity check against the
    current pages (drift named, never passed off), and — while the edit
    capability gate is on — the read-time ``base_ref``, the candidate view
    catalog and the views' screenshots. The images are the MATERIAL's
    captured page views, never frames of the rendered film."""
    from app.agents.contexts import output_one_liner  # deferred: assembly layer

    if params.output_id is None:
        # 当前版本读取座 (the edit model's re-read of the WORK IN PROGRESS —
        # 待产稿可重读): no output id = the film's CURRENT storyboard
        # version — the live pending draft when one stands, else the latest
        # delivered film's version (the revision-base seat's own priority
        # law). The same fact table, the same base_ref mint, the same view
        # catalog and images as an output read — a patch formed against a
        # stale delivered read while a newer draft stands is how
        # consecutive edit turns deadlock, so the draft itself is readable.
        # Film-only: clip/post reads still name their output.
        from app.tools.film.storyboard import (  # deferred: tool seam
            resolve_film_revision_base,
        )

        base = await resolve_film_revision_base(db, project)
        if base is None or not getattr(base, "film_storyboard", None):
            return (
                "No film storyboard version exists in this project yet — "
                "design one first (design_storyboard). To read a clip or "
                "post output, name its id from the context's Current "
                "outputs list or an @-mention.",
                [],
            )
        lines = [
            "Current film storyboard version (no output id named — the "
            "live draft when one stands, else the latest delivered film's "
            "version):"
        ]
        film_lines, images = await _film_observation(
            db,
            project,
            base=base,
            head_lines=lines,
            params=params,
            with_images=with_images,
        )
        return "\n".join(film_lines), images

    output = await db.get(Output, params.output_id)
    if output is None or str(output.project_id) != str(project.id):
        return (
            f"No output with id {params.output_id} exists in this project — "
            "pick an id from the context's Current outputs list or an "
            "@-mention.",
            [],
        )
    lines = [
        f"Output {output.id} — type={output.type}, language={output.language}, "
        f"status={output.status}"
    ]
    one_liner = output_one_liner(output)
    if one_liner:
        lines.append(f"- First line: {one_liner}")
    if output.type == "film":
        from app.tools.film.storyboard import (  # deferred: tool seam
            resolve_film_revision_base,
        )

        base = await resolve_film_revision_base(db, project, output_id=output.id)
        if base is None:
            lines.append(
                "- This film's storyboard version is unrecoverable (no "
                "parseable provenance) — a redesign through "
                "design_storyboard (no edits) is the honest path."
            )
            return "\n".join(lines), []
        film_lines, images = await _film_observation(
            db,
            project,
            base=base,
            head_lines=lines,
            params=params,
            with_images=with_images,
        )
        return "\n".join(film_lines), images
    spec = output.render_spec or {}
    if spec:
        # Clip outputs: the clip-spec's CURRENT settings, raw-dict read
        # (read-tolerant across spec versions — a missing key just skips its
        # line). The renderer's behavior contract stays in the spec; this is
        # the agent's window onto it.
        caption_on = spec.get("caption_enabled", True)
        preset = spec.get("caption_style_preset")
        if preset:
            lines.append(
                f"- Captions: {'on' if caption_on else 'off'}, style preset "
                f"\"{preset}\""
            )
        music = spec.get("music") or {}
        if music.get("enabled"):
            lines.append(
                f"- Music bed: mood \"{music.get('mood', '?')}\", gain "
                f"{music.get('gain_db', '?')} dB"
            )
        else:
            lines.append("- Music bed: none")
        lines.append(
            f"- Aspect: {spec.get('aspect', '?')}; segments: "
            f"{len(spec.get('segments') or [])}"
        )
        dub = spec.get("dub")
        if dub and dub.get("enabled"):
            lines.append(f"- Dub: on, target language {dub.get('target_language', '?')}")
    body = (output.payload or {}).get("body")
    if isinstance(body, str) and body.strip():
        lines.append(f"- Body (excerpt): {body.strip()[:600]}")
    return "\n".join(lines), []


# The film read's image budget (总设计 §7.2 读取座): one read attaches at
# most 12 thumbnails (long edge ~640px — enough for a creative judgment,
# never a pixel-peep); a read naming exactly ONE view re-reads it in high
# resolution (1280px). Over budget is an explicit error naming the remedy —
# the image set is NEVER silently partial.
_FILM_VIEW_IMAGE_MAX = 12
_FILM_VIEW_THUMB_PX = 640
_FILM_VIEW_DETAIL_PX = 1280


def _page_view(page, shot_index: int) -> tuple[str | None, str] | None:
    """The page's shot_index-th captured view as ``(storage key, heading)``;
    None = no such view. A falsy key = the view exists but its screenshot
    was never stored (the capture's visual half degraded). A shots-less
    page (pre-B1 fold-only capture) exposes exactly its fold (shot 0 rides
    ``screenshot_key`` — the fold-only law, never an invented section)."""
    shots = getattr(page, "shots", None) or ()
    if shots:
        if not 0 <= shot_index < len(shots):
            return None
        shot = shots[shot_index]
        return (shot.key, shot.heading or "(top)")
    if shot_index == 0 and getattr(page, "screenshot_key", None):
        return (page.screenshot_key, "(top)")
    return None


def _page_view_count(page) -> int:
    """How many views the page exposes to the read (shots, or the fold-only
    degenerate)."""
    shots = getattr(page, "shots", None) or ()
    if shots:
        return len(shots)
    return 1 if getattr(page, "screenshot_key", None) else 0


async def _film_view_image(
    key: str, max_px: int, caption: str
) -> MediaInput | None:
    """One view screenshot's compressed media input (the seam tests patch —
    the storage download + resize lives in step_context's one seat)."""
    from app.pipeline.step_context import media_input_for_image  # deferred: pipeline edge

    return await media_input_for_image(key, caption=caption, max_px=max_px)


def _film_music_pick(canonical: dict) -> str:
    """The params row's music segment — the user's SELECTION, never the
    outcome: a named mood is the pick, ``off`` is the explicit close, and an
    UNSET mood is not a state at all (the resolution chain still decides —
    the Music line below carries what the version actually carries)."""
    from app.tools.film.storyboard import FILM_MUSIC_OFF  # deferred: tool seam

    mood = canonical.get("music_mood")
    if mood == FILM_MUSIC_OFF:
        return 'music "off" (explicitly closed)'
    if isinstance(mood, str):
        return f'music mood "{mood}"'
    return "music unset (not off — the Music line below reports what the version actually carries)"


def _film_music_fact_line(
    canonical: dict,
    *,
    cut_state_hint: str | None,
    spec_music: Any,
    execution: Any,
) -> str:
    """The film bed's FACT line (the pick is the params row's job — this is
    what the version's own records carry). Sources by the version's state:

    - an EXECUTED version (cut_state "spec"): the DELIVERED render spec's
      music block — the landed truth (a spec without the block proves no
      bed landed; ``build_film_spec`` writes the key whenever a bed went
      in). The design-time snapshot's mood joins only when its track IS
      the delivered one (same track id — never a mismatched mashup);
    - a draft/frozen version: the design-time execution snapshot's
      resolved bed (the plan, frozen with the version);
    - an unreadable executed record or a snapshot-less legacy version:
      UNCONFIRMABLE — missing records never default to "off".
    """
    from app.tools.film.storyboard import FILM_MUSIC_OFF  # deferred: tool seam

    mood = canonical.get("music_mood")
    snap_music = execution.get("music") if isinstance(execution, dict) else None
    snap_mood = snap_music.get("mood") if isinstance(snap_music, dict) else None
    snap_track = snap_music.get("track_id") if isinstance(snap_music, dict) else None

    if cut_state_hint == "spec":
        if isinstance(spec_music, dict):
            parts: list[str] = []
            # The mood is a design-time record — report it only when the
            # snapshot's track IS the delivered one (the spec's url carries
            # the track id; a mismatch would mash up two records).
            spec_url = spec_music.get("url")
            if (
                isinstance(snap_mood, str)
                and isinstance(snap_track, str)
                and isinstance(spec_url, str)
                and snap_track in spec_url
            ):
                parts.append(f'mood "{snap_mood}"')
            bpm = spec_music.get("bpm")
            if isinstance(bpm, (int, float)):
                parts.append(f"{bpm:g} BPM")
            gain = spec_music.get("gain_db")
            if isinstance(gain, (int, float)):
                parts.append(f"gain {gain:g} dB")
            detail = " · ".join(parts) if parts else "details unrecorded"
            return (
                f"- Music: a bed LANDED in the delivered render ({detail} — "
                "the executed record's own entry)"
            )
        if mood == FILM_MUSIC_OFF:
            return (
                "- Music: off — the user switched the bed OFF, and the "
                "delivered render carries none (as confirmed)"
            )
        return (
            "- Music: no bed in the delivered render (the executed record "
            "carries none)"
        )
    if cut_state_hint == "unreadable":
        return (
            "- Music: unconfirmable — the version was executed but its "
            "delivered record is unreadable (never read that as no music)"
        )
    # draft / kept / legacy-no-state: the version's frozen PLAN.
    if isinstance(snap_music, dict) and snap_track:
        parts = []
        if isinstance(snap_mood, str):
            parts.append(f'mood "{snap_mood}"')
        bpm = snap_music.get("bpm")
        if isinstance(bpm, (int, float)):
            parts.append(f"{bpm:g} BPM")
        detail = " · ".join(parts) if parts else "track resolved"
        return (
            f"- Music: bed planned ({detail}) — frozen into this version's "
            "execution record at design time; the run renders this grid"
        )
    if mood == FILM_MUSIC_OFF:
        return "- Music: off — the user switched the bed OFF (no bed planned)"
    if isinstance(mood, str):
        return (
            f'- Music: unconfirmable — the picked mood "{mood}" has no '
            "resolved track in this version's frozen record"
        )
    if isinstance(execution, dict):
        return (
            "- Music: no bed in this version's frozen execution record "
            "(none resolved at design time)"
        )
    return (
        "- Music: unconfirmable — this version predates the frozen "
        "execution record (never read that as off)"
    )


async def _film_observation(
    db: AsyncSession,
    project: Project,
    *,
    base,
    head_lines: list[str],
    params: GetOutputSpecParams,
    with_images: bool,
) -> tuple[list[str], list[MediaInput]]:
    """The film branch (编辑模型的眼睛): version identity + per-scene facts
    (view reference, camera text, narration) + the timeline's provenance +
    — while the edit gate is on — the read-time ``base_ref``, the candidate
    view catalog and the view screenshots. ``base`` is the already-resolved
    revision base (an output read pins its film's run; a no-id read takes
    the current version — live pending first). Pages come from the SAME
    seat the edit validator uses (``load_storyboard_pages`` — capture
    order), so a scene's (page, shot) reference means the same view here
    as in a patch. A missing page/shot/asset is marked honestly, never
    invented — and the version's OWN snapshot pages prove each reference's
    material identity, so materials that drifted since the design are
    named as drift, never passed off as the version's original views."""
    from app.config import settings  # deferred: config leaf
    from app.models.schemas import FilmStoryboard  # deferred: schemas edge
    from app.tools.film.edits import (  # deferred: tool seam
        ensure_scene_ids,
        film_base_cut,
        film_version_identity_digest,
    )
    from app.tools.film.storyboard import (  # deferred: tool seam
        FILM_FPS,
        canonical_film_params,
        execution_frames,
        film_scene_content,
        load_storyboard_media,
        load_storyboard_pages,
        ui_focus_moves,
    )

    lines = head_lines
    board = ensure_scene_ids(
        FilmStoryboard.model_validate(base.film_storyboard)
    )
    base_params = base.film_storyboard_params or {}
    canonical = canonical_film_params(base_params)
    gate = settings.film_edits_enabled
    pages = await load_storyboard_pages(db, project)
    # ADR-140 read seat: the composite scenes' media universe — NO duration
    # probing here (a read never downloads bytes; unknown durations report
    # as unknown).
    media = await load_storyboard_media(db, project, board)

    # 素材身份核对 (版本快照 vs 当前材料): the board's (page, shot)
    # references mean the SNAPSHOT's pages, frozen at design time. When the
    # project's current materials drifted since (a page deleted, replaced,
    # or re-captured), the same index now names a DIFFERENT asset — the
    # read never passes the current page off as the version's original
    # view: drifted indices mark the scene's view line as unrecoverable
    # and drop out of the used-by mapping (the candidate catalog still
    # lists the CURRENT materials an edit may name — the drift line keeps
    # the two apart). Snapshot-less (legacy) versions skip the check.
    drifted_pages: set[int] = set()
    execution = getattr(base, "film_storyboard_execution", None)
    snapshot_pages = (
        execution.get("pages") if isinstance(execution, dict) else None
    )
    if isinstance(snapshot_pages, list):
        for i, sp in enumerate(snapshot_pages):
            if not isinstance(sp, dict):
                continue
            snap_asset = sp.get("asset_id")
            if snap_asset is None:
                continue
            if i >= len(pages) or str(pages[i].asset_id) != str(snap_asset):
                drifted_pages.add(i)
    if drifted_pages:
        drift_list = ", ".join(str(i) for i in sorted(drifted_pages))
        lines.append(
            f"- Materials drift: page(s) {drift_list} changed or were "
            "removed since this version was designed — scenes referencing "
            "them show their ORIGINAL (page, shot) reference, which the "
            "current materials no longer stand behind (the original view "
            "is unrecoverable); re-ground those scenes with an "
            "update_scene edit naming a current view."
        )

    # Media identity drift (ADR-140): the snapshot's composite media pins
    # (asset id + storage key) against the CURRENT project assets — a
    # deleted or replaced asset is named, never silently re-resolved.
    snapshot_media = (
        execution.get("media") if isinstance(execution, dict) else None
    )
    drifted_media: list[str] = []
    if isinstance(snapshot_media, list):
        for pin in snapshot_media:
            if not isinstance(pin, dict):
                continue
            aid = pin.get("asset_id")
            if aid is None:
                continue
            entry = media.assets.get(str(aid))
            if entry is None or entry.key != pin.get("key"):
                drifted_media.append(str(aid))
    if drifted_media:
        lines.append(
            f"- Media drift: asset(s) {', '.join(drifted_media)} changed or "
            "were removed since this version was designed — composite "
            "scenes citing them cannot re-render as designed; address "
            "current assets with update_element edits."
        )

    digest = getattr(base, "film_storyboard_content_digest", None)
    lines.append(
        f"- Storyboard version: {base.film_storyboard_version}"
        + (
            f" (created via {base.film_created_via})"
            if getattr(base, "film_created_via", None)
            else ""
        )
        + (f" · content digest {digest[:12]}" if isinstance(digest, str) else "")
    )
    if gate:
        lines.append(
            f"- base_ref: {film_version_identity_digest(board, base_params, version=base.film_storyboard_version, cut=film_base_cut(base))}"
        )
    lines.append(
        f"- params: aspect {canonical['aspect']}, voiceover "
        f"{'on' if canonical['voiceover'] else 'off'}, "
        f"{_film_music_pick(canonical)}"
    )
    lines.append(
        _film_music_fact_line(
            canonical, cut_state_hint=getattr(base, "film_cut_state", None),
            spec_music=getattr(base, "film_render_spec_music", None),
            execution=getattr(base, "film_storyboard_execution", None),
        )
    )

    # The timeline's PROVENANCE (冻结时间轴 = 版本状态 — the read never
    # recomputes a cut on its own): an executed version's frames are the
    # delivered spec's (flex-baked truth); a frozen version's are its kept
    # frames; a plain draft's are its PRESENTED plan timeline recomputed by
    # the ONE frame seat on the version's own music grid; an unreadable cut
    # is named, never replaced by a guess. Two clocks are NEVER mixed on one
    # line: ``seconds`` stays the AUTHORED design value, the timeline
    # duration derives from the authoritative frames ÷ the project's fixed
    # fps (a unit conversion, never a re-allocation).
    cut_state = getattr(base, "film_cut_state", None)
    cut_frames = getattr(base, "film_cut_frames", None)
    frames: list[int] | None = None
    state_word: str | None = None
    if cut_state == "spec":
        state_word = "actual"
        lines.append(
            "- Timeline: executed cut (the delivered render spec's per-scene "
            "frames — the rendered truth)"
        )
        frames = cut_frames
    elif cut_state == "kept":
        state_word = "frozen"
        lines.append(
            "- Timeline: frozen cut (kept from the base version's "
            "established frames)"
        )
        frames = cut_frames
    elif cut_state == "unreadable":
        lines.append(
            "- Timeline: UNREADABLE — the version was executed but its spec "
            "is missing/corrupt; the actual cut is unrecoverable (per-scene "
            "durations stay absent — the authored seconds below are design "
            "values, never the actual cut)"
        )
    else:
        # "draft" (or a legacy base carrying no cut state): the presented
        # plan timeline — same formula the presentation and the run share,
        # on the version's own snapshot music grid.
        state_word = "planned"
        snapshot = getattr(base, "film_storyboard_execution", None)
        beats = None
        if isinstance(snapshot, dict):
            music = snapshot.get("music")
            if isinstance(music, dict) and isinstance(music.get("beats"), list):
                beats = music["beats"]
        frames = execution_frames(board, beats)
        lines.append(
            "- Timeline: planned (never executed — allocate+snap on the "
            "version's music grid; the run's rendered cut may shift within "
            "the narration flex bounds)"
        )
    if frames is not None and len(frames) != len(board.scenes):
        # A corrupt cut (frame count off the scene count) is named, never
        # zipped past its length.
        lines.append(
            "- The cut's frame count does not match the scene count — "
            "per-scene durations omitted (the stored timeline reads as "
            "corrupt)."
        )
        frames = None
        state_word = None
    if frames is not None:
        total = sum(frames)
        lines[-1] += f" · total {round(total / FILM_FPS, 1):g}s ({total}f)"

    used_by: dict[tuple[int, int], list[str]] = {}
    for s in board.scenes:
        # Drifted references drop out of the used-by mapping — under
        # materials drift the (page, shot) index no longer names the asset
        # the scene was designed on, so a "used by" label would pass the
        # CURRENT page off as the scene's original view.
        if s.type == "ui" and s.page not in drifted_pages:
            used_by.setdefault((s.page, s.shot), []).append(str(s.scene_id))

    # The image plan comes BEFORE the catalog: a view whose screenshot the
    # read attaches also gets its camera-target inventory printed (the legal
    # element ids an update_scene focus may name) — image set and element
    # detail are ONE set, so a summary-only catalog never reads as if the
    # ids were all known. ``targets=None`` after an explicit budget error.
    targets: list[tuple[int, int]] | None = None
    budget_error: str | None = None
    if gate and with_images:
        if params.views is not None:
            targets = [(v.page, v.shot) for v in params.views]
            if len(targets) > _FILM_VIEW_IMAGE_MAX:
                budget_error = (
                    f"- Image budget: {len(targets)} named views exceed the "
                    f"{_FILM_VIEW_IMAGE_MAX}-image read budget — no images "
                    f"attached (never a silent partial set). Name at most "
                    f"{_FILM_VIEW_IMAGE_MAX} views per read; a scoped read "
                    "carries the views' screenshots AND camera-target "
                    "inventories (the element ids)."
                )
                targets = None
        else:
            targets = [
                (p, si)
                for p, page in enumerate(pages)
                for si in range(_page_view_count(page))
            ]
            if len(targets) > _FILM_VIEW_IMAGE_MAX:
                budget_error = (
                    f"- Image budget: this project has {len(targets)} "
                    f"captured views, over the {_FILM_VIEW_IMAGE_MAX}-image "
                    "read budget — no images attached (never a silent "
                    "partial set). Re-read naming the views you need with "
                    "views (page/shot pairs from the catalog, at most "
                    f"{_FILM_VIEW_IMAGE_MAX}); a scoped read carries the "
                    "views' screenshots AND camera-target inventories (the "
                    "element ids), and naming exactly one reads it in high "
                    "resolution."
                )
                targets = None
    target_set = set(targets) if targets else set()

    lines.append(
        "- Scenes (id · type · authored seconds · timeline duration · "
        "view · content · narration):"
    )
    for i, s in enumerate(board.scenes):
        head = f"  [{s.scene_id}] {s.type} · authored {s.seconds:g}s"
        if frames is not None and state_word is not None:
            start_f = sum(frames[:i])
            head += (
                f" · {state_word} {round(frames[i] / FILM_FPS, 1):g}s "
                f"({frames[i]}f) · at {round(start_f / FILM_FPS, 1):g}–"
                f"{round((start_f + frames[i]) / FILM_FPS, 1):g}s"
            )
        if s.type == "ui":
            if s.page in drifted_pages:
                # Materials drift (版本快照核对): the current page at this
                # index is NOT the asset the scene was designed on — the
                # original view is unrecoverable from the current
                # materials, and resolving the heading/camera against the
                # wrong page would fabricate facts.
                head += (
                    f" · view: page {s.page} shot {s.shot} (materials "
                    "changed — the version's original view is "
                    "unrecoverable)"
                )
            elif 0 <= s.page < len(pages):
                view = _page_view(pages[s.page], s.shot)
                if view is None:
                    head += f" · view: page {s.page} shot {s.shot} (no such captured view)"
                else:
                    head += f' · view: page {s.page} shot {s.shot} "{view[1]}"'
            else:
                head += f" · view: page {s.page} shot {s.shot} (page not captured)"
            if s.page not in drifted_pages:
                head += " · browser frame" if s.frame else " · full-bleed"
                moves = ui_focus_moves(s, pages, with_ids=True)
                if moves:
                    head += " · camera: wide → " + " → ".join(moves) + " → settle"
        else:
            content = film_scene_content(
                s,
                frames[i] if frames is not None and i < len(frames) else None,
                media,
            )
            if content:
                head += f" · shows: {content}"
        narration = getattr(s, "narration", None)
        head += f' · narration: "{narration}"' if narration else " · silent"
        lines.append(head)

    if not gate:
        return lines, []

    # The candidate view catalog (the edit model's view menu) + the view
    # screenshots. Gate-on only: the catalog's framing and the images exist
    # for targeted edits, and the wire image form is gated with them.
    lines.append(
        "- Candidate views (the page views an update_scene edit may name):"
    )
    for p, page in enumerate(pages):
        title = (page.research.title or "").strip()
        host = f'{page.host} "{title}"' if title else page.host
        lines.append(f"  page {p} — {host} (asset {page.asset_id}):")
        if _page_view_count(page) == 0:
            lines.append(
                "    (no captured views — the capture's visual half degraded)"
            )
            continue
        shots = getattr(page, "shots", None) or ()
        for si in range(_page_view_count(page)):
            view = _page_view(page, si)
            assert view is not None  # the count seat bounds the range
            if shots:
                entry = (
                    f'    shot {si} "{view[1]}" · '
                    f"{len(shots[si].elements)} elements"
                )
            else:
                entry = f'    shot {si} "{view[1]}" (fold only — no element inventory)'
            users = used_by.get((p, si))
            if users:
                entry += f" · used by [{', '.join(users)}]"
            if shots and (p, si) in target_set:
                entry += " · camera targets:"
            lines.append(entry)
            if shots and (p, si) in target_set:
                for el in shots[si].elements:
                    el_line = f"      {el.id} · {el.kind}"
                    if el.text:
                        el_line += f' · "{el.text}"'
                    if el.covered:
                        el_line += " (covered — occluded at capture)"
                    lines.append(el_line)
    if not pages:
        lines.append("  (no captured pages in this project)")

    if budget_error is not None:
        lines.append(budget_error)
        return lines, []
    if targets is None:
        return lines, []

    max_px = _FILM_VIEW_DETAIL_PX if len(targets) == 1 else _FILM_VIEW_THUMB_PX
    images: list[MediaInput] = []
    for p, si in targets:
        ref = f"page {p} shot {si}"
        if not (0 <= p < len(pages)):
            lines.append(f"- {ref}: no such captured view (see the catalog above).")
            continue
        view = _page_view(pages[p], si)
        if view is None:
            lines.append(f"- {ref}: no such captured view (see the catalog above).")
            continue
        key, heading = view
        page = pages[p]
        users = used_by.get((p, si))
        caption = f'page {p} · shot {si} "{heading}" · {page.host}'
        caption += (
            f" · used by scene [{', '.join(users)}]"
            if users
            else " · not used by any scene"
        )
        if not key:
            lines.append(
                f"- {ref}: no screenshot stored (the capture's visual half "
                "degraded) — the catalog facts above still stand."
            )
            continue
        try:
            image = await _film_view_image(key, max_px, caption)
        except Exception:  # noqa: BLE001 — a storage hiccup is per-view news
            image = None
        if image is None:
            lines.append(
                f"- {ref}: the stored screenshot could not be read — the "
                "catalog facts above still stand."
            )
            continue
        images.append(image)
    return lines, images


# A node's program is LLM-written and short in practice — the cap is the
# module's output-budget law (observations never flood the loop), NOT the
# context's 140-char truncation: anything under the cap rides VERBATIM, an
# over-cap program says so honestly (a silent truncation here would
# re-introduce the blind-revision hole this read exists to close).
_NODE_PROGRAM_LIMIT = 4000


def _node_detail_lines(node, downstream: list[str]) -> list[str]:
    """One node's full detail (the pure renderer — the DB seat below only
    resolves and gathers). The program rides FULL, never truncated at the
    context's 140 chars: this read is the edit_graph revision's factual
    substrate (compose the NEW program from THIS one)."""
    spec = node.spec or {}
    lines = [f"Node {node.id} — type={node.type}, state={node.state}"]
    label = spec.get("summary")
    if label:
        lines.append(f"- Label: {label}")
    prompt = spec.get("prompt")
    if prompt:
        prompt = str(prompt)
        if len(prompt) > _NODE_PROGRAM_LIMIT:
            prompt = (
                prompt[:_NODE_PROGRAM_LIMIT]
                + f"… (truncated at {_NODE_PROGRAM_LIMIT} of {len(prompt)} chars)"
            )
        lines.append(f"- Program (full): {prompt}")
    else:
        lines.append("- Program: (none — this node's spec has no prompt)")
    output_ids = spec.get("output_ids") or []
    if output_ids:
        lines.append(
            f"- Products: {len(output_ids)} (ids: "
            + ", ".join(str(oid) for oid in output_ids)
            + ")"
        )
    else:
        lines.append("- Products: none")
    if downstream:
        lines.append("- Downstream: " + ", ".join(downstream))
    else:
        lines.append("- Downstream: none")
    return lines


async def get_node(db: AsyncSession, project: Project, params: GetNodeParams) -> str:
    """One graph node's FULL current program + state + products + downstream —
    the edit_graph read-before-write seat (A-1, 2026-09-22): the context's
    Graph section truncates long programs, and the revision rule ("compose
    the NEW program from the CURRENT one, never invent") is unsatisfiable
    from a truncation. Read the node here first; then compose."""
    node = await db.get(GraphNode, params.node_id)
    if node is None or str(node.project_id) != str(project.id):
        return (
            f"No node with id {params.node_id} exists in this project — "
            "pick an id from the context's Graph section."
        )
    downstream = [
        str(e.to_node)
        for e in (
            await db.execute(
                select(GraphEdge).where(
                    GraphEdge.project_id == project.id,
                    GraphEdge.from_node == node.id,
                )
            )
        )
        .scalars()
        .all()
    ]
    return "\n".join(_node_detail_lines(node, downstream))


# The caption-style catalog's model-facing behavior notes. The ids MIRROR the
# clip-spec Literal (which mirrors packages/clip/src/captions.ts — the behavior
# source of truth); adding a style = catalog line + Literal + this dict (the
# import-time assert below is the drift alarm, and the pure consistency suite
# re-gates it).
_CAPTION_STYLE_LINES: dict[str, str] = {
    "clean-bottom": "one calm line at the bottom, no animation (the default)",
    "karaoke-highlight": "one line at a time, the spoken word lights up",
    "fade-in": "each line fades in gently",
    "pop-in": "each line pops in with a slight overshoot",
    "slide-up": "each line slides up into place",
    "stacking": "recent lines stay on screen as a sliding stack",
}

_SPEC_PRESET_IDS = set(
    get_args(ClipSpec.model_fields["caption_style_preset"].annotation)
)
assert set(_CAPTION_STYLE_LINES) == _SPEC_PRESET_IDS, (
    "caption-style descriptions drifted from the clip-spec Literal: "
    f"{set(_CAPTION_STYLE_LINES) ^ _SPEC_PRESET_IDS}"
)


async def list_caption_styles(db: AsyncSession, project: Project, params) -> str:
    """The caption style presets with one-line behavior notes — the 「有什么
    其他字幕样式吗？」journey's catalog read (the options the agent offers
    ride ITS OWN speech; this is the factual substrate)."""
    lines = ["Caption style presets (the full catalog):"]
    for preset, note in _CAPTION_STYLE_LINES.items():
        lines.append(f"- {preset}: {note}")
    lines.append(
        "Offer 2-4 as options with your own wording in the interface "
        "language; the preset id rides the edit op / task param."
    )
    return "\n".join(lines)


async def search_music(db: AsyncSession, project: Project, params: SearchMusicParams) -> str:
    """The music library catalog read — 「加个 bgm，有推荐的吗？」's factual
    substrate. The catalog is the public library (platform defaults + shared
    generated pieces); a private-upload axis has no seat yet."""
    from app.pipeline.music import list_music  # deferred: pipeline weight

    catalog = await list_music(db)
    if not catalog:
        return "The music library is empty right now — no track can be recommended."
    query = (getattr(params, "query", None) or "").strip().lower()
    matches = [
        m
        for m in catalog
        if not query or query in f"{m.mood} {m.title}".lower()
    ]
    if not matches:
        moods = ", ".join(sorted({m.mood for m in catalog})[:10])
        return (
            f"No track matches \"{query}\". Available moods include: {moods}. "
            "Call with no query (or one of these moods) for the catalog."
        )
    shown = matches[:8]
    header = (
        f"Music library — {len(matches)} match(es) for \"{query}\""
        if query
        else f"Music library — the full catalog ({len(matches)} tracks)"
    )
    lines = [header + (", first 8:" if len(matches) > 8 else ":")]
    for m in shown:
        duration = f"{m.duration_seconds}s" if m.duration_seconds else "?s"
        lines.append(f"- {m.title} — mood: {m.mood} · {duration} · id={m.id}")
    return "\n".join(lines)


async def get_run_status(db: AsyncSession, project: Project, params) -> str:
    """The latest run's live status + per-step progress (G-2's seat — the
    fixed digest carries only the one-line marker now; the detail lives
    here). 「还要多久 / how far along」的答案从这读，永不猜."""
    latest_run = (
        await db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.project_id == project.id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_run is None:
        return "No runs yet in this project."
    lines = [
        f"Latest run {latest_run.id}: status={latest_run.status} "
        f"(started {_stamp(latest_run.created_at)})"
    ]
    steps = list(
        (
            await db.execute(
                select(WorkflowStep)
                .where(WorkflowStep.run_id == latest_run.id)
                .order_by(WorkflowStep.seq)
            )
        )
        .scalars()
        .all()
    )
    progress = _format_step_progress(steps)
    if progress:
        lines.append("Steps:")
        lines.extend(progress)
    return "\n".join(lines)


_RUN_HISTORY_LIMIT = 5


def _run_history_lines(runs: list[WorkflowRun]) -> list[str]:
    """The run-history roster (pure renderer): newest first, one line per
    run — id + status + start stamp + the run's receipt name (ADR-058, the
    proposal's name rides run.context). Capped at the family's history
    budget; the header owns the honest omission note."""
    lines = []
    for run in runs:
        ctx = run.context if isinstance(run.context, dict) else {}
        name = (ctx.get("name") or "").strip()
        line = (
            f"- {run.id} — {run.status} (started {_stamp(run.created_at)})"
        )
        if name:
            line += f" — {name}"
        lines.append(line)
    return lines


async def list_runs(db: AsyncSession, project: Project, params) -> str:
    """The project's recent run history (newest first, capped) — the
    「之前跑过什么 / what did we already make」 read. The LIVE detail of the
    latest run stays get_run_status's seat; this read is the roster."""
    runs = list(
        (
            await db.execute(
                select(WorkflowRun)
                .where(WorkflowRun.project_id == project.id)
                .order_by(WorkflowRun.created_at.desc())
                .limit(_RUN_HISTORY_LIMIT + 1)
            )
        )
        .scalars()
        .all()
    )
    if not runs:
        return "No runs yet in this project."
    shown = runs[:_RUN_HISTORY_LIMIT]
    omitted = len(runs) - len(shown)
    header = f"Run history (newest first, {len(shown)} run(s)"
    header += ", %d older omitted" % omitted if omitted else ""
    header += "):"
    return "\n".join([header, *_run_history_lines(shown)])


def _pending_plan_lines(plan) -> list[str]:
    """The docked plan's detail (pure renderer): the original request, the
    receipt name, the task chain (registry tool + compact params), the
    distilled extra instruction, the caption-mode answer. Params ride as
    compact JSON, capped — the chain's SHAPE is the read's point."""
    lines = []
    intent = plan.intent
    if plan.prompt:
        lines.append(f"- Original request: {plan.prompt[:200]}")
    if intent is not None and (intent.name or "").strip():
        lines.append(f"- Name: {intent.name.strip()}")
    if intent is not None and intent.tasks:
        lines.append("- Tasks:")
        for task in intent.tasks:
            params_json = (
                json.dumps(task.params, ensure_ascii=False) if task.params else ""
            )
            if len(params_json) > 160:
                params_json = params_json[:160] + "…"
            lines.append(
                f"  - {task.tool}" + (f" {params_json}" if params_json else "")
            )
    if intent is not None and intent.specific_instruction:
        lines.append(f"- Extra instruction: {intent.specific_instruction[:300]}")
    if intent is not None and intent.caption_mode:
        lines.append(f"- Caption mode: {intent.caption_mode}")
    # iter-3 S3 (A-1 观察合同 ≥ 行动合同): the decision package's READING
    # layer — revise_plan's plan_id is reachable ONLY here on the chat
    # path (the plan path sees the package block in its own context).
    plans = getattr(plan, "plans", None) or []
    if plans:
        lines.append("- Content plans (name them by plan_id when revising):")
        for i, p in enumerate(plans, start=1):
            outputs = ", ".join(
                str(o.get("kind", "?"))
                + (f" ({o['language']})" if o.get("language") else "")
                for o in (p.get("outputs") or [])
            )
            lines.append(
                f"  {i}) plan_id={p.get('plan_id')} — "
                f"{p.get('title') or '(unnamed)'}: {outputs} [{p.get('state')}]"
            )
    return lines


async def get_graph(db: AsyncSession, project: Project, params) -> str:
    """The canvas's whole current face (ADR-111 §7 — the plan-ready reveal
    makes the canvas visible BEFORE any run; the model that just showed it
    must be able to read what it shows): every node one line (state · type
    · label), in visual order (top-to-bottom, left-to-right). READ-ONLY —
    the model's canvas interface is the plan vocabulary (present_plan /
    edit_graph), never node handles (北极星 + apply_wiring_ops 唯一写口)."""
    nodes = (
        (
            await db.execute(
                select(GraphNode).where(GraphNode.project_id == project.id)
            )
        )
        .scalars()
        .all()
    )
    if not nodes:
        return "The canvas is empty — nothing has been born yet."

    def _pos(n: GraphNode) -> tuple[float, float]:
        lay = n.layout or {}
        return (float(lay.get("y", 0)), float(lay.get("x", 0)))

    lines = [f"The canvas right now ({len(nodes)} nodes, visual order):"]
    for n in sorted(nodes, key=_pos):
        spec = n.spec or {}
        label = (
            spec.get("summary") or spec.get("name") or spec.get("tool") or "…"
        )
        lines.append(f"- [{n.state}] {n.type}: {label} (id: {n.id})")
    return "\n".join(lines)


async def get_pending_plan(db: AsyncSession, project: Project, params) -> str:
    """The conversation's currently DOCKED plan (the PendingPlan awaiting the
    user's Start) — the chat path's draft-plan read (audit §7(d), 2026-09-22):
    the plan path sees this chain in its context; the chat path read it
    here or not at all. 「我刚才让你做的那个计划是什么」从这读."""
    raw = project.pending_brief if isinstance(project.pending_brief, dict) else None
    if not raw:
        return (
            "No plan is docked for confirmation right now — nothing is "
            "waiting for the user's Start."
        )
    try:
        plan = PendingPlan.model_validate(raw)
    except Exception:  # noqa: BLE001 — a stale-shaped row reads honestly
        return "A docked plan exists but its stored shape is stale — it will be rebuilt on the next proposal."
    if plan.intent is None or not plan.intent.tasks:
        # Brief-only rows (an ask turn's write) carry no chain — the honest
        # read is the same as no docked plan.
        return (
            "No plan is docked for confirmation right now — nothing is "
            "waiting for the user's Start."
        )
    lines = ["Docked plan (waiting for the user's confirmation):"]
    lines.extend(_pending_plan_lines(plan))
    return "\n".join(lines)


# ---- 证据 reads (ADR-088 §2 拍 2, 2026-09-22 迭代一): transcript search + segment
#
# The discovery chain's evidence substrate: search_transcript is the
# DETERMINISTIC retrieval read (keyword retrieval over cue lines — the cue
# law lives in app/tools/clips/transcript), get_segment reads one range's
# verbatim speech (the evidence check's twin — the agent quotes from THIS
# text, and the exploration door rejects anything else). Both degrade
# honestly on assets without word-level timestamps (the understanding
# chain hasn't finished — never a fabricated range).

_SEGMENT_TEXT_LIMIT = 4000
_SEARCH_PER_ASSET_LIMIT = 10


class SearchTranscriptParams(BaseModel):
    query: str = Field(
        description="What to find in the talk — a topic word or phrase (e.g. 'pricing', '定价')."
    )
    asset_id: UUID | None = Field(
        default=None,
        description="The asset to search (from the roster or an @-mention). Omit to search every timeline-ready asset in the project.",
    )


class GetSegmentParams(BaseModel):
    asset_id: UUID = Field(description="The asset whose timeline to read.")
    start: float = Field(description="Range start, in seconds.")
    end: float = Field(description="Range end, in seconds.")


def _cue_match_lines(matches: list[dict], speaker_map: dict | None) -> list[str]:
    """One search-hit line: [start–end] cue text (+ speaker when the
    speaker_map attributes one). The range anchor is the point — the
    agent's propose_candidates members copy these anchors."""
    lines = []
    for m in matches:
        line = f"- [{m['start']:.1f}–{m['end']:.1f}] {m['text']}"
        speaker = speaker_at(speaker_map, m["start"], m["end"])
        if speaker:
            line += f" ({speaker})"
        lines.append(line)
    return lines


def _asset_label(asset: Asset) -> str:
    return asset.display_name or "(text)"


async def search_transcript(
    db: AsyncSession, project: Project, params: SearchTranscriptParams
) -> str:
    """Deterministic keyword retrieval over the project's transcripts
    （拍 2「Searching… / Found 14 relevant sections」）. Hits ride cue-line
    anchors [start–end]; per-asset hits are capped with an honest omission
    note (observations never flood)."""
    assets = list(
        (
            await db.execute(select(Asset).where(Asset.project_id == project.id))
        )
        .scalars()
        .all()
    )
    if params.asset_id is not None:
        target = _resolve_asset_target(assets, params.asset_id)
        if isinstance(target, str):
            return target
        pool = [target]
    else:
        pool = [a for a in assets if a.file_url]
    timed = [a for a in pool if (a.meta or {}).get("words")]
    if not timed:
        return (
            "No timeline-ready asset in this project yet — the understanding "
            "chain (ASR word timestamps) has not finished, so there is "
            "nothing to search."
        )

    sections: list[str] = []
    grand_total = 0
    for asset in timed:
        words = (asset.meta or {}).get("words") or []
        cues, _ = group_cues(words)
        matches, total = search_cues(
            cues, params.query, limit=_SEARCH_PER_ASSET_LIMIT
        )
        grand_total += total
        if not matches:
            continue
        # The asset_id rides the header (iter-2 ⑤ live-gate fix): get_segment
        # and propose_candidates REQUIRE the id downstream, and the single-
        # file plan context never names one — without it here the agent
        # invents an id and burns loop iterations on params rejections.
        header = f"Asset {_asset_label(asset)} (asset_id: {asset.id}) — {total} hit(s)"
        if total > len(matches):
            header += f" (showing {len(matches)})"
        header += ":"
        sections.append(
            "\n".join(
                [header, *_cue_match_lines(matches, (asset.meta or {}).get("speaker_map"))]
            )
        )
    if not sections:
        return f'No section mentions "{params.query}" — try a different word, or read the understanding summary with get_understanding.'
    head = f'Search "{params.query}" — {grand_total} hit(s) across {len(sections)} asset(s):'
    return "\n".join([head, *sections])


def _segment_body(
    words: list[dict], start: float, end: float
) -> tuple[str, bool]:
    """The range's verbatim speech, capped at the observation budget —
    the truncation flag rides so the caller says so (a silent cut here
    would re-open the blind-evidence hole)."""
    text = words_in_range(words, start, end)
    if len(text) <= _SEGMENT_TEXT_LIMIT:
        return text, False
    return text[:_SEGMENT_TEXT_LIMIT] + f"… (truncated at {_SEGMENT_TEXT_LIMIT} of {len(text)} chars)", True


async def get_segment(
    db: AsyncSession, project: Project, params: GetSegmentParams
) -> str:
    """One timeline range's verbatim speech — the evidence read: the
    agent reads THIS before proposing the range as a candidate member
    (compose the excerpt from what is actually said here)."""
    if not params.start < params.end:
        return f"start ({params.start}) must be < end ({params.end})."
    asset = await db.get(Asset, params.asset_id)
    if asset is None or str(asset.project_id) != str(project.id):
        return (
            f"No asset with id {params.asset_id} exists in this project — "
            "pick an id from the roster (get_asset)."
        )
    words = (asset.meta or {}).get("words") or []
    if not words:
        return (
            f"Asset {_asset_label(asset)} has no timeline yet — the "
            "understanding chain has not finished."
        )
    timeline_end = float(words[-1].get("end") or 0.0)
    note = ""
    end = params.end
    if end > timeline_end:
        end = timeline_end
        note = f" (end clamped to the timeline's {timeline_end:.1f}s)"
    text, truncated = _segment_body(words, params.start, end)
    if not text:
        return (
            f"No speech inside [{params.start:.1f}–{end:.1f}] — the range "
            "lands in a pause or outside the talk."
        )
    header = (
        f"Segment of {_asset_label(asset)} [{params.start:.1f}–{end:.1f}]"
        f" ({end - params.start:.1f}s){note}:"
    )
    speaker = speaker_at((asset.meta or {}).get("speaker_map"), params.start, end)
    if speaker:
        header += f"\nSpeaker: {speaker}"
    return "\n".join([header, text])


def _asset_roster_line(asset: Asset) -> str:
    """One roster row (the multi-asset observation): id + name + the same
    type/duration/language bits the plan context's asset block uses — the id
    is the point (the re-call's legitimate provenance)."""
    name = asset.display_name or "(text)"
    bits = [asset.type.value if hasattr(asset.type, "value") else str(asset.type)]
    if asset.duration_seconds:
        bits.append(f"{int(asset.duration_seconds)}s")
    lang = (asset.meta or {}).get("language")
    if lang:
        bits.append(str(lang))
    return f"- {asset.id} — {name} ({' · '.join(bits)})"


def _resolve_asset_target(
    assets: list[Asset], asset_id: UUID | None
) -> Asset | str:
    """工具自证 provenance（2026-09-17 交互完整性批 ①）: an asset id's only
    legitimate sources are an @-mention or THIS tool's own roster reply
    (prior tool output) — the prompt surface never lists asset ids, so a
    required id forced the model to invent one (the 2026-09-16 incident:
    get_asset(schema reject) → silent repair window). The idless call
    resolves deterministically: 0 file assets → an honest empty; exactly 1 →
    the read proceeds (a unique reference carries no ambiguity); several →
    the roster observation — the tool never guesses a target, an ambiguity
    returns the CHOICE with the ids the re-call needs. An explicit id
    resolves by membership over the project's own assets (tenant-inherent,
    text assets included — the @-mention reach the old db.get had). Returns
    the Asset to render, or the observation text."""
    if asset_id is not None:
        asset = next((a for a in assets if str(a.id) == str(asset_id)), None)
        if asset is None:
            return (
                f"No asset with id {asset_id} exists in this project — call "
                "get_asset without an id for the roster, or use an @-mention."
            )
        return asset
    file_assets = [a for a in assets if a.file_url]
    if not file_assets:
        return "No file assets in this project — there is nothing to read."
    if len(file_assets) > 1:
        roster = "\n".join(_asset_roster_line(a) for a in file_assets)
        return (
            "Several file assets in this project — call get_asset again "
            f"with one of these ids:\n{roster}"
        )
    return file_assets[0]


async def get_asset(db: AsyncSession, project: Project, params: GetAssetParams) -> str:
    """One asset's detail — identity + processing status + language +
    duration + an opening text excerpt (the 「看这个素材」mention's read).
    The target resolution lives in ``_resolve_asset_target`` (idless 0/1/N);
    one project-scoped query, the membership check is the tenant law."""
    assets = list(
        (
            await db.execute(select(Asset).where(Asset.project_id == project.id))
        )
        .scalars()
        .all()
    )
    resolved = _resolve_asset_target(assets, params.asset_id)
    if isinstance(resolved, str):
        return resolved
    asset = resolved
    lines = [
        f"Asset {asset.id} — type={asset.type}, status={asset.processing_status}"
    ]
    lang = (asset.meta or {}).get("language")
    if lang:
        lines[0] += f", language={lang}"
    name = asset.display_name
    if name:
        lines.append(f"- Name: {name}")
    if asset.duration_seconds:
        lines.append(f"- Duration: {asset.duration_seconds}s")
    excerpt = asset_text_content(asset).strip()
    if excerpt:
        lines.append(f"- Opening text: {excerpt[:300]}")
    elif asset.processing_status == AssetStatus.FAILED:
        lines.append("- Processing FAILED — no text will land for this file.")
    elif asset.processing_status != AssetStatus.COMPLETED:
        lines.append("- Still processing — no text yet.")
    return "\n".join(lines)


def _media_candidate_row(c: dict) -> str:
    """One candidate's fact line (the paged listing and the scoped read
    share this exact rendering — one row law, two doors)."""
    bits = [c["kind"]]
    if c["kind"] == "video":
        bits.append(
            f"{c['duration_seconds']:g}s"
            if c["duration_seconds"] is not None
            else "duration unknown — a source window you cite gets "
            "verified against the real bytes"
        )
    bits.append(
        f"{c['width']}×{c['height']}"
        if c["width"] and c["height"]
        else "dimensions unknown"
    )
    if not c["usable"]:
        bits.append("NOT usable — no media bytes")
    elif c["processing"] == AssetStatus.FAILED.value:
        bits.append("content analysis failed — still usable as footage")
    name = f' "{c["title"]}"' if c["title"] else ""
    return f"- {c['id']}{name} · {' · '.join(bits)}"


_MEDIA_NOT_A_VIEWING_TRAILER = (
    "These are metadata facts, not a viewing — the system has not "
    "watched the videos. Only the user can say WHAT happens at a moment: "
    "when the request depends on the content ('the part where the button "
    "is clicked'), ask for the time range instead of guessing it."
)


async def list_project_media(db: AsyncSession, project: Project, params) -> str:
    """The film-material discovery read (ADR-140): the project's
    video/image assets a film may compose with — stable ids + facts, NEVER
    storage URLs. The facts ride the ONE listing seat
    (``project_media_candidates``) the text director's prompt renders, so
    what the agent reads and what it designs from can never drift apart.
    Facts are metadata, not a viewing — the read says so (a duration or a
    thumbnail-shaped fact is not a watching; a transcript-less video is
    still fully usable footage).

    Two doors, one seat: the PAGED listing (newest first,
    ``MEDIA_LISTING_CAP`` rows per page — a truncated listing says how to
    reach older rows; truncation never means an asset does not exist) and
    the SCOPED read (``ids`` = the user's explicit picks — past the cap or
    not — with unknown/foreign ids named honestly; project scoping never
    relaxes: the ids resolve through the project-scoped listing seat,
    never against arbitrary storage)."""
    from app.tools.film.storyboard import (  # deferred: tool seam
        MEDIA_LISTING_CAP,
        project_media_candidates,
    )

    ids = [str(i) for i in (getattr(params, "ids", None) or [])]
    offset = max(0, int(getattr(params, "offset", 0) or 0))

    if ids:
        # The scoped read: the picks ride the listing seat's pinned-first
        # ordering (tenant scoping lives THERE — an id the project does not
        # own simply finds no row), then only the named rows render.
        candidates = await project_media_candidates(db, project, pinned_ids=ids)
        wanted = set(ids)
        shown = [c for c in candidates if c["id"] in wanted]
        found = {c["id"] for c in shown}
        missing = [i for i in dict.fromkeys(ids) if i not in found]
        lines = [
            f"Project media — {len(shown)} selected asset(s) a film may "
            "cite by id (cite only this project):"
        ]
        lines.extend(_media_candidate_row(c) for c in shown)
        for m in missing:
            lines.append(
                f"- {m} — not one of this project's assets (unknown id)"
            )
        lines.append(_MEDIA_NOT_A_VIEWING_TRAILER)
        return "\n".join(lines)

    candidates = await project_media_candidates(db, project)
    if not candidates:
        return (
            "No video or image assets in this project — footage or images "
            "the user uploads land here and become citable by id."
        )
    total = len(candidates)
    shown = candidates[offset : offset + MEDIA_LISTING_CAP]
    if not shown:
        return (
            f"Project media — {total} asset(s) exist, but no assets in "
            f"this page (offset={offset} is past the end; the first page "
            "is offset=0)."
        )
    complete = offset == 0 and total <= MEDIA_LISTING_CAP
    lines = [
        f"Project media — {total} asset(s) a film may cite by id "
        "(cite only this project"
        + ("; an id not listed does not exist):" if complete else "):")
    ]
    lines.extend(_media_candidate_row(c) for c in shown)
    end = offset + len(shown)
    if end < total:
        lines.append(
            f"(showing {offset + 1}–{end} of {total} — older assets: "
            f"call again with offset={end})"
        )
    lines.append(_MEDIA_NOT_A_VIEWING_TRAILER)
    return "\n".join(lines)


# ---- 资产角色 pins (ADR-078 判词④) — the shared inheritance read -------------


async def _conversation_role_pins(
    db: AsyncSession, project: Project
) -> tuple[str | None, str | None]:
    """The conversation's current role pins (source_asset_id,
    exemplar_asset_id) — reference 常驻可回读's read seat. The pending plan's
    pins win while one is on the table (the pre-run state — a role answer
    just settled them); else the latest run's context pins (what the last
    run actually ran with — the post-run inheritance the chat path's
    proposal dispatch reads). Each None when unset. Pure read — the WRITE
    seat is service.py's _stamp_role_pins, the only one."""
    pending = project.pending_brief if isinstance(project.pending_brief, dict) else {}
    source = pending.get("source_asset_id")
    exemplar = pending.get("exemplar_asset_id")
    if source or exemplar:
        return (str(source) if source else None, str(exemplar) if exemplar else None)
    latest_run = (
        await db.execute(
            select(WorkflowRun)
            .where(WorkflowRun.project_id == project.id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    ctx = (latest_run.context or {}) if latest_run is not None else {}
    source = ctx.get("source_asset_id")
    exemplar = ctx.get("exemplar_asset_id")
    return (str(source) if source else None, str(exemplar) if exemplar else None)


async def get_craft_skeleton(
    db: AsyncSession, project: Project, params: GetCraftSkeletonParams
) -> str:
    """The reference video's craft skeleton — what a remix BORROWS (ADR-078):
    aspect / shot rhythm / caption best-fit / music mood = measured facts
    (never guesses), plus the honest 做不到 list (gaps — the 带理由纠偏
    substrate, JOURNEYS 旅程二 2b). The craft_decompiled trigger turn's first
    read; the 「照这个案例做」family's factual substrate."""
    from app.pipeline.decompile import (  # deferred: pipeline weight
        find_reusable_skeleton,
    )

    asset_id = getattr(params, "asset_id", None)
    if asset_id is None:
        _, pinned = await _conversation_role_pins(db, project)
        asset_id = pinned
        if asset_id is None:
            return (
                "No reference video is pinned in this conversation — the "
                "user pins one by @-mentioning a video as the case to "
                "imitate, or by answering the role question."
            )
    asset = await db.get(Asset, UUID(str(asset_id)))
    if asset is None or str(asset.project_id) != str(project.id):
        return (
            f"No asset with id {asset_id} exists in this project — pick an "
            "id from the context's Assets list or an @-mention."
        )
    if asset.type != AssetType.VIDEO:
        return (
            f"Asset {asset.id} is not a video — only a video can be a style "
            "reference."
        )
    row = await find_reusable_skeleton(db, project, asset)
    if row is None:
        status = str(asset.processing_status)
        if status in ("failed",):
            # A failed processing never produces a warm skeleton — the
            # "still processing" copy below would stall the planner FOREVER
            # on this asset (R1 B1 S16 实测: the agent waits for a skeleton
            # that never lands and the remix journey dead-ends pre-plan).
            return (
                "The reference video's own processing FAILED, so no warm "
                "skeleton is coming — but a remix is still possible: the "
                "run's decompile step reads the bytes directly, and if the "
                "case proves unreadable the cut honestly proceeds as a "
                "regular one (exemplar params fall back to defaults). "
                "Present the plan, saying this plainly."
            )
        if status != "completed":
            return (
                "The reference video is still processing — its craft "
                "skeleton lands in a moment. Say so honestly rather than "
                "guessing at its style."
            )
        return (
            "No craft skeleton exists for this video yet — it materializes "
            "when the decompile step runs (or its warm fires on the role "
            "pin). Never invent its style."
        )
    try:
        s = CraftSkeleton.model_validate(row.payload)
    except Exception:  # noqa: BLE001 — a stale-shaped row reads honestly
        return "A craft skeleton exists but its stored shape is stale — it will be regenerated on the next run."
    name = asset.display_name or str(asset.id)
    lines = [f'Craft skeleton of "{name}" (measured, zero guessing):']
    lines.append(
        f"- Aspect {s.aspect}, {s.duration_seconds:.0f}s, "
        f"{s.rhythm.shot_count} shots "
        f"({s.rhythm.cuts_per_minute:.0f} cuts/min — {s.rhythm.pace} pace)"
    )
    if s.captions.present:
        cap = f'- Captions: preset "{s.captions.preset}"'
        if s.captions.color:
            cap += f", color {s.captions.color}"
        if s.captions.position is not None:
            cap += f", centered at y={s.captions.position.y:.2f}"
        lines.append(cap)
    else:
        lines.append("- Captions: none detected in the case")
    if s.music_mood:
        lines.append(f'- Music mood: "{s.music_mood}"')
    if s.hook_device:
        lines.append(f"- Opening hook: {s.hook_device}")
    if s.gaps:
        lines.append("- What a remix CANNOT reproduce (say this honestly):")
        for gap in s.gaps:
            wording = (
                "not possible with the current render contract"
                if gap.severity == "unsupported"
                else "not yet available"
            )
            detail = f" — {gap.detail}" if gap.detail else ""
            lines.append(f"  - {gap.kind}: {wording}{detail}")
    return "\n".join(lines)


# ---- get_artifact (iter-3 S6, ADR-088 §7 read 洞销账 / N-58) ----------------------

_ARTIFACT_MEMBERS_CAP = 12


async def get_artifact(
    db: AsyncSession, project: Project, params: GetArtifactParams
) -> str:
    """One exploration artifact's user-safe full fields: the candidate
    collection's sections (verbatim), a pick's verdict/reason + the section
    it POINTS at (R7 dereferenced at read time — the pointer never makes
    the model chase a second read), a plan card's deliverables. Tenant-scoped
    like every read; a miss answers honestly."""
    node = await db.get(ExplorationRow, params.artifact_id)
    if node is None or str(node.project_id) != str(project.id):
        return (
            f"No exploration artifact with id {params.artifact_id} exists in "
            "this project — pick an id from a discovery-chain observation."
        )
    spec = node.spec or {}
    kind = spec.get("exploration_kind")
    if kind == KIND_CANDIDATE_SET:
        members = spec.get("members") or []
        lines = [
            f"Candidate collection (id={node.id}, state={node.state}) — "
            f"topic \"{spec.get('topic')}\", {len(members)} section(s):"
        ]
        for i, m in enumerate(members[: _ARTIFACT_MEMBERS_CAP]):
            speaker = m.get("speaker") or "—"
            lines.append(
                f"  {i}) [{m.get('start')}–{m.get('end')}s] {speaker}: "
                f"{m.get('excerpt') or ''}"
            )
        if len(members) > _ARTIFACT_MEMBERS_CAP:
            lines.append(f"  … ({len(members) - _ARTIFACT_MEMBERS_CAP} more sections)")
        return "\n".join(lines)
    if kind == KIND_SELECT:
        idx = spec.get("member_index")
        lines = [
            f"Pick (id={node.id}, state={node.state}): member {idx} of "
            f"collection {spec.get('candidate_set_id')}",
            f"- verdict: {spec.get('verdict')}",
            f"- reason: {spec.get('reason')}",
        ]
        # R7 dereference: the pointed member's range + excerpt ride the read.
        cset = await db.get(ExplorationRow, UUID(str(spec.get("candidate_set_id"))))
        members = ((cset.spec or {}).get("members") or []) if cset is not None else []
        if isinstance(idx, int) and 0 <= idx < len(members):
            m = members[idx]
            lines.append(
                f"- the section: [{m.get('start')}–{m.get('end')}s] "
                f"{m.get('excerpt') or ''}"
            )
        return "\n".join(lines)
    if kind == KIND_CONTENT_PLAN:
        outputs = spec.get("outputs") or []
        lines = [
            f"Plan (id={node.id}, state={node.state}): "
            f"{spec.get('title') or '(unnamed)'} — from pick "
            f"{spec.get('select_id')}, {len(outputs)} output(s):"
        ]
        for o in outputs:
            line = f"  - {output_fact(o)}"
            if o.get("brief"):
                line += f" — {o['brief']}"
            lines.append(line)
        issues = spec.get("issues") or []
        if issues:
            lines.append("- open gaps: " + "; ".join(str(i) for i in issues))
        return "\n".join(lines)
    return (
        f"Exploration artifact {node.id} (state={node.state}) — unrecognized "
        f"kind {kind!r}."
    )


# ---- web reads (the research pair's chat projection) -------------------------
#
# The SAME zero-key web pair the research node drives (app/tools/research/
# web.py), projected into the chat read family unchanged — one capability,
# one implementation, two altitudes (chat read / DAG loop); no second web
# tool with qualification clauses. Degrade-honest by construction: an empty
# read is an honest "nothing came back" observation, never an exception.

_WEB_SNIPPET_CAP = 300


async def get_web_page(db: AsyncSession, project: Project, params: GetWebPageParams) -> str:
    """Read one web page's readable text. consult-first (world-seat 律):
    the project's stored reading (page_readings) answers when present —
    snapshot semantics, the capture stamp rides the observation; a fresh
    fetch happens only on a miss or an explicit ``refresh``, and writes
    back through the seat's own short session (the turn's transaction
    stays read-only). 「这个网站你看看？」's factual substrate: the link
    shared for discussion is never material, but it is always readable."""
    url = params.url.strip()
    if not params.refresh:
        stored = await page_reading_for_url(db, project.id, url)
        if stored is not None:
            when = stored.fetched_at.date().isoformat()
            return (
                f"The project's stored reading of {url} (captured {when} — "
                "if the user says the page has changed since, re-read with "
                f"refresh=true):\n\n{stored.text}"
            )
    text = await fetch_text(url)
    if not text:
        return (
            f"Nothing readable came back from {url} — the page was "
            "unreachable, refused the fetch, or carried no readable text."
        )
    await write_page_reading(project.id, url, text)
    return f"Readable text of {url} (capped at {FETCH_TEXT_CAP} chars):\n\n{text}"


async def search_web(db: AsyncSession, project: Project, params: SearchWebParams) -> str:
    """Search the web (web_search — DDG zero-key, organic hits only)."""
    query = params.query.strip()
    hits = await web_search(query)
    if not hits:
        return f"The web search for \"{query}\" came back empty — the trail ran dry."
    lines = [f"Web results for \"{query}\":"]
    for h in hits:
        lines.append(f"- {h['title']} — {h['url']}")
        snippet = (h.get("snippet") or "")[:_WEB_SNIPPET_CAP]
        if snippet:
            lines.append(f"  {snippet}")
    return "\n".join(lines)
