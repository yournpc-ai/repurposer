"""Graph kernel (ADR-039 P2): the NodeBase protocol + the NODE_KINDS table.

Every plan-graph node is a declared ``NodeBase`` instance — the kernel's only
vocabulary. A node self-describes: ``kind`` (unique key; a skill node's kind
IS the skill name, N-35), the class attributes below, and ``run`` (the sole
required method). The kernel degrades to graph algorithms over these
declarations (AGENT_ARCH §4.2): execution = topo walk, validation =
∀``requires``, reconciliation = recipe flow keys ⊆ compiled kind set,
quotation = fold (P4).

``NODE_KINDS`` self-populates: a concrete subclass (one that declares
``kind``) registers a singleton instance at class-creation time. The import
that completes the table is the registry's door — ``app/skills/__init__.py``
imports the internal crew (``pipeline/node_runners``) and every skill
package; this module itself imports no concrete node (no cycles).

Derived views (``known_output_types`` / ``node_for_output`` /
``slot_default_counts`` / …) are computed from the table — the retired
parallel maps (output→kind, slot-type→label, count limits…) have no home
anywhere else (prohibition: no parallel maps).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AssetType, IntentSlot
from app.models.tables import Asset, Persona, Project
from app.pipeline.step_display import slot_tag


# ---- birthplace requirements ------------------------------------------------


class Requirement:
    """One birthplace-gate input (create_run ∀-check, AGENT_ARCH §4.2).

    ``key`` is the error-message token ("media" / "transcript" / …); the check
    itself is the node's own knowledge (N-35: no parallel kernel-side table).
    """

    key: str = ""

    async def missing(self, db: AsyncSession, project: Project) -> bool:
        raise NotImplementedError


class _MediaRequirement(Requirement):
    key = "media"

    async def missing(self, db: AsyncSession, project: Project) -> bool:
        return await media_missing(db, project.id)


async def media_missing(db: AsyncSession, project_id) -> bool:
    """The single renderable-media predicate (VIDEO / AUDIO / IMAGE / SLIDES
    with bytes) — every consumer (birthplace ∀-check, chat plan-path
    clarification reason) reads this one definition."""
    result = await db.execute(
        select(Asset.id)
        .where(
            Asset.project_id == project_id,
            Asset.type.in_(
                [AssetType.VIDEO, AssetType.AUDIO, AssetType.IMAGE, AssetType.SLIDES]
            ),
            Asset.file_url.isnot(None),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is None


class _TranscriptRequirement(Requirement):
    key = "transcript"

    async def missing(self, db: AsyncSession, project: Project) -> bool:
        # Mirrors the consumption rule (platform/project_context.py):
        # documents land in extracted_text, ASR lands in transcript /
        # meta.words — any of the three satisfies a text input.
        result = await db.execute(
            select(Asset.id)
            .where(
                Asset.project_id == project.id,
                or_(
                    Asset.transcript.isnot(None),
                    Asset.extracted_text.isnot(None),
                    Asset.meta["words"].isnot(None),
                ),
            )
            .limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return False
        # "Transcript" means words to work with — and words-in-waiting count:
        # a text-typed asset with bytes yields them at extraction, ASR-able
        # media yields them at preprocess (the claim gate holds the run until
        # asset processing finishes). Photos alone do NOT qualify.
        derivable = await db.execute(
            select(Asset.id)
            .where(
                Asset.project_id == project.id,
                Asset.type.in_(
                    [
                        AssetType.TRANSCRIPT,
                        AssetType.PAST_MATERIAL,
                        AssetType.VIDEO,
                        AssetType.AUDIO,
                    ]
                ),
                Asset.file_url.isnot(None),
            )
            .limit(1)
        )
        return derivable.scalar_one_or_none() is None


class _PersonaPhotoRequirement(Requirement):
    key = "persona_photo"

    async def missing(self, db: AsyncSession, project: Project) -> bool:
        persona = (
            await db.get(Persona, project.persona_id) if project.persona_id else None
        )
        return persona is None or not persona.avatar_url


class _VoiceprintRequirement(Requirement):
    key = "voiceprint"

    async def missing(self, db: AsyncSession, project: Project) -> bool:
        if not project.persona_id:
            return True
        result = await db.execute(
            select(Asset.id)
            .where(
                Asset.persona_id == project.persona_id,
                Asset.type == AssetType.VOICE_SAMPLE,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is None


MEDIA = _MediaRequirement()
TRANSCRIPT = _TranscriptRequirement()
PERSONA_PHOTO = _PersonaPhotoRequirement()
VOICEPRINT = _VoiceprintRequirement()


# ---- the node protocol ------------------------------------------------------


class NodeBase:
    """The kernel's only node protocol (AGENT_ARCH §4.1).

    Class attributes are the declaration; ``run`` is the sole required
    method. Instances are stateless singletons living in ``NODE_KINDS``.
    """

    # —— 类属性声明 ——
    kind: str = ""  # unique key; a skill node's kind IS the skill name (N-35)
    output_type: str | None = None  # producer nodes only (outputs extensibility seat, N-32)
    slot_label: str | None = None  # the output type's display word ("Clips")
    slot_label_zh: str | None = None  # its Chinese form ("切片") — step lines follow the UI locale
    # The step's static task name (declarative — no "正在…"), en/zh. Preset as
    # the step's creation-time spec.summary by the graph builder (label()): the
    # task list's pending-row text is builder-written, never a frontend
    # kind→copy dictionary. A future custom-graph builder (user-defined steps)
    # writes the same field — the frontend reader never changes.
    task_name: str | None = None
    task_name_zh: str | None = None
    after: tuple[str, ...] = ()  # topology constraint (modifier ordering)
    needs_director: bool = False  # needs the director prelude (preprocess→persona∥understand→plan)
    retries: int = 0  # step-level transient retry budget
    produces_outputs: bool = False  # counts as a generation node at run settle
    count_default: int | None = None  # slot count default (None = no count)
    count_limits: tuple[int, int] | None = None  # slot count bounds (birthplace C3)
    requires: tuple[Requirement, ...] = ()  # birthplace gate inputs
    agents: tuple[Any, ...] = ()  # declared agent references (startup self-check)
    runtime_fanout: bool = False  # may materialize outside compile (render, D2)
    # Internal topology node (ADR-043): compile-injected, never a registered
    # skill — users never say its name (materialize_source is the whole-
    # source materialization, the transform chain's implied object). The
    # startup self-check exempts internal nodes from the registry-membership
    # requirement (same standing as the app.pipeline.* crew, declared here
    # because the class lives in its skill package for cohesion).
    internal: bool = False
    # Canvas 渲染单元 (2026-08-12 ADR-041 D6 修订, 与 label() 同哲学——节点类
    # 自描述; 2026-08-19 名词节点收窄): the results canvas renders NOUN nodes
    # only — 素材 / 文本 (任务书 = the "plan" key, the only live grant) / 产物.
    # Process verbs never get a card: each is an ATTRIBUTE of its product
    # (the translate_clip 2026-08-15 precedent generalized — select_clips /
    # dub / add_music all folded). ``canvas_group`` returns the node's
    # artifact key; steps sharing a key within one run merge into ONE canvas
    # node (director's understand+interrupt+plan = the single "plan" card).
    # None = fold into the 过程脊 group node (intervention = click the
    # product, or the expanded spine's step pill via @workflow_step).
    # ``canvas_hidden`` = never a node at all — the step's state projects
    # onto the product card in place (render is 1:1 with its clip).
    # Folding/projection is a VIEW behavior — the step rows stay full (cost /
    # rerun / lineage rely on them).
    canvas_hidden: bool = False

    def canvas_group(self, node: Any) -> str | None:
        return None

    def canvas_text(self, node: Any) -> str | None:
        """The canvas node's body copy (the card shows it verbatim). Default
        None = the surface falls back to the step's summary line."""
        return None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        kind = cls.__dict__.get("kind")
        if kind:
            if kind in NODE_KINDS:
                raise RuntimeError(f"Duplicate node kind: {kind}")
            NODE_KINDS[kind] = cls()

    # —— 方法（run 唯一必实现，其余有默认）——
    async def run(
        self, db: AsyncSession, run: Any, node: Any, project: Project
    ) -> list[UUID]:
        """Execute the node; return the produced output-row ids."""
        raise NotImplementedError

    def estimate(self, ctx: dict) -> dict | None:
        """Self-quotation (P4, N-34): mechanical exact units / agent token
        ranges / free zeros. The estimate JSON is uniform and fold-friendly::

            {"prompt_tokens": [low, high],
             "completion_tokens": [low, high],
             "units": {"tts_chars": n, "render_seconds": s, …}}

        ``ctx`` keys (assembled once per ``create_run`` —
        ``pipeline/step_context._estimate_facts``): ``spec`` (the node's
        compile spec), ``input_kinds`` (upstream kinds, same run),
        ``text_chars`` / ``text_count`` / ``media_count`` /
        ``persona_exists`` / ``voice_clone_needed`` / ``clips`` (existing
        renderable clips: caption chars + seconds) / ``output_seconds``.
        None = unquotable at compile time (e.g. a dub fan-out whose clips
        do not exist yet) — the row keeps NULL (未估价).
        """
        return None

    def label(self, slot: IntentSlot | None, ui_language: str = "en") -> str | None:
        """Display name preset as the step's creation-time summary — run
        progress graph and step list share this one source. With a slot tag:
        "{output word} · {tag}" so same-kind siblings read differently before
        they run. Without: the static ``task_name`` (declarative). ``None``
        only when the class declares neither — legacy/unknown kinds then fall
        back to the raw kind string. ``ui_language`` is the run's pinned UI
        locale: the label word follows it, never the material's language."""
        zh = ui_language.startswith("zh")
        name = (self.task_name_zh if zh and self.task_name_zh else None) or self.task_name
        tag = slot_tag(slot)
        if tag is not None:
            word = (
                (self.slot_label_zh if zh and self.slot_label_zh else None)
                or self.slot_label
                or name
            )
            return f"{word or self.kind} · {tag}"
        return name

    async def reuse(self, *args: Any, **kwargs: Any) -> UUID | None:
        """Idempotent-reuse predicate (asset-hash class): a hit returns the
        earlier row's id — the node costs nothing; a miss falls through to
        ``run``. First case: ``director_understand``."""
        return None


