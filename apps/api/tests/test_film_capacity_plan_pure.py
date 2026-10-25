"""Capacity proposals go through the director and the real validators, never to rendering."""
import re

import pytest

from app.agents.base import jinja_env
from app.tools.film import storyboard as film

COPY = (
    "Genesis Bounded Autonomy Stack\n"
    "Independent Containment · Safer Execution · Verifiable Outcomes\n"
    "AI services should not have to choose between unchecked execution and a hard stop. "
    "Genesis brings together safer agent actions, multi-agent risk governance, "
    "an infrastructure containment design and an open interoperability baseline. "
    "The goal is to complete authorised work safely and produce evidence that operators can review."
)


def compact(text):
    return re.sub(r"\s+", "", text)


@pytest.mark.parametrize("copy", [COPY, "不漏字，不乱序；保留中文与英文 Cafe\u0301 的组合。接着展示完整的第二段文字，再按容量分到下一幕。"])
@pytest.mark.parametrize("size", [None, "small", "large"])
def test_capacity_plan_covers_copy_in_order_and_fits(copy, size):
    source = film.FilmTextSource(text=copy, verbatim=True)
    lines = film.build_text_manifest(copy)
    plan = film.text_capacity_plan(lines, source, size=size)
    direction = film.FilmTextDirection.model_validate(plan["direction"])
    board, errors = film.assemble_text_storyboard(direction, lines, source=source)
    assert not errors and board is not None
    assert compact("".join(s.copy_text for s in board.scenes)) == compact(copy)
    assert all(len(s.lines) <= 4 for s in board.scenes)
    assert not film.validate_storyboard(board, [], text_lines=lines, narration_required=False)
    for seg in direction.segments:
        for ref in seg.refs:
            line = next(l for l in lines if l.id == ref.line)
            assert film._snap_span(line.text, *ref.span) == tuple(ref.span)


def test_capacity_proposal_does_not_override_named_count_or_authored_copy():
    source = film.FilmTextSource(text=COPY, verbatim=True, scene_count=1)
    lines = film.build_text_manifest(COPY)
    plan = film.text_capacity_plan(lines, source)
    board, errors = film.assemble_text_storyboard(
        film.FilmTextDirection.model_validate(plan["direction"]), lines, source=source,
    )
    assert board is None
    assert any("plan named 1 scenes" in e.detail for e in errors)
    assert film.text_capacity_plan(lines, film.FilmTextSource(text=COPY, verbatim=False)) is None


@pytest.mark.asyncio
async def test_overflow_returns_lossless_plan_and_previous_candidate_to_director(monkeypatch):
    source = film.FilmTextSource(text=COPY, verbatim=True)
    lines = film.build_text_manifest(COPY)
    calls = []

    async def direct(**kwargs):
        calls.append(kwargs)
        plan = kwargs["capacity_plan"]
        assert compact("".join("".join(rows) for rows in plan["display_lines"])) == compact(COPY)
        # Exercise the real prompt wiring as well as the orchestration call.
        ctx = {k: v for k, v in kwargs.items() if k != "repair_feedback"}
        prompt_ctx, _ = film._assemble_text(**ctx)
        prompt = jinja_env.get_template("film_director_text.j2").render(**prompt_ctx)
        assert "Capacity proposal" in prompt
        if len(calls) == 1:
            assert kwargs["previous_direction"] is None
            return film.FilmTextDirection(segments=[film.FilmTextSegment(
                refs=[film.CopyRef(line=l.id) for l in lines], size="large",
            )])
        assert kwargs["previous_direction"]["segments"][0]["size"] == "large"
        assert "wraps to" in kwargs["repair_feedback"]
        assert plan["line_capacity"] == film.film_text_line_cap("large", seat="words")
        assert "Previous rejected candidate" in prompt
        # A visibly authored decision proves the program's proposal isn't
        # silently substituted as the final storyboard.
        answer = film.FilmTextDirection.model_validate(plan["direction"])
        for segment in answer.segments:
            segment.motion = "push"
            segment.motion_scale = 1.03
            segment.seconds = 4.0
        return answer

    monkeypatch.setattr(film.film_text_director, "call", direct)
    board = await film._orchestrate_text_storyboard(
        text_source=source, instruction="Make an animated text film", focus=None,
        language="en", current=None, on_reject=None, allow_fixed_fallback=False,
        voiceover=False,
    )
    assert len(calls) == 2
    assert all(s.motion == "push" and s.seconds == 4 for s in board.scenes)
    assert compact("".join(s.copy_text for s in board.scenes)) == compact(COPY)


@pytest.mark.asyncio
async def test_capacity_seed_is_never_shipped_if_director_fails(monkeypatch):
    from app.providers.llm.base import LLMError

    async def down(**kwargs):
        assert kwargs["capacity_plan"] is not None
        raise LLMError("provider down")

    monkeypatch.setattr(film.film_text_director, "call", down)
    with pytest.raises(LLMError):
        await film._orchestrate_text_storyboard(
            text_source=film.FilmTextSource(text=COPY, verbatim=True),
            instruction=None, focus=None, language=None, current=None,
            on_reject=None, allow_fixed_fallback=False, voiceover=False,
        )


def test_director_can_split_further_and_set_pacing_without_losing_named_total():
    source = film.FilmTextSource(text="First sentence.\nSecond sentence.", verbatim=True,
                                 target_seconds=12)
    lines = film.build_text_manifest(source.text)
    direction = film.FilmTextDirection(segments=[
        film.FilmTextSegment(refs=[film.CopyRef(line=lines[0].id)], seconds=2),
        film.FilmTextSegment(refs=[film.CopyRef(line=lines[1].id)], seconds=4),
    ])
    board, errors = film.assemble_text_storyboard(direction, lines, source=source)
    assert not errors
    assert [s.seconds for s in board.scenes] == [4, 8]
    assert not film.validate_storyboard(board, [], text_lines=lines, narration_required=False)
