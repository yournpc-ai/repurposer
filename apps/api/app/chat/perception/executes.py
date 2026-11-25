"""The perception family's read implementations (ADR-077 判词②, T2b).

只读纪律: this module holds ZERO write functions — every execute below only
reads (a SELECT, or the web pair's read-only fetch) and renders compact
model-facing text (the observation). The editor's writes use its native tools.

Every execute is tenant-scoped to the turn's project (the same ownership
check as the edit verbs' doors — a client-pinned id resolves only inside its
own project) and answers a MISS honestly (an empty observation the model
adapts to), never raises on content. Infrastructure failures (the DB
itself) propagate — the turn's honest terminal failure, never a fabricated
read (静默降级禁令).

Output budget: observations are model context, not user copy — each is
capped (see the per-tool caps) so a read never floods the loop.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.models.schemas import (
    AssetStatus,
    AssetType,
    GetVideoVersionParams,
    MaterialUnderstanding,
)
from app.models.tables import (
    Asset,
    Output,
    Project,
)
from app.editing.transcript import (
    build_anchored_transcript,
    group_cues,
    search_cues,
    speaker_at,
    words_in_range,
)
from app.tools.research.web import FETCH_TEXT_CAP, fetch_text, web_search
from app.tools.world import page_reading_for_url, write_page_reading
from app.pipeline.assets import asset_text_content


# ---- params models (package-local, like tools/<pkg>/params.py) --------------
#
# Default pydantic config on purpose (no extra="forbid"): the loop boundary
# already pops the retired habit keys (type/kind/prose), and ignoring unknown
# extras here is the read-tolerant posture — a read call never dies on an
# extra key. Field descriptions ARE the model's parameter documentation
# (they compile into the tool's JSON schema).




class GetAssetParams(BaseModel):
    asset_id: UUID | None = Field(
        default=None,
        description=(
            "素材 ID，来自 @ 引用或先前 get_asset 返回的清单。若为 null 且项目只有一个文件素材，读取该素材；若有多个，返回带 ID 的清单。"
        ),
    )


class ListProjectMediaParams(BaseModel):
    ids: list[str] | None = Field(
        default=None,
        description=(
            "只按 ID 读取用户明确选定的素材（来自 @ 引用或之前的清单）。超出清单单页上限的 ID 也可读取。null 表示按最新在前分页列出。"
        ),
    )
    offset: int = Field(
        default=0,
        description=(
            "跳过的素材数量，按最新在前排序。清单提示有更早记录时用于翻页，例如每页 40 条时，第二页用 offset=40。"
        ),
        ge=0,
    )


class SearchMusicParams(BaseModel):
    genre: str | None = None
    energy: str | None = None
    bpm: int | None = Field(default=None,gt=0)
    query: str | None = Field(
        default=None,
        description="用于匹配曲目标题、标签、情绪或提示词的关键词。null 或空字符串表示按复用优先级列出可用曲库。",
    )
    style_preset: str | None = Field(
        default=None,
        description="可选的视觉风格预设（institutional_dark, swiss_paper, vox_editorial, kinetic_anime），优先匹配兼容配乐。",
    )
    mood: str | None = Field(
        default=None,
        description="可选的曲目情绪标签（如 editorial-warm, tech-pulse, calm, cinematic）。",
    )
    tags: list[str] | None = Field(
        default=None,
        description="可选的配乐标签列表（如 ['piano', 'warm', 'modern']）。",
    )
    instrumental_only: bool = Field(
        default=True,
        description="默认 true（只搜索无人声纯音乐，避免与旁白打架）。",
    )


class SearchVoicesParams(BaseModel):
    pacing: str | None = None
    language: str | None = Field(
        default=None,
        description="目标配音语言代码（如 'en', 'zh', 'fr', 'de', 'es', 'it'）。",
    )
    style_preset: str | None = Field(
        default=None,
        description="可选的视觉风格预设（institutional_dark, swiss_paper, vox_editorial, kinetic_anime）。",
    )
    tone: str | None = Field(
        default=None,
        description="可选音色气质标签（如 'warm', 'authoritative', 'crisp', 'founder', 'documentary'）。",
    )
    query: str | None = Field(
        default=None,
        description="自由关键词（匹配名称、描述、设计提示词或标签）。留空列出当前可用音色库。",
    )
    limit: int = Field(default=12, ge=1, le=50)


class GetWebPageParams(BaseModel):
    url: str = Field(
        description="从本轮或此前对话中逐字复制的完整网页 URL。返回的可读正文有长度上限。空结果表示无法访问、被拒绝或没有可读内容。"
    )
    refresh: bool = Field(
        default=False,
        description="false 表示有已存的页面读取结果时复用。仅当用户说页面已变更时才设为 true，重新抓取并替换原记录。",
    )


class SearchWebParams(BaseModel):
    query: str = Field(
        description="具体且独立完整的网页搜索问题。点明主题，不使用“上面的内容”等指代。"
    )


# ---- shared rendering helpers ------------------------------------------------

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
    from app.pipeline.understanding import (  # deferred: pipeline weight
        find_reusable_understanding,
        warm_understanding,
    )
    from app.pipeline.step_context import asset_digest, list_assets
    from app.providers.llm import get_llm_client

    assets = await list_assets(db, project.id)
    if not assets:
        return (
            "No assets in this project yet — there is no material to read. "
            "If the user means to work from material, they need to upload or "
            "paste it first.",
            False,
        )
    if any(
        asset.processing_status in (AssetStatus.PENDING, AssetStatus.PROCESSING)
        for asset in assets
    ) and not get_llm_client().capabilities.understands_video_audio:
        await _stamp_processing_requested(project.id)
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
            if pending and not get_llm_client().capabilities.understands_video_audio:
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
            await warm_understanding(project.id)
            warm_kicked = True


async def get_understanding(db: AsyncSession, project: Project, params) -> str:
    """The project's material understanding — what the material SAYS (the
    warm/run materialized row, content-addressed by the current asset set).
    Journeys: 「我看了——你在讲 X」的读法 + 推荐配乐/样式前的氛围匹配.

    Registry-compatible wrapper (text only); the turn dispatch seat reads
    :func:`understanding_observation` for the landed flag."""
    text, _ = await understanding_observation(db, project)
    return text


async def search_music(db: AsyncSession, project: Project, params: SearchMusicParams) -> str:
    """Reuse-first search over the permanent music library (platform + owner's tracks)."""
    from app.pipeline.music import list_music, search_music_library

    query = (getattr(params, "query", None) or "").strip()
    style_preset = (getattr(params, "style_preset", None) or "").strip() or None
    mood = (getattr(params, "mood", None) or "").strip() or None
    tags = getattr(params, "tags", None) or None
    instrumental_only = bool(getattr(params, "instrumental_only", True))

    matches = await search_music_library(
        db,
        owner_id=project.user_id,
        style_preset=style_preset,
        mood=mood,
        tags=tags,
        query=query or None,
        instrumental_only=instrumental_only, genre=params.genre, energy=params.energy, bpm=params.bpm,
        limit=12,
    )
    if not matches:
        catalog = await list_music(db, user_id=project.user_id)
        if not catalog:
            return "The music library is empty right now — generate a reusable BGM track via generate_music."
        moods = ", ".join(sorted({m.mood for m in catalog})[:10])
        return (
            f"No track matches those filters. Available moods include: {moods}. "
            "Call with no filters to inspect all available tracks, or call generate_music to save a new permanent track."
        )
    shown = matches[:10]
    header = (
        f"Music library — {len(matches)} match(es)"
        if (query or style_preset or mood or tags)
        else f"Music library — {len(matches)} reusable track(s)"
    )
    lines = [header + (", top 10:" if len(matches) > 10 else ":")]
    for m in shown:
        duration = f"{m.duration_seconds}s" if m.duration_seconds else "?s"
        tag_str = f" · tags={','.join(m.tags)}" if m.tags else ""
        style_str = f" · styles={','.join(m.compatible_styles)}" if m.compatible_styles else ""
        lufs_str = f" · {m.lufs:.1f} LUFS" if m.lufs is not None else ""
        lines.append(
            f"- {m.title} — mood: {m.mood} · {duration}{tag_str}{style_str}{lufs_str} · uses={int(m.use_count or 0)} · music_id={m.id} (Music library, not Asset)"
        )
    return "\n".join(lines)


async def search_voices(db: AsyncSession, project: Project, params: SearchVoicesParams) -> str:
    """Reuse-first search over the permanent voiceprint library + verified stock voices."""
    from app.editing.catalog import VOICE_CATALOG
    from app.pipeline.voices import search_voices as query_voices

    language = (getattr(params, "language", None) or "").strip() or None
    style_preset = (getattr(params, "style_preset", None) or "").strip() or None
    tone = (getattr(params, "tone", None) or "").strip() or None
    query = (getattr(params, "query", None) or "").strip() or None
    limit = int(getattr(params, "limit", 12) or 12)

    library_rows = await query_voices(
        db,
        owner_id=project.user_id,
        language=language, pacing=params.pacing,
        style_preset=style_preset,
        tone=tone,
        query=query,
        limit=limit,
    )

    lines: list[str] = []
    if library_rows:
        lines.append(f"Permanent voice library — {len(library_rows)} match(es) (reuse-first):")
        for v in library_rows:
            langs = ",".join(v.languages or []) or "multi"
            tags = f" · tones={','.join(v.tone_tags)}" if v.tone_tags else ""
            styles = f" · styles={','.join(v.compatible_styles)}" if v.compatible_styles else ""
            lines.append(
                f"- {v.name} — voice_id={v.id} · provider_voice_id={v.provider_voice_id} · langs={langs} · scope={v.scope}{tags}{styles} · uses={int(v.use_count or 0)}"
            )
    else:
        lines.append("Permanent voice library — 0 saved custom/curated matches for these filters.")

    lang_norm = (language or "").lower()
    stock_matches = [
        item
        for item in VOICE_CATALOG
        if (not lang_norm or lang_norm in item["languages"])
        and (
            not query
            or query.lower() in f"{item['voice_id']} {item['style']} {' '.join(item['languages'])}".lower()
        )
        and (not tone or tone.lower() in item["style"].lower())
    ]
    if stock_matches:
        lines.append("Verified stock voices (fallback when no saved voiceprint matches):")
        for item in stock_matches[:6]:
            lines.append(
                f"- {item['voice_id']} — langs={','.join(item['languages'])} · {item['style']}"
            )
    lines.append("Tip: Reuse an existing voice_id first; call design_voice only when no existing voice fits the brand timbre.")
    return "\n".join(lines)


# ---- 证据 reads (ADR-088 §2 拍 2, 2026-09-22 迭代一): transcript search + segment
#
# The discovery chain's evidence substrate: search_transcript is the
# DETERMINISTIC retrieval read (keyword retrieval over cue lines — the cue
# transcript grouping lives in editing/transcript.py; get_segment reads one range's
# verbatim speech (the evidence check's twin — the agent quotes from THIS
# text, and the exploration door rejects anything else). Both degrade
# honestly on assets without word-level timestamps (the understanding
# chain hasn't finished — never a fabricated range).

_SEGMENT_TEXT_LIMIT = 4000
_SEARCH_PER_ASSET_LIMIT = 10


class SearchTranscriptParams(BaseModel):
    query: str = Field(
        description="希望在演讲中查找的主题词或短语，例如 pricing 或“定价”。"
    )
    asset_id: UUID | None = Field(
        default=None,
        description="要搜索的素材，取自清单或 @ 引用。省略则搜索本项目中所有时间线已就绪的素材。",
    )


class GetSegmentParams(BaseModel):
    asset_id: UUID = Field(description="要读取时间线的素材。")
    start: float = Field(description="区段起始秒数。")
    end: float = Field(description="区段结束秒数。")


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
            await db.execute(select(Asset).where(
                Asset.user_id == project.user_id,
                Asset.id == params.asset_id if params.asset_id else Asset.project_id == project.id,
            ))
        )
        .scalars()
        .all()
    )
    resolved = _resolve_asset_target(assets, params.asset_id)
    if isinstance(resolved, str):
        return resolved
    asset = resolved
    source_url = (asset.meta or {}).get("capture_url")
    lines = [
        f"Asset {asset.id} — type={asset.type}, status={asset.processing_status}"
    ]
    lang = (asset.meta or {}).get("language")
    if lang:
        lines[0] += f", language={lang}"
    name = asset.display_name
    if name:
        lines.append(f"- Name: {name}")
    if source_url:
        lines.append(f"- Source URL: {source_url}")
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
MEDIA_LISTING_CAP = 40