NODE_KINDS: dict[str, NodeBase] = {}


# ---- derived views (no parallel maps — everything computes off the table) ---


def node_for(kind: str) -> NodeBase | None:
    return NODE_KINDS.get(kind)


def known_output_types() -> frozenset[str]:
    """The requestable output types (producer nodes' ``output_type``)."""
    return frozenset(n.output_type for n in NODE_KINDS.values() if n.output_type)


def node_for_output(output_type: str) -> NodeBase | None:
    """The producer node owning an output type (outputs = skill attribute, N-32)."""
    for n in NODE_KINDS.values():
        if n.output_type == output_type:
            return n
    return None


def slot_default_counts() -> dict[str, int]:
    """Per-type count defaults, from the nodes' declarations."""
    return {
        n.output_type: n.count_default
        for n in NODE_KINDS.values()
        if n.output_type is not None and n.count_default is not None
    }


def generation_node_kinds() -> frozenset[str]:
    """GENERATION_NODE_KINDS, node-derived (``produces_outputs``)."""
    return frozenset(n.kind for n in NODE_KINDS.values() if n.produces_outputs)


def runtime_fanout_kinds() -> frozenset[str]:
    """Kinds that may materialize outside compile_graph (render, D2)."""
    return frozenset(n.kind for n in NODE_KINDS.values() if n.runtime_fanout)


