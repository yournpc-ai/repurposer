"""Skill registry — the single door for LLM-proposed work (CHAT_ARCH §4).

Three consumers, three views of the same table:
- the intent agent (LLM) sees the proposal space (``dispatchable_skills``
  feeds its prompt);
- ``compile_graph`` adjudicates existence / params / topology against it;
- progress display and metering read ``summary_template`` / ``cost_hint`` /
  ``behavior``.

It is NOT the execution dispatch table (that is ``STEP_RUNNERS`` in
node_runners, which also holds non-skill internal nodes) and NOT a plugin
system (static dict, deployed with the code). Admission discipline: a new
skill passes the NAMING §7/§8 review before it is registered here.
"""

from __future__ import annotations

import difflib
import importlib
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel


class SkillRejected(Exception):
    """A proposed task failed registry adjudication (unknown skill, bad
    params, or a registered-but-not-implemented skill). Carries the closest
    available skills so the caller can let the intent agent repair once."""

    def __init__(self, message: str, *, suggestions: list[str] | None = None) -> None:
        super().__init__(message)
        self.suggestions = suggestions or []


# ---- params schemas (compile-time adjudication; defaults filled by code) ---


class SelectClipsParams(BaseModel):
    count: int = 5


class ReviseScriptParams(BaseModel):
    scope: str = "clip"
    target_output_id: str | None = None
    instruction: str | None = None


class AddMusicParams(BaseModel):
    mood: str | None = None
    music_id: str | None = None
    gain_db: float | None = None


class DubClipParams(BaseModel):
    voice: str | None = None
    target_output_id: str | None = None
    target_language: str = "en"


class TranslateClipParams(BaseModel):
    target_output_id: str | None = None
    target_language: str  # required — no meaningful default


class SynthesizeTalkVideoParams(BaseModel):
    instruction: str | None = None


# ---- registry --------------------------------------------------------------


class SkillEntry(BaseModel):
    """One registered skill (NAMING §5 registry, third member).

    ``runner`` is a dotted path (``module:function``) resolved lazily —
    ``None`` marks a registered-but-not-implemented seat (dub is a sync
    endpoint; synthesize_talk_video awaits the virtual chain). An entry with
    a runner that does not resolve into ``STEP_RUNNERS`` is not dispatchable.
    """

    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str  # "when to use" — injected into the intent prompt
    kind: Literal["skill", "tool"]  # skill = LLM decision unit / tool = deterministic
    behavior: Literal["deterministic", "probabilistic"]
    params_model: type[BaseModel] | None = None
    summary_template: str = ""
    cost_hint: Literal["cheap", "moderate", "expensive"] = "moderate"
    runner: str | None = None  # dotted path; None = seat
    node_kind: str
    needs_director: bool = False
    after: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()  # "media"/"transcript"/"speaker_photo"/"voiceprint"
    produces_outputs: bool = False
    retries: int = 0  # Mastra step-level retry seat; generic retry lands with provider skills


SKILL_REGISTRY: dict[str, SkillEntry] = {
    entry.name: entry
    for entry in [
        SkillEntry(
            name="select_clips",
            description="Cut highlight clips from the source media (batch re-cut)",
            kind="skill",
            behavior="probabilistic",
            params_model=SelectClipsParams,
            summary_template="Selected {n} clips · {total_seconds}s total",
            cost_hint="expensive",
            runner="app.pipeline.node_runners:run_clips_pipeline",
            node_kind="clips_pipeline",
            needs_director=True,
            requires=("media", "transcript"),
            produces_outputs=True,
        ),
        SkillEntry(
            name="write_post",
            description="Write a LinkedIn long-form post from the talk",
            kind="skill",
            behavior="probabilistic",
            summary_template="Wrote a LinkedIn post · {word_count} words",
            runner="app.pipeline.node_runners:run_derivative_gen",
            node_kind="post_gen",
            needs_director=True,
            requires=("transcript",),
            produces_outputs=True,
        ),
        SkillEntry(
            name="write_quotes",
            description="Write quote cards from the talk's best lines",
            kind="skill",
            behavior="probabilistic",
            summary_template="Wrote quote cards · {word_count} words",
            runner="app.pipeline.node_runners:run_derivative_gen",
            node_kind="quotes_gen",
            needs_director=True,
            requires=("transcript",),
            produces_outputs=True,
        ),
        SkillEntry(
            name="write_carousel",
            description="Write a LinkedIn carousel (slide deck copy)",
            kind="skill",
            behavior="probabilistic",
            summary_template="Wrote a carousel · {word_count} words",
            runner="app.pipeline.node_runners:run_derivative_gen",
            node_kind="carousel_gen",
            needs_director=True,
            requires=("transcript",),
            produces_outputs=True,
        ),
        SkillEntry(
            name="write_article",
            description="Write a long-form article / newsletter draft",
            kind="skill",
            behavior="probabilistic",
            summary_template="Wrote an article · {word_count} words",
            runner="app.pipeline.node_runners:run_derivative_gen",
            node_kind="article_gen",
            needs_director=True,
            requires=("transcript",),
            produces_outputs=True,
        ),
        SkillEntry(
            name="revise_script",
            description="Revise one existing output (shorter/longer/tone/language) in place",
            kind="skill",
            behavior="probabilistic",
            params_model=ReviseScriptParams,
            summary_template="Revised {scope}",
            runner="app.pipeline.node_runners:run_script_revision",
            node_kind="script",
            produces_outputs=True,
        ),
        SkillEntry(
            name="dub_clip",
            description="Dub existing clips with the speaker's cloned voice into a target language, then re-render",
            kind="skill",
            behavior="probabilistic",
            params_model=DubClipParams,
            summary_template="Dubbed {n} clips · {lang}",
            runner="app.pipeline.node_runners:run_dub_clip",
            node_kind="dub",
            requires=("media",),
        ),
        SkillEntry(
            name="translate_clip",
            description="Translate existing clips' captions into another language, then re-render",
            kind="skill",
            behavior="probabilistic",
            params_model=TranslateClipParams,
            summary_template="Translated {n} clips · {lang}",
            cost_hint="moderate",
            runner="app.pipeline.node_runners:run_translate_clip",
            node_kind="translate_clip",
            requires=("transcript",),
        ),
        SkillEntry(
            name="remove_filler",
            description="Remove filler words and repeated takes from existing clips, then re-render",
            kind="tool",
            behavior="deterministic",
            summary_template="Removed {filler_count} fillers · {repeat_count} repeated takes",
            cost_hint="cheap",
            runner="app.pipeline.node_runners:run_remove_filler",
            node_kind="remove_filler",
            after=("select_clips",),
            requires=("transcript",),
        ),
        SkillEntry(
            name="add_music",
            description="Score existing clips with a music bed, then re-render",
            kind="tool",
            behavior="deterministic",
            params_model=AddMusicParams,
            summary_template="Scored · {mood} bed",
            cost_hint="cheap",
            runner="app.pipeline.node_runners:run_add_music",
            node_kind="add_music",
            after=("select_clips",),
            requires=("media",),
        ),
        SkillEntry(
            name="synthesize_talk_video",
            description="Synthesize a talking-head video from transcript + speaker photo + voiceprint",
            kind="skill",
            behavior="probabilistic",
            params_model=SynthesizeTalkVideoParams,
            summary_template="Synthesized a talk video",
            cost_hint="expensive",
            runner=None,  # seat: virtual chain lands with docs/tasks/synthetic-talk-video.md
            node_kind="synth_talk_video",
            requires=("transcript", "speaker_photo", "voiceprint"),
            produces_outputs=True,
        ),
    ]
}