async def _project_media_candidates(
    db: AsyncSession,
    project: Project,
    *,
    pinned_ids: list[str] | None = None,
) -> list[dict]:
    rows = list((
        await db.execute(
            select(Asset)
            .where(
                Asset.project_id == project.id,
                Asset.type.in_((AssetType.VIDEO, AssetType.IMAGE)),
            )
            .order_by(Asset.created_at.desc())
            .execution_options(populate_existing=True)
        )
    ).scalars().all())
    candidates = []
    for row in rows:
        meta = row.meta if isinstance(row.meta, dict) else {}
        duration = float(row.duration_seconds) if row.duration_seconds is not None else None
        probed = meta.get("probed_duration_seconds")
        if isinstance(probed, (int, float)) and not isinstance(probed, bool):
            duration = float(probed)
        candidates.append({
            "id": str(row.id),
            "kind": row.type.value,
            "title": row.display_name,
            "duration_seconds": duration,
            "width": meta.get("width") if isinstance(meta.get("width"), int) else None,
            "height": meta.get("height") if isinstance(meta.get("height"), int) else None,
            "usable": bool(row.file_url),
            "processing": row.processing_status.value if row.processing_status else None,
        })
    if pinned_ids:
        by_id = {candidate["id"]: candidate for candidate in candidates}
        pinned = [
            by_id[asset_id]
            for asset_id in dict.fromkeys(str(item) for item in pinned_ids)
            if asset_id in by_id
        ]
        if pinned:
            pinned_set = {candidate["id"] for candidate in pinned}
            candidates = pinned + [c for c in candidates if c["id"] not in pinned_set]
    return candidates

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
    project_media_candidates = _project_media_candidates

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


