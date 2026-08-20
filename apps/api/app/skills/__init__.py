"""Skill registry (ADR-039 P2) — the single door for LLM-proposed work.

This module IS the registry door: importing it imports the internal crew
(``pipeline/node_runners``) and every skill package's ``node.py``, which
self-registers each node into ``pipeline/graph.py``'s ``NODE_KINDS`` (import
order below is the curated proposal order). Three consumers, three views of
the same table:

- the intent agent (LLM) sees the proposal space (``dispatchable_skills``
  feeds its prompt);
- ``compile_graph`` adjudicates existence / params / topology against it;
- progress display and metering read ``summary_templates`` / ``behavior``.

It is NOT a plugin system (static dict, deployed with the code). Admission
discipline: a new skill passes the NAMING §7/§8 review before it is
registered here.

A ``SkillEntry`` carries only proposal/display data (description / params /
summary template); all execution and topology knowledge lives on the node
classes (N-35: a skill's name IS its node's kind — no parallel fields).
"""

from __future__ import annotations

import difflib
from typing import Any, Literal

from pydantic import BaseModel

# The registry door: these imports populate NODE_KINDS (side effect). The
# internal crew first, then skill packages in curated proposal order.
import app.pipeline.node_runners  # noqa: F401
from app.skills.clips.node import SelectClips  # noqa: F401
from app.skills.clips.materialize import MaterializeSource  # noqa: F401 — NODE_KINDS only; an internal node (ADR-043), never a registry entry
from app.skills.clips.params import SelectClipsParams
from app.pipeline.derivative_dispatch import CopyWriterParams
from app.skills.posts.node import WritePost  # noqa: F401
from app.skills.quotes.node import WriteQuotes  # noqa: F401
from app.skills.quotes.params import WriteQuotesParams
from app.skills.carousel.node import WriteCarousel  # noqa: F401
from app.skills.carousel.params import WriteCarouselParams
from app.skills.article.node import WriteArticle  # noqa: F401
from app.skills.revise.node import ReviseScript  # noqa: F401
from app.skills.revise.params import ReviseScriptParams
from app.skills.dub.node import DubClip  # noqa: F401
from app.skills.dub.params import DubClipParams
from app.skills.captions.node import TranslateClip  # noqa: F401
from app.skills.captions.params import TranslateClipParams
from app.skills.filler.node import RemoveFiller  # noqa: F401
from app.skills.music.node import AddMusic  # noqa: F401
from app.skills.music.params import AddMusicParams
from app.skills.reframe.node import ReframeClip  # noqa: F401
from app.skills.reframe.params import ReframeClipParams
from app.skills.stills.node import AlignStills  # noqa: F401

from app.pipeline.graph import NODE_KINDS


class SkillRejected(Exception):
    """A proposed task failed registry adjudication (unknown skill, bad
    params, or a registered-but-not-implemented skill). Carries the closest
    available skills so the caller can let the intent agent repair once."""

    def __init__(self, message: str, *, suggestions: list[str] | None = None) -> None:
        super().__init__(message)
        self.suggestions = suggestions or []


# ---- params schemas ---------------------------------------------------------
#
# Skill params models live in their packages (``skills/<pkg>/params.py``)
# and are imported above. Field descriptions are injected into the intent
# agent's proposal prompt (agent-loop-upgrade W2) — they ARE the LLM's
# parameter documentation, so write them as "when to use / what null
# means", not as type restatements.
#
# Only node-less seats keep their params model here.


class SynthesizeTalkVideoParams(BaseModel):
    instruction: str | None = None


# ---- registry --------------------------------------------------------------


