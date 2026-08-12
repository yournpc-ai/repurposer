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
from app.skills.clips.params import SelectClipsParams
from app.skills.posts.node import WritePost  # noqa: F401
from app.skills.quotes.node import WriteQuotes  # noqa: F401
from app.skills.carousel.node import WriteCarousel  # noqa: F401
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
                "en": "Selected {n} clips · {total_seconds}s total",
                "zh": "选出了 {n} 个片段 · 共 {total_seconds} 秒",
            },
        ),
        SkillEntry(
            name="write_post",
            description="Write a LinkedIn long-form post from the talk",
            behavior="probabilistic",
            summary_templates={
                "en": "Wrote a LinkedIn post · {word_count} words",
                "zh": "写好了 LinkedIn 帖子 · {word_count} 词",
            },
        ),
        SkillEntry(
            name="write_quotes",
            description="Write quote cards from the talk's best lines",
            behavior="probabilistic",
            summary_templates={
                "en": "Wrote quote cards · {word_count} words",
                "zh": "写好了金句卡 · {word_count} 词",
            },
        ),
        SkillEntry(
            name="write_carousel",
            description="Write a LinkedIn carousel (slide deck copy)",
            behavior="probabilistic",
            summary_templates={
                "en": "Wrote a carousel · {word_count} words",
                "zh": "写好了轮播 · {word_count} 词",
            },
        ),
        SkillEntry(
            name="write_article",
            description="Write a long-form article / newsletter draft",
            behavior="probabilistic",
            summary_templates={
                "en": "Wrote an article · {word_count} words",
                "zh": "写好了文章 · {word_count} 词",
            },
        ),
        SkillEntry(
            name="revise_script",
            description="Revise one existing output (shorter/longer/tone/language) in place",
            behavior="probabilistic",
            params_model=ReviseScriptParams,
            summary_templates={
                "en": "Revised {scope}",
                "zh": "修订了 {scope}",
            },
        ),
        SkillEntry(
            name="dub_clip",
            description="Dub existing clips with the persona's cloned voice into a target language, then re-render",
            behavior="probabilistic",
            params_model=DubClipParams,
            summary_templates={
                "en": "Dubbed {n} clips · {lang}",
                "zh": "配音了 {n} 个片段 · {lang}",
            },
        ),
        SkillEntry(
            name="translate_clip",
            description="Translate existing clips' captions into another language, then re-render",
            behavior="probabilistic",
            params_model=TranslateClipParams,
            summary_templates={
                "en": "Translated {n} clips · {lang}",
                "zh": "翻译了 {n} 个片段 · {lang}",
            },
        ),
        SkillEntry(
            name="remove_filler",
            description="Remove filler words and repeated takes from existing clips, then re-render",
            behavior="deterministic",
            summary_templates={
                "en": "Removed {filler_count} fillers · {repeat_count} repeated takes",
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
            name="align_stills",
            description="Build an estimated speaking timeline from the transcript so a photo "
            "slideshow gets word-level caption timing — use when there is NO recording "
            "(transcript + photos only; RECIPES §2's third time source: reading pace)",
            behavior="deterministic",
            summary_templates={
                "en": "Aligned transcript · {n} words · {total_seconds}s",
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


def dispatchable_skills() -> list[SkillEntry]:
    """Skills the intent agent may propose: a live node exists in
    ``NODE_KINDS``. Seats (synthesize) are excluded automatically."""
    return [
        entry
        for entry in SKILL_REGISTRY.values()
        if not entry.seat and entry.name in NODE_KINDS
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
