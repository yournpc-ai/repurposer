"""Modifier-step machinery (ADR-039 P1 split): the shared body of the morph
tools (remove_filler / add_music / translate_clip / dub_clip) — resolve the
clips a modifier acts on and journal the spec write. Render requests (pend +
writer barrier + mirror) live in ``app.pipeline.render_ownership`` (ADR-096
§1): every render request — birth fan-out, morph touch, failure repair —
goes through the one seat there.
"""

from uuid import UUID

from sqlalchemy import cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.tables import Asset, Message, Output, WorkflowStep
from app.models.tables import Project, WorkflowRun

# Transform kinds whose target_language faces a source language (the
# compile-time adjudication's scope — same two the runtime guard covers).
_TRANSFORM_TARGET_KINDS = ("translate_clip", "dub_clip")


async def target_clips(
    db: AsyncSession, node: WorkflowStep, project: Project
) -> list[Output]:
    """Clips a modifier step acts on: the upstream steps' output_refs (same
    run — e.g. a clips_pipeline or a previous modifier in the chain), else the
    project's existing renderable clips."""
    clip_ids: list[UUID] = []
    if node.inputs:
        upstream = list(
            (
                await db.execute(
                    select(WorkflowStep).where(
                        WorkflowStep.id.in_([UUID(str(i)) for i in node.inputs])
                    )
                )
            )
            .scalars()
            .all()
        )
        for step in upstream:
            # A FORK upstream's output_refs are NEW derived rows — its source
            # clips stay untouched and arrive via the chain's base edge
            # (select_clips / materialize_source, which is also in inputs).
            # The modifier→modifier edge exists for ORDERING only; collecting
            # the fork's rows would re-transform the derivative (an all-fork
            # translate→translate→dub chain would combinatorially fan out
            # instead of producing one version per named language).
            if (step.spec or {}).get("fork"):
                continue
            clip_ids.extend(UUID(str(ref)) for ref in (step.output_refs or []))
    if clip_ids:
        clips = list(
            (
                await db.execute(
                    select(Output).where(Output.id.in_(clip_ids), Output.type == "clip")
                )
            )
            .scalars()
            .all()
        )
    else:
        # "Existing" = PRE-RUN rows only: when every input edge is a skipped
        # fork (an all-fork chain on the existing profile, e.g. two subtitle
        # versions of clips from an earlier run), the first fork's derived
        # rows already sit in the project — an unfiltered project-wide
        # fallback would re-transform them and fan out combinatorially.
        this_run_steps = select(WorkflowStep.id).where(
            WorkflowStep.run_id == node.run_id
        )
        clips = list(
            (
                await db.execute(
                    select(Output).where(
                        Output.project_id == project.id,
                        Output.type == "clip",
                        Output.render_spec.isnot(None),
                        or_(
                            Output.workflow_step_id.is_(None),
                            Output.workflow_step_id.not_in(this_run_steps),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
    return [c for c in clips if c.render_spec]


async def modifier_target_clips(
    db: AsyncSession, node: WorkflowStep, project: Project
) -> list[Output]:
    """Target resolution for modifier steps: an explicit
    ``spec.target_output_id`` (asset-scoped chat) wins; otherwise fall back to
    the upstream/project clips (``target_clips``)."""
    target_id = (node.spec or {}).get("target_output_id")
    if target_id:
        clips = list(
            (
                await db.execute(
                    select(Output).where(
                        Output.id == UUID(str(target_id)),
                        Output.project_id == project.id,
                        Output.type == "clip",
                    )
                )
            )
            .scalars()
            .all()
        )
        return [c for c in clips if c.render_spec]
    return await target_clips(db, node, project)


async def run_origin(db: AsyncSession, run: WorkflowRun) -> str:
    """Operations-journal source for run-dispatched morphs (agent-loop-upgrade
    W4, ADR-033 shell parity): ``"chat"`` when the run was dispatched from a
    chat message (``messages.workflow_run_id`` backlink), else ``"system"``."""
    linked = await db.scalar(
        select(func.count()).select_from(Message).where(
            Message.workflow_run_id == run.id
        )
    )
    return "chat" if linked else "system"


def _same_language_message(src_lang: str, *, zh: bool) -> str:
    """The fix-naming same-language rejection line — ONE message, two seats
    (the runtime guard's step error and the compile-time adjudication's
    422 / router repair feedback). The bilingual hint follows the source's
    direction (2026-09-13): on a zh source the 中英双语 target is en; on an
    en source it is zh — the old fixed "target en" tail coached the exact
    wrong move it was written to prevent."""
    low = src_lang.lower()
    if low == "zh":
        hint = "（中英双语的目标应为 en）" if zh else " (for Chinese-English bilingual, target en)"
    elif low == "en":
        hint = "（中英双语的目标应为 zh）" if zh else " (for Chinese-English bilingual, target zh)"
    else:
        hint = ""
    return (
        f"源素材已经是{src_lang}——目标语言必须换一种{hint}。"
        if zh
        else f"The source is already {src_lang} — the target must be a different language{hint}."
    )


async def _clip_source_language(db: AsyncSession, output: Output) -> str | None:
    """One clip's source language, the guard's precedence: the source asset's
    ASR-detected ``meta.language``, then the caption cues' lang."""
    asset_id = (output.source_ref or {}).get("asset_id")
    if asset_id:
        asset = await db.get(Asset, UUID(str(asset_id)))
        if asset is not None:
            raw = (asset.meta or {}).get("language")
            if raw:
                return str(raw)
    track0 = (output.render_spec or {}).get("caption_track") or []
    if track0 and track0[0].get("lang"):
        return str(track0[0]["lang"])
    return None


async def guard_target_differs_from_source(
    db: AsyncSession,
    clips: list[Output],
    lang: str,
    *,
    zh: bool,
) -> None:
    """Same-language guard (2026-08-17 走查实修): a translate/dub whose target
    IS the source's language produces a same-language "translation" — the
    中英双语 farce where the bilingual pair came out 繁体+简体 with no English
    anywhere (the intent router had defaulted target_language to the prompt's own
    language). Fail loud and name the fix — a silent same-language rewrite is
    the banned posture. This is the LAST backstop: the same adjudication runs
    earlier at the plan/birthplace seats (``check_transform_targets``) so a
    doomed chain bounces before the user confirms; this seat covers stale
    plans and wiring-born runs. Raises plain ``ValueError`` — errors.py passes
    an exact ValueError's authored message through to the step's user-facing
    line.
    """
    for output in clips:
        src_lang = await _clip_source_language(db, output)
        if src_lang and src_lang.lower() == str(lang).lower():
            raise ValueError(_same_language_message(src_lang, zh=zh))


async def _faced_source_languages(
    db: AsyncSession,
    project: Project,
    target_output_id: str | None,
    *,
    chain_births_clips: bool,
) -> set[str]:
    """The languages a translate/dub task would ACTUALLY face at run time
    (compile-time mirror of the runtime targeting, one truth two seats):
    the ``target_output_id``-scoped clip; a chain birthing clips
    (select_clips / cut_segments — the output_type="clips" declaration,
    N-56) → the source recording's language (the run's clips are unborn at
    plan time and come from the assets, never from the project's older
    clips); else the project's existing clips (the "existing" materialize
    profile), else the project's recording assets (the
    materialize-whole-source profile)."""
    if target_output_id:
        output = await db.get(Output, UUID(str(target_output_id)))
        lang = (
            await _clip_source_language(db, output)
            if output is not None and output.project_id == project.id
            else None
        )
        return {lang} if lang else set()

    async def _asset_languages() -> set[str]:
        assets = list(
            (
                await db.execute(
                    select(Asset).where(
                        Asset.project_id == project.id,
                        Asset.file_url.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            lang
            for asset in assets
            if (lang := (asset.meta or {}).get("language"))
        }

    if chain_births_clips:
        return await _asset_languages()
    clips = list(
        (
            await db.execute(
                select(Output).where(
                    Output.project_id == project.id,
                    Output.type == "clip",
                    Output.render_spec.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    langs = {
        lang
        for output in clips
        if (lang := await _clip_source_language(db, output))
    }
    if langs:
        return langs
    return await _asset_languages()


async def check_transform_targets(
    db: AsyncSession, project: Project, tasks: list, *, zh: bool
) -> None:
    """Compile-time same-language adjudication (chat 修复环 + birthplace
    422 两座): a translate/dub whose target IS the faced source language is
    doomed by construction — reject it where the plan is judged, naming the
    fix, so the router's repair round (chat path) or the confirm card's 422
    (typed path) lands on a runnable chain instead of failing mid-run after
    money moved (2026-09-13 实拍: "中英双语" on an en source drafted
    translate→en, confirmed, then died at the step). Unknown languages stay
    silent (no false positives) — the runtime guard remains the backstop.
    Raises plain ``ValueError`` (the caller wraps it for its own door)."""
    faced: dict[str | None, set[str]] = {}
    # "The chain births clips" reads the output_type DECLARATION (N-56:
    # select_clips and the compiler-only cut_segments both claim "clips") —
    # never a tool name.
    from app.pipeline.graph import NODE_KINDS  # deferred: import cycle

    chain_births_clips = any(
        getattr(t, "tool", None) in NODE_KINDS
        and NODE_KINDS[getattr(t, "tool")].output_type == "clips"
        for t in tasks
    )
    for t in tasks:
        if getattr(t, "tool", None) not in _TRANSFORM_TARGET_KINDS:
            continue
        params = getattr(t, "params", None) or {}
        lang = params.get("target_language")
        if not lang:
            continue
        scope = str(params["target_output_id"]) if params.get("target_output_id") else None
        if scope not in faced:
            faced[scope] = await _faced_source_languages(
                db, project, scope, chain_births_clips=chain_births_clips
            )
        matched = next(
            (src for src in faced[scope] if src.lower() == str(lang).lower()),
            None,
        )
        if matched is not None:
            raise ValueError(_same_language_message(matched, zh=zh))


async def record_target_output_ids(node_id: UUID, output_ids: list[UUID]) -> None:
    """Record the cross-run DAG edge (which outputs this step consumed) on the
    step's spec — jsonb_set in its own session, same discipline as set_stage."""
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(WorkflowStep)
            .where(WorkflowStep.id == node_id)
            .values(
                spec=func.jsonb_set(
                    WorkflowStep.spec,
                    pg_array(["target_output_ids"]),
                    cast([str(oid) for oid in output_ids], JSONB),
                    True,
                )
            )
        )
        await s.commit()