class SkillEntry(BaseModel):
    """One registered skill (NAMING §5 registry, third member).

    Proposal/display data only — execution knowledge (run / requires /
    retries / topology) and the quotation (``estimate``, N-34) live on the
    node class in ``NODE_KINDS`` under the same name (N-35). A seat
    (``seat=True``) is a registered-but-not-implemented skill: propose-able
    nowhere, excluded from dispatchable.
    """

    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str  # "when to use" — injected into the intent prompt
    behavior: Literal["deterministic", "probabilistic"]
    params_model: type[BaseModel] | None = None
    # Per-locale display templates ("en" required, others fall back to it):
    # _fill_summary picks by the run's pinned UI locale — step lines follow
    # the UI language, never the material's.
    summary_templates: dict[str, str] = {}
    seat: bool = False  # registered-but-not-implemented (no node yet)


SKILL_REGISTRY: dict[str, SkillEntry] = {
    entry.name: entry
    for entry in [
        SkillEntry(
            name="select_clips",
            description="Cut highlight clips from the source media (batch re-cut)",
            behavior="probabilistic",
            params_model=SelectClipsParams,
            summary_templates={
                "en": "Selected {n} clip{n_s} · {total_seconds}s total",
                "zh": "选出了 {n} 个片段 · 共 {total_seconds} 秒",
            },
        ),
        SkillEntry(
            name="write_post",
            description="Write a LinkedIn long-form post from the talk",
            behavior="probabilistic",
            params_model=CopyWriterParams,
            summary_templates={
                "en": "Wrote a LinkedIn post · {word_count} word{word_count_s}",
                "zh": "写好了 LinkedIn 帖子 · {word_count} 词",
            },
        ),
        SkillEntry(
            name="write_quotes",
            description="Write quote cards from the talk's best lines",
            behavior="probabilistic",
            params_model=WriteQuotesParams,
            summary_templates={
                "en": "Wrote quote cards · {word_count} word{word_count_s}",
                "zh": "写好了金句卡 · {word_count} 词",
            },
        ),
        SkillEntry(
            name="write_carousel",
            description="Write a LinkedIn carousel (slide deck copy)",
            behavior="probabilistic",
            params_model=WriteCarouselParams,
            summary_templates={
                "en": "Wrote a carousel · {word_count} word{word_count_s}",
                "zh": "写好了轮播 · {word_count} 词",
            },
        ),
        SkillEntry(
            name="write_article",
            description="Write a long-form article / newsletter draft",
            behavior="probabilistic",
            params_model=CopyWriterParams,
            summary_templates={
                "en": "Wrote an article · {word_count} word{word_count_s}",
                "zh": "写好了文章 · {word_count} 词",
            },
        ),
        SkillEntry(
            name="revise_script",
            description="Revise one existing output (shorter/longer/tone/language) in place",
            behavior="probabilistic",
            params_model=ReviseScriptParams,
            summary_templates={
                "en": "Revised · {title}",
                "zh": "修订了 · {title}",
            },
        ),
        SkillEntry(
            name="dub_clip",
            description="Dub existing clips with the persona's cloned voice into a target language, then re-render",
            behavior="probabilistic",
            params_model=DubClipParams,
            summary_templates={
                "en": "Dubbed {n} clip{n_s} · {lang}",
                "zh": "配音了 {n} 个片段 · {lang}",
            },
        ),
        SkillEntry(
            name="translate_clip",
            description="Translate existing clips' captions into another language, then re-render",
            behavior="probabilistic",
            params_model=TranslateClipParams,
            summary_templates={
                "en": "Translated {n} clip{n_s} · {lang}",
                "zh": "翻译了 {n} 个片段 · {lang}",
            },
        ),
        SkillEntry(
            name="remove_filler",
            description="Remove filler words and repeated takes from existing clips, then re-render",
            behavior="deterministic",
            summary_templates={
                "en": "Removed {filler_count} filler{filler_count_s} · {repeat_count} repeated take{repeat_count_s}",
                "zh": "剪掉了 {filler_count} 处口水词 · {repeat_count} 处重拍",
            },
        ),
        SkillEntry(
            name="add_music",
            description="Score existing clips with a music bed, then re-render",
            behavior="deterministic",
            params_model=AddMusicParams,
            summary_templates={
                "en": "Scored · {mood} bed",
                "zh": "配乐完成 · {mood} 风格",
            },
        ),
        SkillEntry(
            name="reframe_clip",
            description="Reframe existing clips for the output aspect — the camera sits on "
            "whoever is talking, or follows a moving speaker — then re-render",
            behavior="deterministic",
            params_model=ReframeClipParams,
            summary_templates={
                "en": "Reframed {n} clip{n_s}",
                "zh": "分镜完成 · {n} 个片段",
            },
        ),
        SkillEntry(
            name="align_stills",
            description="Build an estimated speaking timeline from the transcript so a photo "
            "slideshow gets word-level caption timing — use when there is NO recording "
            "(transcript + photos only; RECIPES §2's third time source: reading pace)",
            behavior="deterministic",
            summary_templates={
                "en": "Aligned transcript · {n} word{n_s} · {total_seconds}s",
                "zh": "对齐了逐字稿 · {n} 词 · {total_seconds} 秒",
            },
        ),
        SkillEntry(
            name="synthesize_talk_video",
            description="Synthesize a talking-head video from transcript + persona photo + voiceprint",
            behavior="probabilistic",
            params_model=SynthesizeTalkVideoParams,
            summary_templates={
                "en": "Synthesized a talk video",
                "zh": "合成了口播视频",
            },
            seat=True,  # seat: virtual chain lands with docs/tasks/synthetic-talk-video.md
        ),
    ]
}


