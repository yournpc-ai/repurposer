"""RunPlan orchestrator: materialize the plan graph, walk it, settle runs.

Topology is code-determined — the LLM never shapes the graph (ADR-028, task
brief §9). Every WorkflowRun is born here (``create_run``); the worker claims
ready nodes (``jobs.claim_ready_node``) and executes them through
``execute_step``.

Run-level semantics preserved from the retired run_generation:
- "all failed or nothing" — a run only fails when every generation node
  failed/was skipped (partial failures still complete the run);
- run COMPLETED flips the project to REVIEW;
- render nodes never hold a run open (they mirror the render chain, D2).
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import (
    AnswerPayload,
    AssetType,
    IntentSlot,
    ProjectStatus,
    TaskItem,
    WorkflowStatus,
)
from app.models.tables import Asset, Message, Output, WorkflowStep, Project, WorkflowRun
from app.metering import bind_workflow_step
from app.pipeline.derivative_dispatch import derivative_output_types
from app.pipeline.errors import TransientNodeError, user_error_line
from app.pipeline.step_display import ui_lang_of
from app.pipeline.graph import (
    MEDIA,
    NODE_KINDS,
    Requirement,
    generation_node_kinds,
    node_for,
    node_for_output,
    runtime_fanout_kinds,
)
from app.pipeline.recipes import RECIPE_REGISTRY
from app.pipeline.step_context import _estimate_facts
from app.pipeline.tracks import assert_single_writer_per_track
from app.skills import SKILL_REGISTRY, SkillEntry, validate_task_list

logger = structlog.get_logger()

GENERATION_NODE_KINDS = generation_node_kinds()
# Kinds whose terminal state is owned outside the worker topo walk (D2) —
# node-declared (`runtime_fanout`), consumed here so a new fan-out kind needs
# zero kernel edits. The SQL fragment is built from code constants only.
RUNTIME_FANOUT_KINDS = runtime_fanout_kinds()
_RUNTIME_FANOUT_SQL = ", ".join(f"'{k}'" for k in sorted(RUNTIME_FANOUT_KINDS))

# Targeted-regen scopes: the generic "derivative" plus every copy-writer
# output type (node-derived — a new writer package is targetable here with
# zero kernel edits, N-32).
_TARGETED_DERIVATIVE_SCOPES = {"derivative"} | derivative_output_types()


class Suspend(Exception):
    """挂起: a thin checkpoint node parks itself for a human answer (期 4).

    The checkpoint runner raises it after docking the question; execute_step's
    catch branch parks the node in ``waiting`` (options ride in
    ``spec.suspend_payload``) and the run in WAITING_HUMAN. Re-entry is
    queue-based, not call-stack resumption: the answer endpoint writes
    ``spec.answer``, flips the node back to pending and the run back to
    RUNNING, and the claim loop re-runs the runner from the top — whose
    answer branch goes straight to done.
    """

    def __init__(self, payload: dict) -> None:
        super().__init__("suspended")
        self.payload = payload


class TaskSpec(BaseModel):
    """The task book: normalized generation intent (任务书).

    Mirrors GenerateRequest/chat dispatch; stored verbatim on run.context.
    The only request grammar is the skill chain (``tasks``, ADR-043) —
    outputs are the compiled graph's derived projection, never declared.
    Targeted scopes (hook/clip/derivative/render) carry no chain — they
    re-run one node family off ``target_id``.
    """

    target_language: str = "en"
    instruction: str | None = None
    tone_settings: dict | None = None
    # The confirmed persona choice, pinned into run.context at task-book
    # confirmation (the composer persona block → chat first message → pending
    # intent chain). None = resolve per the default-persona chain.
    persona_id: str | None = None
    # Autonomy tier (intent-ask-primitive §2.7): stored verbatim on
    # run.context; the review tier inserts a direction checkpoint between
    # director_understand and director_plan on full runs (期 4).
    autonomy: str = "auto"
    scope: str = "full"
    operation: str = "regenerate"
    target_id: UUID | None = None
    tasks: list[TaskItem] | None = None
    # The UI locale the run was launched under (Accept-Language, pinned at
    # the birthplace): display-layer strings (step summaries, ask chrome)
    # follow it, never the material's language. None on legacy rows → the
    # display layer falls back to project/source language.
    ui_language: str | None = None


def first_task_language(tasks: list[TaskItem] | None) -> str | None:
    """The chain's first language param — the spec-level fallback.

    Language is a per-task param now (``target_language`` on clip
    transforms, ``language`` on the writers); the spec-level field only
    feeds defaults for nodes a task didn't pin.
    """
    for task in tasks or []:
        params = task.params or {}
        lang = params.get("target_language") or params.get("language")
        if isinstance(lang, str) and lang:
            return lang
    return None


class _NodeSpec:
    """Lowering record; ``inputs`` are indices into the lowered list."""
    __slots__ = ("kind", "seq", "inputs", "spec")

    def __init__(self, kind: str, seq: int, inputs: list[int] | None = None, spec: dict | None = None) -> None:
        self.kind = kind
        self.seq = seq
        self.inputs = inputs or []
        self.spec = spec or {}


def slot_step_label(slot: IntentSlot, ui_language: str = "en") -> str | None:
    """Display label distinguishing same-kind sibling steps (per-slot fan-out).

    The label derives from the slot type's node (``NodeBase.label`` — the
    retired slot-type→label map's home): preset as the step's
    spec.summary at materialization so two ``write_post`` nodes (e.g.
    English/German) read differently in the stepper before they run; the
    runner rewrites it with the quantified line + the same tag when done.
    Without a distinguishing tag the label is the node's static task name
    (``NodeBase.label`` never returns None for a registered kind).
    ``ui_language`` is the run's pinned UI locale — the label word follows
    it.
    """
    owner = node_for_output(slot.type)
    if owner is None:
        return None
    return owner.label(slot, ui_language)


def compile_graph(
    task: TaskSpec,
    target_type: str | None = None,
    *,
    add_stills_align: bool = False,
    materialize_profile: str | None = None,
) -> list[_NodeSpec]:
    """Lower a task book into a node topology (pure, code-determined).

    Full scope: ``task.tasks`` (the skill chain, ADR-043) materializes via
    ``_compile_task_list`` — generation skills share one deduped director
    prelude (preprocess → persona_bootstrap ∥ director_understand →
    director_plan); clip-spec consumers without select_clips get the
    compile-injected ``materialize_source`` (whole-source, no LLM picking).
    Targeted:   hook/clip -> [script];
                derivative -> [director_understand -> director_plan -> X_gen];
                render -> [render].

    ``add_stills_align`` (input profile, computed async at the birthplace):
    the no-recording combination — transcript + photos, no video/audio — gets
    an ``align_stills`` node between director_plan and the clips node, so the
    stills branch renders with an estimated caption timeline (RECIPES §4.2).
    """
    if task.tasks is not None:
        return _compile_task_list(
            task,
            add_stills_align=add_stills_align,
            materialize_profile=materialize_profile,
        )

    scope = task.scope or "full"
    if scope == "full":
        raise ValueError("A full-scope run needs a task list (the confirmed chain).")

    if scope in ("hook", "clip"):
        return [
            _NodeSpec(
                "revise_script",
                1,
                spec={
                    "scope": scope,
                    "target_id": str(task.target_id) if task.target_id else None,
                    "instruction": task.instruction,
                    "operation": task.operation,
                },
            )
        ]

    if scope in _TARGETED_DERIVATIVE_SCOPES:
        if not target_type:
            raise ValueError(f"Cannot lower scope={scope} without a target type")
        return [
            _NodeSpec("director_understand", 1),
            _NodeSpec("director_plan", 2, inputs=[0], spec={"target_type": target_type}),
            _NodeSpec(
                node_for_output(target_type).kind,
                3,
                inputs=[1],
                spec={
                    "target_id": str(task.target_id) if task.target_id else None,
                    "target_language": task.target_language,
                    "target_type": target_type,
                },
            ),
        ]

    if scope == "render":
        return [
            _NodeSpec(
                "render",
                1,
                spec={"target_id": str(task.target_id) if task.target_id else None},
            )
        ]

    raise ValueError(f"Targeted scope not implemented: {scope}")


def _compile_task_list(
    task: TaskSpec,
    *,
    add_stills_align: bool = False,
    materialize_profile: str | None = None,
) -> list[_NodeSpec]:
    """Mode②: materialize an LLM-proposed task list into a standard graph.

    Pure, code-determined (CHAT_ARCH §5): the registry adjudicates existence
    and params; topology is derived here — generation skills that need a
    director share one deduped prelude (preprocess → persona_bootstrap ∥
    director_understand → director_plan); modifier skills (needs_director=
    False, e.g. remove_filler / add_music) hang off the clips node when one
    exists, else off the injected materialize_source (whole-source
    materialization, ADR-043), else get empty inputs (= act on the project's
    existing clips). Modifiers are chained in proposal order so two of them
    never edit the same render_spec concurrently. Defaults come from the
    params schemas, never from the LLM.

    ``add_stills_align``: same input-profile injection as mode① — an
    ``align_stills`` node is inserted right before the clips node and wired
    into its inputs (an LLM-proposed align_stills is folded into the
    injection; the runner is idempotent either way).

    ``materialize_profile``: the birthplace-computed whole-source profile
    (``_materialize_profile``) — "media" / "stills" inject materialize_source
    when modifiers exist without select_clips; "existing" leaves them acting
    on the project's clips; None with modifiers and no select_clips rejects.
    """
    entries = validate_task_list(task.tasks or [])  # raises SkillRejected
    if not entries:
        # An empty chain compiles to nothing — reject here, never a vacuous
        # run (the ``tasks is not None`` dispatch in compile_graph routes
        # empty lists here deliberately).
        raise ValueError("The task list is empty — nothing to run.")
    nodes: list[_NodeSpec] = []

    if any(NODE_KINDS[entry.name].needs_director for entry in entries):
        nodes.extend(
            [
                _NodeSpec("preprocess", 1),
                _NodeSpec("persona_bootstrap", 2, inputs=[0]),
                _NodeSpec("director_understand", 3, inputs=[0]),
            ]
        )
        if task.autonomy == "review":
            # Direction checkpoint (期 4, review tier only — the auto tier
            # never inserts one; targeted runs don't either). It parks the
            # run for the user's direction pick between understanding and
            # planning; persona and understanding ride its inputs so the
            # plan node's ordering constraint survives transitively.
            nodes.append(
                _NodeSpec("checkpoint", 4, inputs=[1, 2], spec={"for": "direction"})
            )
            nodes.append(_NodeSpec("director_plan", 5, inputs=[3]))
        else:
            nodes.append(_NodeSpec("director_plan", 4, inputs=[1, 2]))
    director_idx = len(nodes) - 1 if nodes else None

    seq = 10
    skill_node_idx: dict[str, int] = {}
    modifiers: list[tuple[TaskItem, SkillEntry]] = []
    # Per-type ordinals for same-type multi tasks (an English and a German
    # post = two write_post tasks): each generation node's spec carries its
    # task's params as a synthesized slot + its ordinal among its own type —
    # the slot is a compile-time projection of the chain, never a request-
    # layer declaration (outputs-derive, ADR-043). Storyboard alignment and
    # step labels downstream read it unchanged.
    type_ordinals: dict[str, int] = {}
    for item, entry in zip(task.tasks or [], entries, strict=True):
        node_cls = NODE_KINDS[entry.name]
        params = entry.params_model.model_validate(item.params or {}) if entry.params_model else None
        if entry.name == "align_stills":
            # Handled by the input-profile injection below — the LLM naming
            # it explicitly changes nothing (idempotent runner).
            continue
        if not node_cls.needs_director and not node_cls.produces_outputs:
            modifiers.append((item, entry))
            continue
        params_dict = params.model_dump(mode="json", exclude_none=True) if params else {}
        if entry.name == "revise_script":
            assert params is not None
            spec = {
                "scope": params.scope,
                "target_id": params.target_output_id
                or (str(task.target_id) if task.target_id else None),
                "instruction": params.instruction or task.instruction,
                "operation": "revise",
            }
        else:
            slot_index = type_ordinals.get(node_cls.output_type, 0)
            type_ordinals[node_cls.output_type] = slot_index + 1
            slot = {
                "type": node_cls.output_type,
                **{
                    k: v
                    for k, v in params_dict.items()
                    if k in ("count", "focus", "language", "tone_override")
                },
            }
            spec = {
                "target_id": str(task.target_id) if task.target_id else None,
                "target_language": slot.get("language") or task.target_language,
                "target_type": node_cls.output_type,
                "slot": slot,
                "slot_index": slot_index,
            }
            # Preset the sibling-distinguishing label (two write_post nodes,
            # e.g. English/German, must read differently in the stepper
            # before they run) — the runner rewrites it with the quantified
            # line when done.
            label = slot_step_label(
                IntentSlot.model_validate(slot), task.ui_language or "en"
            )
            if label:
                spec["summary"] = label
            if entry.name == "select_clips" and params_dict.get("aspect"):
                spec["aspect"] = params_dict["aspect"]
        inputs = [director_idx] if director_idx is not None else []
        if entry.name == "select_clips" and add_stills_align:
            align_inputs = [director_idx] if director_idx is not None else []
            skill_node_idx["align_stills"] = len(nodes)
            nodes.append(_NodeSpec("align_stills", seq, inputs=align_inputs))
            seq += 1
            inputs = [*inputs, skill_node_idx["align_stills"]]
        skill_node_idx[entry.name] = len(nodes)
        nodes.append(_NodeSpec(entry.name, seq, inputs=inputs, spec=spec))
        seq += 1

    # Whole-source materialization (ADR-043): clip-spec consumers without a
    # select_clips to hang off need an object to act on. The birthplace
    # profile decides: "media" / "stills" inject materialize_source (the
    # stills profile first injects align_stills to estimate the caption
    # timeline; both wire into the modifiers through their `after`
    # declarations below); "existing" leaves the modifiers with empty inputs
    # (= act on the project's clips); no profile = nothing to act on
    # anywhere — reject at compile, not mid-run.
    if modifiers and "select_clips" not in skill_node_idx:
        if materialize_profile in ("media", "stills"):
            # Reuse the director prelude's preprocess when one exists.
            pre_idx = 0 if nodes and nodes[0].kind == "preprocess" else None
            if pre_idx is None:
                pre_idx = len(nodes)
                nodes.append(_NodeSpec("preprocess", seq))
                seq += 1
            mat_inputs = [pre_idx]
            if materialize_profile == "stills":
                skill_node_idx["align_stills"] = len(nodes)
                nodes.append(_NodeSpec("align_stills", seq, inputs=[pre_idx]))
                seq += 1
                mat_inputs.append(skill_node_idx["align_stills"])
            skill_node_idx["materialize_source"] = len(nodes)
            nodes.append(_NodeSpec("materialize_source", seq, inputs=mat_inputs))
            seq += 1
        elif materialize_profile != "existing":
            names = ", ".join(entry.name.replace("_", " ") for _, entry in modifiers)
            raise ValueError(
                f"Nothing for {names} to act on: the chain selects no clips, "
                "the project has no existing clips, and no renderable source "
                "(recording, or transcript + photos) was found."
            )

    # Modifiers run after the nodes named in their `after` constraints (when
    # present in this graph) and after the previous modifier — never in
    # parallel with each other. No edges at all = act on existing clips.
    prev_modifier_idx: int | None = None
    for item, entry in modifiers:
        node_cls = NODE_KINDS[entry.name]
        params = entry.params_model.model_validate(item.params or {}) if entry.params_model else None
        inputs = [skill_node_idx[name] for name in node_cls.after if name in skill_node_idx]
        if prev_modifier_idx is not None:
            inputs.append(prev_modifier_idx)
        prev_modifier_idx = len(nodes)
        spec = params.model_dump(mode="json") if params else {}
        # Sibling-distinguishing tag for the language fan-out (two
        # translate_clip tasks, e.g. DE+FR, must not both read "翻译字幕"
        # while pending) — the same tag the runner's quantified done-line
        # carries; the base name comes from label(), the one builder source.
        lang = spec.get("target_language")
        base = node_cls.label(None, task.ui_language or "en")
        if isinstance(lang, str) and lang and base:
            spec["summary"] = f"{base} · {lang.upper()}"
        nodes.append(_NodeSpec(entry.name, seq, inputs=inputs, spec=spec))
        seq += 1

    return nodes


async def derive_plan_preview(
    db: AsyncSession, project: Project, tasks: list[TaskItem]
) -> list[dict]:
    """The plan card's derived preview (ADR-043): dry-run the task list
    through compile_graph and project the user-facing rows — what this chain
    will MAKE (outputs are a derived projection, never a request field).
    Display vocabulary only: no run is created, nothing is written.

    Row shape: {"type": "video"|"clips"|<writer output_type>, "variant":
    "subs"|"dub"|None, "language"?, "count"?, "bilingual"?}. ``video`` is the
    whole-source materialization row (整条视频); transform rows take their
    base from the upstream they hang off (materialize → video, select_clips
    or existing clips → clips). Raises SkillRejected / ValueError — the
    caller decides the degradation."""
    spec = TaskSpec(tasks=list(tasks))
    profile = await _materialize_profile(db, project, spec)
    nodes = _compile_task_list(spec, materialize_profile=profile)
    materialize_idxs = {i for i, n in enumerate(nodes) if n.kind == "materialize_source"}
    rows: list[dict] = []
    base_row_idx: int | None = None  # the clip producer's row (video/clips)
    for i, ns in enumerate(nodes):
        if ns.kind == "materialize_source":
            base_row_idx = len(rows)
            rows.append({"type": "video"})
            continue
        if ns.kind in ("translate_clip", "dub_clip"):
            # Fork = a new derived row (originals coexist); morph on a
            # materialized source annotates the base row itself (the whole
            # video BECOMES the subtitled/dubbed version); morph on existing
            # clips previews as its own row (the clips get the treatment).
            variant = "subs" if ns.kind == "translate_clip" else "dub"
            fork = bool((ns.spec or {}).get("fork"))
            hangs_on_materialize = any(j in materialize_idxs for j in ns.inputs)
            if not fork and hangs_on_materialize and base_row_idx is not None:
                rows[base_row_idx] = {
                    **rows[base_row_idx],
                    "variant": variant,
                    "language": (ns.spec or {}).get("target_language"),
                    "bilingual": bool((ns.spec or {}).get("bilingual")),
                }
            else:
                rows.append(
                    {
                        "type": "video" if hangs_on_materialize else "clips",
                        "variant": variant,
                        "language": (ns.spec or {}).get("target_language"),
                        "bilingual": bool((ns.spec or {}).get("bilingual")),
                    }
                )
            continue
        node_cls = NODE_KINDS.get(ns.kind)
        if node_cls is None or not node_cls.produces_outputs or not node_cls.output_type:
            continue
        slot = (ns.spec or {}).get("slot") or {}
        if ns.kind == "select_clips":
            base_row_idx = len(rows)
        rows.append(
            {
                "type": node_cls.output_type,
                "language": slot.get("language"),
                "count": slot.get("count"),
            }
        )
    return rows


async def _check_birthplace_requires(
    db: AsyncSession, project: Project, task: "TaskSpec"
) -> None:
    """Birthplace ∀-check (AGENT_ARCH §4.2: 校验 = ∀requires) — the chain's
    skills carry their nodes' ``requires`` declarations (the clips gate is
    SelectClips' own declaration, not a kernel special case).
    Raises ValueError; request handlers translate to 422."""
    needs: dict[str, tuple[Requirement, list[str]]] = {}
    for entry in validate_task_list(task.tasks or []):  # raises SkillRejected
        for req in NODE_KINDS[entry.name].requires:
            owners = needs.setdefault(req.key, (req, []))[1]
            owners.append(entry.name.replace("_", " "))
    has_clips_slot = any(t.skill == "select_clips" for t in (task.tasks or []))
    for key in sorted(needs):
        req, owners = needs[key]
        if await req.missing(db, project):
            # The clips-media 422 keeps its own copy: it names the way out
            # ("deselect clips") in task-book terms, not skill terms.
            if key == MEDIA.key and has_clips_slot:
                raise ValueError(CLIPS_NEED_MEDIA)
            raise ValueError(
                f"Missing required input: {key} (needed by: {', '.join(owners)})"
            )


# Birthplace rejection copy for the clips-media gate — fired by the ∀-check
# when a clips slot's MEDIA requirement fails (the knowledge is the node's;
# only this user-facing way-out copy lives here).
CLIPS_NEED_MEDIA = (
    "Clips need a video, audio, or image source. Upload one or deselect clips."
)


async def _needs_stills_alignment(db: AsyncSession, project: Project, task: TaskSpec) -> bool:
    """Input profile for the no-recording path (RECIPES §4.2).

    True only for the exact combination: clips requested + NO video/audio
    recording on the project + a transcript with text + photos/slides to back
    the visual. Any recording present -> the existing media chain wins; no
    images -> the clips-media gate already rejects. Computed once here and
    passed into compile_graph, which stays pure.
    """
    clips_requested = any(t.skill == "select_clips" for t in (task.tasks or []))
    if not clips_requested:
        return False
    recording = await db.execute(
        select(Asset.id)
        .where(
            Asset.project_id == project.id,
            Asset.type.in_([AssetType.VIDEO, AssetType.AUDIO]),
            Asset.file_url.isnot(None),
        )
        .limit(1)
    )
    if recording.scalar_one_or_none() is not None:
        return False
    transcript = await db.execute(
        select(Asset.id)
        .where(
            Asset.project_id == project.id,
            Asset.type == AssetType.TRANSCRIPT,
            Asset.extracted_text.isnot(None),
        )
        .limit(1)
    )
    if transcript.scalar_one_or_none() is None:
        return False
    images = await db.execute(
        select(Asset.id)
        .where(
            Asset.project_id == project.id,
            Asset.type.in_([AssetType.IMAGE, AssetType.SLIDES]),
            Asset.file_url.isnot(None),
        )
        .limit(1)
    )
    return images.scalar_one_or_none() is not None


async def _materialize_profile(db: AsyncSession, project: Project, task: TaskSpec) -> str | None:
    """Input profile for whole-source materialization (ADR-043).

    Only meaningful for a transform-only chain — clip-spec consumers present
    (skills whose ``after`` names materialize_source, a node declaration, no
    parallel map) and no select_clips: "existing" = the project already has
    clips for the modifiers to act on (no injection); "media" = a
    video/audio recording to materialize whole; "stills" = the no-recording
    combination (align_stills estimates the timeline before materialize);
    None = nothing to act on — the compile rejects. Any other chain shape
    returns None (no injection applies). Computed once here and passed into
    compile_graph, which stays pure.
    """
    tasks = task.tasks or []
    consumes_clips = any(
        t.skill in NODE_KINDS
        and "materialize_source" in (NODE_KINDS[t.skill].after or ())
        for t in tasks
    )
    if not consumes_clips or any(t.skill == "select_clips" for t in tasks):
        return None
    clips = await db.execute(
        select(Output.id)
        .where(Output.project_id == project.id, Output.type == "clip")
        .limit(1)
    )
    if clips.scalar_one_or_none() is not None:
        return "existing"
    recording = await db.execute(
        select(Asset.id)
        .where(
            Asset.project_id == project.id,
            Asset.type.in_([AssetType.VIDEO, AssetType.AUDIO]),
            Asset.file_url.isnot(None),
        )
        .limit(1)
    )
    if recording.scalar_one_or_none() is not None:
        return "media"
    transcript = await db.execute(
        select(Asset.id)
        .where(
            Asset.project_id == project.id,
            Asset.type == AssetType.TRANSCRIPT,
            Asset.extracted_text.isnot(None),
        )
        .limit(1)
    )
    if transcript.scalar_one_or_none() is None:
        return None
    images = await db.execute(
        select(Asset.id)
        .where(
            Asset.project_id == project.id,
            Asset.type.in_([AssetType.IMAGE, AssetType.SLIDES]),
            Asset.file_url.isnot(None),
        )
        .limit(1)
    )
    return "stills" if images.scalar_one_or_none() is not None else None


async def create_run(
    db: AsyncSession,
    project: Project,
    task: TaskSpec,
) -> WorkflowRun:
    """Create a run and materialize its plan graph. THE ONLY WorkflowRun birthplace.

    Every entry constraint rejects here, once — targeted-scope validity and
    the birthplace ∀-check (the chain skills' requires, all node-declared) —
    so the entry points (/generate, the task_book start answer, chat
    dispatch) only assemble the TaskSpec. Raises ValueError; request handlers
    translate to 422, chat dispatch degrades to an ask-back.

    Flush-only — the caller commits at the request boundary, so the run, the
    answer that started it, and the project state land in ONE transaction
    (the run only becomes claimable by the worker on commit).
    """
    # Pin the requesting browser's locale into the task book (stored verbatim
    # on run.context below) — the worker process has no request context, so
    # display strings read the pinned value off the run.
    if task.ui_language is None:
        from app.ui_locale import current_ui_language  # deferred: import cycle

        task.ui_language = current_ui_language()
    target_type: str | None = None
    if task.scope in _TARGETED_DERIVATIVE_SCOPES and task.target_id is not None:
        target = await db.get(Output, task.target_id)
        if target is None or target.project_id != project.id:
            raise ValueError("Target output not found")
        if node_for_output(target.type) is None or target.type == "clips":
            raise ValueError(f"Target output type {target.type} is not regenerable")
        target_type = target.type

    # One ∀-check for every birth constraint (AGENT_ARCH §4.2) — the chain's
    # skills' requires, all node-declared. Unconditional: targeted re-renders
    # read the same source media, so no scope is exempt.
    await _check_birthplace_requires(db, project, task)

    run = WorkflowRun(
        project_id=project.id,
        status=WorkflowStatus.PENDING,
        context=task.model_dump(mode="json"),
        progress=0,
    )
    db.add(run)
    await db.flush()

    node_specs = compile_graph(
        task,
        target_type,
        add_stills_align=await _needs_stills_alignment(db, project, task),
        materialize_profile=await _materialize_profile(db, project, task),
    )
    # 一轨一写者 (ADR-044): within one run a clip-spec track takes at most one
    # non-fork morph writer; a collision rejects HERE (ValueError → 422 at the
    # entry points), never a runtime merge.
    assert_single_writer_per_track(
        ((ns.kind, ns.spec) for ns in node_specs),
        lambda kind: bool(NODE_KINDS[kind].produces_outputs),
    )
    # 报价 = 图 fold 的存储侧 (P4, N-34): each compile-time node quotes
    # itself from the shared facts; an unquotable node keeps NULL (未估价).
    estimate_facts = await _estimate_facts(db, project)
    nodes: list[WorkflowStep] = []
    for ns in node_specs:
        spec = dict(ns.spec or {})
        if "summary" not in spec:
            # Builder-written task name (the task list's pending-row text —
            # label() carries the static name, or the slot-tagged sibling
            # word): every node presets its spec.summary here, never a
            # frontend kind dictionary. The runner rewrites it with the
            # quantified line when done.
            label = NODE_KINDS[ns.kind].label(
                IntentSlot.model_validate(spec["slot"])
                if isinstance(spec.get("slot"), dict)
                else None,
                task.ui_language or "en",
            )
            if label:
                spec["summary"] = label
        node = WorkflowStep(
            run_id=run.id,
            kind=ns.kind,
            status="pending",
            seq=ns.seq,
            spec=spec,
            estimate=NODE_KINDS[ns.kind].estimate(
                {
                    **estimate_facts,
                    "spec": ns.spec,
                    "input_kinds": [node_specs[i].kind for i in ns.inputs],
                }
            ),
        )
        db.add(node)
        nodes.append(node)
    await db.flush()  # assign ids
    # Resolve input indices to node ids.
    for node, ns in zip(nodes, node_specs, strict=True):
        node.inputs = [str(nodes[i].id) for i in ns.inputs]
    await db.flush()
    logger.info(
        "run_materialized",
        run_id=str(run.id),
        nodes=len(node_specs),
        scope=task.scope,
    )
    return run


async def execute_step(node_id: UUID) -> None:
    """Execute one claimed node; settle terminal state + downstream + the run.

    Never raises — failures land on the node row (and cascade-skip downstream).
    """
    run_id: UUID | None = None
    try:
        async with AsyncSessionLocal() as db:
            node = await db.get(WorkflowStep, node_id)
            if node is None or node.status not in ("pending", "running"):
                return
            run_id = node.run_id
            if node.status == "pending":
                node.status = "running"
                node.started_at = datetime.now(UTC)
                node.attempt = (node.attempt or 0) + 1
            run = await db.get(WorkflowRun, node.run_id)
            if run is not None and run.status == WorkflowStatus.PENDING:
                run.status = WorkflowStatus.RUNNING
            await db.commit()

        try:
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                run = await db.get(WorkflowRun, node.run_id)
                project = await db.get(Project, run.project_id)
                executor = NODE_KINDS[node.kind]
                with bind_workflow_step(node.id):
                    output_ids = await executor.run(db, run, node, project)
                node.output_refs = [str(oid) for oid in (output_ids or [])]
                if NODE_KINDS[node.kind].runtime_fanout:
                    # The render chain owns this node's terminal state (D2):
                    # back to pending so the render-status claim mirror moves it.
                    node.status = "pending"
                    node.finished_at = None
                else:
                    node.status = "done"
                    node.finished_at = datetime.now(UTC)
                    # Clear any transient note from earlier attempts (W3) —
                    # a done node carries no error.
                    node.error = None
                await db.commit()
                logger.info("workflow_step_done", node_id=str(node_id), kind=node.kind)
        except Suspend as s:
            # Checkpoint park (期 4): node → waiting with the derived options
            # in spec.suspend_payload, run → WAITING_HUMAN. The question was
            # already docked by the runner in its own session (committed
            # before raising), so nothing here rolls back. No cascade — the
            # downstream nodes simply stay pending behind the waiting one.
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                node.status = "waiting"
                node.spec = {**(node.spec or {}), "suspend_payload": s.payload}
                run = await db.get(WorkflowRun, node.run_id)
                if run is not None:
                    run.status = WorkflowStatus.WAITING_HUMAN
                await db.commit()
                logger.info("workflow_step_waiting", node_id=str(node_id), kind=node.kind)
        except Exception as e:  # noqa: BLE001 — record any failure on the node
            logger.error("workflow_step_failed", node_id=str(node_id), error=str(e))
            async with AsyncSessionLocal() as db:
                node = await db.get(WorkflowStep, node_id)
                # Step-level retry (agent-loop-upgrade W3): a TransientNodeError
                # within the kind's retry budget resets the node to pending —
                # the worker's next tick is the backoff, downstream is NOT
                # cascade-skipped. Deterministic failures fail fast as before.
                # The budget lives on the node class (NodeBase.retries).
                executor = node_for(node.kind)
                budget = executor.retries if executor is not None else 0
                if isinstance(e, TransientNodeError) and (node.attempt or 0) <= budget:
                    node.status = "pending"
                    node.error = f"transient attempt {node.attempt}: {str(e)[:500]}"
                    node.finished_at = None
                    await db.commit()
                    logger.info(
                        "workflow_step_retry",
                        node_id=str(node_id),
                        kind=node.kind,
                        attempt=node.attempt,
                    )
                    return
                node.status = "failed"
                # node.error is USER copy — the failed step row's tail. Bake the
                # localized line (errors.USER_ERROR_LINES, the run's pinned UI
                # locale — same bake-at-write discipline as step summaries);
                # the raw exception stays in the structlog event above, never
                # in the DB the UI reads.
                run = await db.get(WorkflowRun, node.run_id)
                project = await db.get(Project, run.project_id) if run else None
                node.error = (
                    user_error_line(e, ui_lang_of(run, project))
                    if run is not None
                    else user_error_line(e)
                )
                node.finished_at = datetime.now(UTC)
                await db.commit()
                await _cascade_skip(db, node)
                await db.commit()
    finally:
        if run_id is not None:
            await maybe_finalize_run(run_id)


async def _cascade_skip(
    db: AsyncSession, failed_node: WorkflowStep, *, reason: str | None = None
) -> None:
    """Transitively mark downstream pending nodes as skipped.

    ``reason`` overrides the failure line — the checkpoint bail cascade is a
    graceful exit (#5), so its skipped children read "user bailed", never
    "upstream failed".
    """
    frontier = [failed_node.id]
    while frontier:
        current = frontier.pop()
        result = await db.execute(
            select(WorkflowStep).where(
                WorkflowStep.run_id == failed_node.run_id,
                WorkflowStep.status.in_(["pending", "running"]),
                WorkflowStep.inputs.contains([str(current)]),
            )
        )
        for child in result.scalars():
            child.status = "skipped"
            child.error = reason or f"upstream node {current} failed"
            child.finished_at = datetime.now(UTC)
            frontier.append(child.id)


async def resume_waiting_checkpoint(
    db: AsyncSession, run: WorkflowRun, answer: dict
) -> WorkflowStep | None:
    """answer = resume: write the AnswerPayload dump into the waiting
    checkpoint's spec, flip the node back to pending and the run back to
    RUNNING — the claim loop re-executes the thin node, whose spec.answer
    branch goes straight to done. Idempotent: no waiting checkpoint → None
    (already resumed or bailed). Flush-only; the caller commits."""
    result = await db.execute(
        select(WorkflowStep).where(
            WorkflowStep.run_id == run.id,
            WorkflowStep.kind == "checkpoint",
            WorkflowStep.status == "waiting",
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        return None
    node.spec = {**(node.spec or {}), "answer": answer}
    node.status = "pending"
    node.started_at = None
    if run.status == WorkflowStatus.WAITING_HUMAN:
        run.status = WorkflowStatus.RUNNING
    logger.info("checkpoint_resumed", run_id=str(run.id), node_id=str(node.id))
    return node


async def bail_waiting_checkpoint(
    db: AsyncSession, run: WorkflowRun
) -> WorkflowStep | None:
    """Bail path (期 4): node done with ``spec.bailed`` + downstream cascade-
    skipped with the non-failure reason (#5). The run itself settles
    COMPLETED via maybe_finalize_run once the caller commits — the bailed
    checkpoint's summary line ("Bailed by user") is the user-abort note in
    the aggregated run summary. Idempotent like resume. Flush-only."""
    result = await db.execute(
        select(WorkflowStep).where(
            WorkflowStep.run_id == run.id,
            WorkflowStep.kind == "checkpoint",
            WorkflowStep.status == "waiting",
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        return None
    node.spec = {**(node.spec or {}), "bailed": True, "summary": "Bailed by user"}
    node.status = "done"
    node.finished_at = datetime.now(UTC)
    await _cascade_skip(db, node, reason="user bailed")
    logger.info("checkpoint_bailed", run_id=str(run.id), node_id=str(node.id))
    return node


async def maybe_finalize_run(run_id: UUID) -> None:
    """Settle a run once no non-render node is active.

    Render nodes are excluded from the active/failure tally (they mirror the
    render chain and never hold a run open — same semantics as the retired
    orchestration, where renders continued after the run completed).
    """
    async with AsyncSessionLocal() as db:
        run = await db.get(
            WorkflowRun, run_id, with_for_update=True
        )
        if run is None or run.status in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
        ):
            return

        nodes = list(
            (await db.execute(select(WorkflowStep).where(WorkflowStep.run_id == run_id)))
            .scalars()
            .all()
        )
        total = len(nodes)
        settled = sum(1 for n in nodes if n.status in ("done", "failed", "skipped"))
        run.progress = int(settled / total * 100) if total else 100

        active = [
            n
            for n in nodes
            # waiting counts as active: a checkpoint parked for a human answer
            # must never let the run settle (期 4).
            if n.status in ("pending", "running", "waiting") and n.kind not in RUNTIME_FANOUT_KINDS
        ]
        if active:
            await db.commit()
            return

        gen_nodes = [n for n in nodes if n.kind in GENERATION_NODE_KINDS]
        any_failed = any(n.status == "failed" for n in nodes)
        gen_failed_like = [n for n in gen_nodes if n.status in ("failed", "skipped")]

        if any_failed and (not gen_nodes or len(gen_failed_like) == len(gen_nodes)):
            first_error = next((n.error for n in nodes if n.status == "failed"), None)
            run.status = WorkflowStatus.FAILED
            run.error = first_error or "All outputs failed"
        else:
            run.status = WorkflowStatus.COMPLETED
            run.error = None
            project = await db.get(Project, run.project_id)
            if project is not None:
                project.status = ProjectStatus.REVIEW
                project.updated_at = datetime.now(UTC)
        run.progress = 100
        await db.commit()
        logger.info(
            "run_finalized",
            run_id=str(run_id),
            status=run.status.value,
            nodes=total,
        )


async def expire_stale_checkpoints(older_than: timedelta | None = None) -> int:
    """Auto-answer long-parked checkpoints with their default option.

    Expiry semantics = the review tier degrades to best-judgment completion
    after the TTL (the leave-note promise: 离开不中断) — never a bail, never
    a permanent park. The answer carries the machine marker
    ``answer.text="expired"`` (same pattern as ``superseded``); the default
    option has no argument id, so director_plan injects no direction —
    exactly the auto-tier behavior. The message UPDATE is guarded by
    ``answer IS NULL``: a user answer racing the sweep always wins, and
    ``resume_waiting_checkpoint`` is itself idempotent. Returns the number
    of checkpoints expired (0 is the common, silent case).
    """
    ttl = (
        older_than
        if older_than is not None
        else timedelta(seconds=settings.checkpoint_expiry_seconds)
    )
    cutoff = datetime.now(UTC) - ttl
    expired = 0
    async with AsyncSessionLocal() as db:
        nodes = list(
            (
                await db.execute(
                    select(WorkflowStep).where(
                        WorkflowStep.kind == "checkpoint",
                        WorkflowStep.status == "waiting",
                        WorkflowStep.started_at < cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        for node in nodes:
            payload = (node.spec or {}).get("suspend_payload") or {}
            message_id = payload.get("question_message_id")
            default = next(
                (
                    o
                    for o in payload.get("options") or []
                    if o.get("argument_id") is None
                ),
                None,
            )
            if not message_id or default is None:
                logger.warning(
                    "checkpoint_expiry_skipped_corrupt_payload", node_id=str(node.id)
                )
                continue
            answer = AnswerPayload(
                kind="option",
                option_id=default["id"],
                text="expired",
                answered_at=datetime.now(UTC),
            ).model_dump(mode="json")
            settled_id = await db.scalar(
                update(Message)
                .where(Message.id == UUID(str(message_id)), Message.answer.is_(None))
                .values(answer=answer)
                .returning(Message.id)
            )
            if settled_id is None:
                continue  # the user answered between the scan and this write
            run = await db.get(WorkflowRun, node.run_id)
            if run is not None:
                await resume_waiting_checkpoint(db, run, answer)
            await db.commit()
            expired += 1
            logger.info(
                "checkpoint_expired", node_id=str(node.id), run_id=str(node.run_id)
            )
    return expired


async def finalize_stuck_runs() -> None:
    """Finalize RUNNING runs whose nodes are all settled (crash recovery)."""
    async with AsyncSessionLocal() as db:
        run_ids = (
            await db.execute(
                text(
                    f"""
                    SELECT r.id FROM workflow_runs r
                    WHERE r.status = 'RUNNING'
                      AND NOT EXISTS (
                        SELECT 1 FROM workflow_steps pn
                        WHERE pn.run_id = r.id
                          AND pn.status IN ('pending', 'running', 'waiting')
                          AND pn.kind NOT IN ({_RUNTIME_FANOUT_SQL})
                      )
                    """
                )
            )
        ).scalars().all()
    for rid in run_ids:
        await maybe_finalize_run(rid)


# ---- startup self-check (AGENT_ARCH §10) ------------------------------------


def _recipe_adds_stills(input_types: set[str]) -> bool:
    """The recipe's input profile (its declared input_slots) answers what
    ``_needs_stills_alignment`` answers from real assets at the birthplace:
    no recording + a transcript + images → the compiled graph carries an
    align_stills node."""
    return (
        "video" not in input_types
        and "audio" not in input_types
        and "transcript" in input_types
        and bool({"images", "slides"} & input_types)
    )


def assert_runners_registered() -> None:
    """Startup self-check, three parts (AGENT_ARCH §10):

    1. registry ↔ node consistency: every non-seat skill entry has a node in
       ``NODE_KINDS`` under the same name (N-35), and every skill-package
       node has an entry (internal crew — ``app.pipeline.*`` — never enters
       the proposal space by design). Output types are unique across nodes —
       ``node_for_output`` routing depends on it (N-32: one producer per type).
    2. node → agent references exist: every agent a node declares (its
       ``agents`` tuple, plus Agent-typed class attributes like the writers'
       ``writer``) is collected in the ``AGENTS`` roster.
    3. recipe flow reconciliation (对账 = ⊆): every curated recipe flow key
       names a kind the recipe's own preset compiles to (``compile_graph``
       is pure — compiled and compared directly; runtime fan-out kinds —
       render, D2 — count as present).
    4. track registry (ADR-044): every ClipSpec top-level field is owned by
       exactly one registered track (and op ``writes`` stay inside the
       partition); a phantom track proves the consumers (bake seam /
       addressing / compliance / pricing) fold with zero consumer changes.
    """
    for entry in SKILL_REGISTRY.values():
        if not entry.seat and entry.name not in NODE_KINDS:
            raise RuntimeError(
                f"Skill '{entry.name}': no node registered under that name"
            )
    for node in NODE_KINDS.values():
        if (
            not type(node).__module__.startswith("app.pipeline.")
            and not node.internal
            and node.kind not in SKILL_REGISTRY
        ):
            raise RuntimeError(
                f"Node '{node.kind}' ({type(node).__module__}): no SKILL_REGISTRY entry"
            )
    output_owners: dict[str, str] = {}
    for node in NODE_KINDS.values():
        if node.output_type is None:
            continue
        owner = output_owners.get(node.output_type)
        if owner is not None:
            raise RuntimeError(
                f"Output type '{node.output_type}' claimed by both "
                f"'{owner}' and '{node.kind}'"
            )
        output_owners[node.output_type] = node.kind

    from app.agents.base import AGENTS, Agent  # deferred: metering-free leaf

    for node in NODE_KINDS.values():
        refs = list(node.agents) + [
            v for v in vars(type(node)).values() if isinstance(v, Agent)
        ]
        for agent in refs:
            if AGENTS.get(agent.name) is not agent:
                raise RuntimeError(
                    f"Node '{node.kind}': agent '{agent.name}' not in the AGENTS roster"
                )

    for recipe_id, entry in RECIPE_REGISTRY.items():
        if not entry.flow:
            continue
        input_types = {s.type for s in entry.input_slots}
        add_stills = _recipe_adds_stills(input_types)
        # The recipe's declared inputs answer what `_materialize_profile`
        # answers from real assets at the birthplace: a recording → media;
        # transcript + images → stills; anything else → no injection.
        materialize = (
            "media"
            if {"video", "audio"} & input_types
            else ("stills" if add_stills else None)
        )
        compiled = {
            ns.kind
            for ns in compile_graph(
                TaskSpec(tasks=entry.tasks),
                add_stills_align=add_stills,
                materialize_profile=materialize,
            )
        } | runtime_fanout_kinds()
        missing = [step.key for step in entry.flow if step.key not in compiled]
        if missing:
            raise RuntimeError(
                f"Recipe '{recipe_id}': flow keys missing from the compiled graph: {missing}"
            )

    from app.pipeline.tracks import assert_phantom_track, assert_track_registry

    assert_track_registry()
    assert_phantom_track()