# ---- consumers' views ------------------------------------------------------


def _resolve_runner(entry: SkillEntry) -> Callable[..., Any] | None:
    """Resolve an entry's dotted runner path; None when unresolvable."""
    if entry.runner is None:
        return None
    try:
        module_path, func_name = entry.runner.split(":", 1)
        return getattr(importlib.import_module(module_path), func_name)
    except (ImportError, AttributeError, ValueError):
        return None


def dispatchable_skills() -> list[SkillEntry]:
    """Skills the intent agent may propose: runner resolves AND the node kind
    is registered in STEP_RUNNERS. Seats (dub / synthesize) and not-yet-landed
    runners are excluded automatically."""
    from app.pipeline.node_runners import STEP_RUNNERS  # deferred: avoid import cycle

    return [
        entry
        for entry in SKILL_REGISTRY.values()
        if entry.node_kind in STEP_RUNNERS
        and _resolve_runner(entry) is STEP_RUNNERS[entry.node_kind]
    ]


def validate_task_list(tasks: list[Any]) -> list[SkillEntry]:
    """Adjudicate a proposed task list. Returns the resolved entries in order;
    raises SkillRejected (with close-match suggestions) on the first offense."""
    dispatchable = {entry.name: entry for entry in dispatchable_skills()}
    entries: list[SkillEntry] = []
    for task in tasks:
        entry = dispatchable.get(task.skill)
        if entry is None:
            known = task.skill in SKILL_REGISTRY
            message = (
                f"Skill '{task.skill}' is registered but not yet implemented"
                if known
                else f"Unknown skill '{task.skill}'"
            )
            raise SkillRejected(
                message,
                suggestions=difflib.get_close_matches(
                    task.skill, dispatchable.keys(), n=3, cutoff=0.4
                )
                or sorted(dispatchable.keys()),
            )
        if entry.params_model is not None:
            try:
                entry.params_model.model_validate(task.params or {})
            except Exception as e:
                raise SkillRejected(
                    f"Skill '{task.skill}' rejected its params: {e}",
                    suggestions=[entry.name],
                ) from e
        entries.append(entry)
    return entries


def generation_node_kinds() -> frozenset[str]:
    """GENERATION_NODE_KINDS, registry-derived (produces_outputs=True)."""
    return frozenset(
        entry.node_kind for entry in SKILL_REGISTRY.values() if entry.produces_outputs
    )


def assert_runners_registered() -> None:
    """Startup self-check: every entry with a runner path must resolve into
    STEP_RUNNERS under its declared node_kind. Seats (runner=None) are skipped."""
    from app.pipeline.node_runners import STEP_RUNNERS  # deferred: avoid import cycle

    for entry in SKILL_REGISTRY.values():
        if entry.runner is None:
            continue
        resolved = _resolve_runner(entry)
        if resolved is None:
            raise RuntimeError(f"Skill '{entry.name}': runner {entry.runner} unresolvable")
        if entry.node_kind not in STEP_RUNNERS:
            raise RuntimeError(
                f"Skill '{entry.name}': node_kind '{entry.node_kind}' not in STEP_RUNNERS"
            )
        if STEP_RUNNERS[entry.node_kind] is not resolved:
            raise RuntimeError(
                f"Skill '{entry.name}': runner does not match STEP_RUNNERS[{entry.node_kind!r}]"
            )