# ---- consumers' views ------------------------------------------------------


# Billing guardrail (2026-08-20 ruling): every task in a chain is paid work
# (LLM / image / render) — an unbounded list is an unbounded bill.
MAX_TASKS_PER_RUN = 10


def dispatchable_skills() -> list[SkillEntry]:
    """Skills the intent agent may propose: a live node exists in
    ``NODE_KINDS``. Seats (synthesize) are excluded automatically."""
    return [
        entry
        for entry in SKILL_REGISTRY.values()
        if not entry.seat and entry.name in NODE_KINDS
    ]


def strip_null_params(params: dict | None) -> dict:
    """The proposal convention is "null = take the default" (the params field
    descriptions say so) — drop explicit nulls before schema validation so an
    optional-in-spirit field never dies on a strict-typed schema (2026-08-19:
    a bare `count: null` sank ~half of recipe-template plan turns after the
    repair round repeated it; the STORED book then 500'd the same way at
    compile time — every params-validation site goes through here)."""
    return {k: v for k, v in (params or {}).items() if v is not None}


def validate_task_list(tasks: list[Any]) -> list[SkillEntry]:
    """Adjudicate a proposed task list. Returns the resolved entries in order;
    raises SkillRejected (with close-match suggestions) on the first offense."""
    # Billing guardrail (2026-08-20 ruling): every task in the chain is paid
    # work (LLM / image / render) — an unbounded list is an unbounded bill.
    if len(tasks) > MAX_TASKS_PER_RUN:
        raise SkillRejected(
            f"Task book too large: {MAX_TASKS_PER_RUN} tasks max per run "
            f"(got {len(tasks)})",
            suggestions=[],
        )
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
                params = entry.params_model.model_validate(strip_null_params(task.params))
            except Exception as e:
                raise SkillRejected(
                    f"Skill '{task.skill}' rejected its params: {e}",
                    suggestions=[entry.name],
                ) from e
            # Count bounds adjudication (birthplace C3's mode② form): the
            # node's count_limits declaration is the single source — an
            # out-of-bounds count is real money (999 quotes = 999 images).
            node = NODE_KINDS.get(entry.name)
            count = getattr(params, "count", None)
            if node is not None and node.count_limits and count is not None:
                lo, hi = node.count_limits
                if not lo <= count <= hi:
                    raise SkillRejected(
                        f"Skill '{task.skill}' count must be between {lo} and "
                        f"{hi} (got {count})",
                        suggestions=[entry.name],
                    )
        entries.append(entry)
    return entries
