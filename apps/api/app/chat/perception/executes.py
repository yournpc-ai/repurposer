"""The perception family's read implementations (ADR-077 判词②, T2b).

只读纪律: this module holds ZERO write functions — every execute below only
SELECTs and renders compact model-facing text (the observation). The world's
READINGS live here; the world's WRITINGS stay behind the three doors
(edit ops / wiring ops / ``create_run``) — a read tool is never a doorbell
for a write (简报 §3).

Every execute is tenant-scoped to the turn's project (the same ownership
check as ``apply_edit_ops`` — a client-pinned id resolves only inside its
own project) and answers a MISS honestly (an empty observation the model
adapts to), never raises on content. Infrastructure failures (the DB
itself) propagate — the turn's honest terminal failure, never a fabricated
read (静默降级禁令).

Output budget: observations are model context, not user copy — each is
capped (see the per-tool caps) so a read never floods the loop.
"""

from typing import get_args
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.models.schemas import ClipSpec, MaterialUnderstanding
from app.models.tables import (
    Asset,
    Output,
    Project,
    WorkflowRun,
    WorkflowStep,
)


# ---- params models (package-local, like tools/<pkg>/params.py) --------------
#
# Default pydantic config on purpose (no extra="forbid"): the loop boundary
# already pops the retired habit keys (type/kind/prose), and ignoring unknown
# extras here is the read-tolerant posture — a read call never dies on an
# extra key. Field descriptions ARE the model's parameter documentation
# (they compile into the tool's JSON schema).


class GetOutputSpecParams(BaseModel):
    output_id: UUID = Field(
        description="The output's id (from the context's Current outputs list or an @-mention)."
    )


class GetAssetParams(BaseModel):
    asset_id: UUID = Field(
        description="The asset's id (from the context's Assets list or an @-mention)."
    )


class SearchMusicParams(BaseModel):
    query: str | None = Field(
        default=None,
        description="A mood or keyword to match against track mood/title (e.g. 'calm', 'upbeat'); null/empty = the full catalog.",
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


# ---- the six reads -----------------------------------------------------------


async def get_understanding(db: AsyncSession, project: Project, params) -> str:
    """The project's material understanding — what the material SAYS (the
    warm/run materialized row, content-addressed by the current asset set).
    Journeys: 「我看了——你在讲 X」的读法 + 推荐配乐/样式前的氛围匹配."""
    from app.pipeline.node_runners import (  # deferred: pipeline weight
        _find_reusable_understanding,
    )
    from app.pipeline.step_context import _asset_digest, _list_assets

    assets = await _list_assets(db, project.id)
    if not assets:
        return (
            "No assets in this project yet — there is no material to read. "
            "If the user means to work from material, they need to upload or "
            "paste it first."
        )
    digest = _asset_digest(assets)
    row = await _find_reusable_understanding(db, project, digest)
    if row is None:
        pending = [a for a in assets if str(a.processing_status) != "completed"]
        if pending:
            return (
                f"The material understanding is not ready yet — {len(pending)} "
                "asset(s) are still processing. Answer from what you know and "
                "say the material read lands in a moment."
            )
        return "No material understanding exists yet for the current assets."
    try:
        u = MaterialUnderstanding.model_validate(row.payload)
    except Exception:  # noqa: BLE001 — a stale-shaped row reads honestly
        return "A material understanding exists but its stored shape is stale — it will be regenerated on the next run."

    lines = ["Material understanding (the current asset set):"]
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
    if u.topic_boundaries or u.climax_spans:
        lines.append(
            f"- Beat map: {len(u.topic_boundaries)} topic boundaries, "
            f"{len(u.climax_spans)} climax spans"
        )
    if len(lines) == 1:
        # The stub shape (a no-material chain's placeholder row) — say so.
        lines.append("- (empty stub — the chain ran without material)")
    return "\n".join(lines)


async def get_output_spec(db: AsyncSession, project: Project, params: GetOutputSpecParams) -> str:
    """One output's current state — the read-before-write seat for relative
    revisions (「字幕调小一点」「声音小一点不」: compose the op from the CURRENT
    settings, never invent them)."""
    from app.agents.contexts import _output_one_liner  # deferred: assembly layer

    output = await db.get(Output, params.output_id)
    if output is None or str(output.project_id) != str(project.id):
        return (
            f"No output with id {params.output_id} exists in this project — "
            "pick an id from the context's Current outputs list or an "
            "@-mention."
        )
    lines = [
        f"Output {output.id} — type={output.type}, language={output.language}, "
        f"status={output.status}"
    ]
    one_liner = _output_one_liner(output)
    if one_liner:
        lines.append(f"- First line: {one_liner}")
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
    return "\n".join(lines)


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


async def get_asset(db: AsyncSession, project: Project, params: GetAssetParams) -> str:
    """One asset's detail — identity + processing status + language +
    duration + an opening text excerpt (the 「看这个素材」mention's read)."""
    asset = await db.get(Asset, params.asset_id)
    if asset is None or str(asset.project_id) != str(project.id):
        return (
            f"No asset with id {params.asset_id} exists in this project — "
            "pick an id from the context's Assets list or an @-mention."
        )
    lines = [
        f"Asset {asset.id} — type={asset.type}, status={asset.processing_status}"
    ]
    lang = (asset.meta or {}).get("language")
    if lang:
        lines[0] += f", language={lang}"
    name = asset.title or (
        asset.file_url.rsplit("/", 1)[-1] if asset.file_url else None
    )
    if name:
        lines.append(f"- Name: {name}")
    if asset.duration_seconds:
        lines.append(f"- Duration: {asset.duration_seconds}s")
    excerpt = (asset.transcript or asset.extracted_text or "").strip()
    if excerpt:
        lines.append(f"- Opening text: {excerpt[:300]}")
    elif str(asset.processing_status) != "completed":
        lines.append("- Still processing — no text yet.")
    return "\n".join(lines)