# ---- self-quotation (P4, N-34): estimate shape + the fold --------------------


def token_bounds(chars: int) -> list[int]:
    """Char count → token range: [chars/5, chars/2] brackets latin (~4
    chars/token) and CJK (~1.5–2) without shipping a tokenizer."""
    return [chars // 5, max(chars // 2, 1)]


def estimate_free() -> dict:
    """A zero quotation (interrupt / deterministic nodes: no LLM, no
    provider-priced units)."""
    return {"prompt_tokens": [0, 0], "completion_tokens": [0, 0], "units": {}}


def estimate_agent(prompt: list[int], completion: list[int]) -> dict:
    """An agent node's quotation: token ranges, no mechanical units."""
    return {
        "prompt_tokens": [max(0, prompt[0]), max(0, prompt[1])],
        "completion_tokens": [max(0, completion[0]), max(0, completion[1])],
        "units": {},
    }


def estimate_mechanical(
    units: dict[str, float], *, prompt: list[int] | None = None, completion: list[int] | None = None
) -> dict:
    """A mechanical node's quotation: exact unit quantities (TTS per char /
    render per second / clone per use / image per piece), optionally with a
    token range when the node also calls an agent (e.g. dub's translator)."""
    base = estimate_agent(prompt or [0, 0], completion or [0, 0])
    base["units"] = dict(units)
    return base


def fold_estimates(estimates: Any) -> dict:
    """报价 = 图 fold (AGENT_ARCH §4.2): field-wise sum over node estimates —
    range lows and highs sum separately; units sum per key. NULL estimates
    (unquoted nodes: fan-out steps, compile-time-unknowable quantities) are
    skipped — the fold is the quotation of the QUOTED subgraph."""
    total = {"prompt_tokens": [0, 0], "completion_tokens": [0, 0], "units": {}}
    for est in estimates:
        if not est:
            continue
        total["prompt_tokens"][0] += int(est["prompt_tokens"][0])
        total["prompt_tokens"][1] += int(est["prompt_tokens"][1])
        total["completion_tokens"][0] += int(est["completion_tokens"][0])
        total["completion_tokens"][1] += int(est["completion_tokens"][1])
        for key, value in (est.get("units") or {}).items():
            total["units"][key] = total["units"].get(key, 0) + value
    return total
