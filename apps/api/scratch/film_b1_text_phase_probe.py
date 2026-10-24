"""B1 verification probe (2026-10-22, repurposer-29): a TEXT film's
draft_film_storyboard must never emit the "capturing" phase — the web
branch alone owns it (the frontend's thinkingPhases.capturing copy is
「正在读网页…」, and a text film reads no page). In-process, zero LLM:
orchestrate_storyboard is stubbed; the probe records the on_progress
sequence and asserts ["storyboarding", None]. The web path's byte-for-byte
behavior is covered by tests/test_film_wait_regression.py (["capturing"]).

Run: cd apps/api && uv run python -I scratch/film_b1_text_phase_probe.py
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.film import storyboard as sb


async def main() -> None:
    phases: list[str | None] = []

    async def on_progress(phase: str | None) -> None:
        phases.append(phase)

    async def fake_orchestrate(**_kwargs):  # zero LLM — the probe's seam
        return SimpleNamespace()

    original = sb.orchestrate_storyboard
    sb.orchestrate_storyboard = fake_orchestrate
    try:
        await sb.draft_film_storyboard(
            None,  # db — the text branch never touches it
            SimpleNamespace(id="b1-probe"),
            instruction="probe",
            on_progress=on_progress,
            text_source=sb.FilmTextSource(
                text="第一句话，验证用。\n第二句话，同样验证。",
                verbatim=True,
            ),
        )
    finally:
        sb.orchestrate_storyboard = original

    print("text-film phases:", phases)
    assert "capturing" not in phases, "B1 regression: a text film emits 'capturing'"
    assert phases == ["storyboarding", None], phases
    print("B1 OK: text film's first phase is 'storyboarding'; no 读网页 flash")


asyncio.run(main())