_WEB_SNIPPET_CAP = 500


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


async def get_video_version(db: AsyncSession, project: Project, params: GetVideoVersionParams) -> str:
    """The video chain's explicit version read (ADR-145 §2.2): one
    Composition's current version or one exact version, with the canonical
    storyboard's full facts — the immutable version read and the
    answer seat for 'what does the storyboard look like now'."""
    from app.editing.service import (  # deferred: domain seat
        format_storyboard_text,
        video_version_read,
    )
    from app.editing.store import CompositionNotFound, PermissionDenied

    try:
        if params.purpose == "edit":
            from app.editing.store import content_of, get_video_version
            import json

            composition, version = await get_video_version(
                db, owner_id=project.user_id, composition_id=params.composition_id
            )
            content = content_of(version)
            clips = [
                clip for track in content.timeline.tracks for clip in track.clips
                if (params.clip_id is None or clip.clip_id == params.clip_id)
                and (params.scene_id is None or clip.scene_id == params.scene_id)
            ]
            read = {
                "base_ref": {
                    "composition_id": str(composition.id),
                    "composition_version_id": str(version.id),
                    "content_digest": version.content_digest,
                },
                "scenes": [
                    scene.model_dump(mode="json") for scene in content.scenes
                    if params.scene_id is None or scene.scene_id == params.scene_id
                ],
                "clips": [clip.model_dump(mode="json") for clip in clips],
            }
            observation = json.dumps(read, ensure_ascii=False)
            version_id, digest = str(version.id), version.content_digest
        else:
            read = await video_version_read(
                db,
                owner_id=project.user_id,
                version_id=params.version_id,
                composition_id=params.composition_id,
                output_id=params.output_id,
            )
            observation = format_storyboard_text(read)
            version_id = read.get("composition_version_id")
            digest = read.get("content_digest")
    except (CompositionNotFound, PermissionDenied):
        return (
            "No such video version in your works — name a version_id or "
            "composition_id from a storyboard card or an earlier read."
        )
    from app.agents.tool_loop import ToolObservation

    return ToolObservation(
        observation,
        context_lifetime="project",
        context_keys=(f"composition:{version_id}:{digest}",) if version_id and digest else (),
        project_text=(
            "The exact saved version is in CURRENT PROJECT EVIDENCE with its base_ref; "
            "recover this full observation by its context item id when needed."
        ),
    )
