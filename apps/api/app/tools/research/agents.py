"""researcher — the research loop's one agent (ADR-052 B4).

One decision per iteration: search (a NEW query) / fetch (one result URL)
/ brief (close with the final artifact). The node owns the loop and the
tool set; the agent only picks the next action over the evidence it can
see. No declared fallback: a funnel failure propagates as MiniMaxError and
the NODE degrades honestly (a caveated brief, the run continues) — a
silent LLM-free "brief" here would fabricate grounding that never happened.
"""

from app.agents.base import Agent, AssembleResult
from app.models.schemas import ResearchVerdict

# One evidence item's text cap in the prompt — fetches arrive capped at
# FETCH_TEXT_CAP; the prompt trims further so 8 iterations of evidence stay
# well inside the window.
_EVIDENCE_TEXT_CAP = 2000


def _assemble(
    query: str,
    angle: str | None,
    evidence: list[dict[str, str]],
    iteration: int,
    max_iterations: int,
) -> AssembleResult:
    trimmed = [
        {
            "kind": item.get("kind", ""),
            "label": item.get("label", ""),
            "text": (item.get("text") or "")[:_EVIDENCE_TEXT_CAP],
        }
        for item in evidence
    ]
    return (
        {
            "query": query,
            "angle": angle,
            "evidence": trimmed,
            "iteration": iteration,
            "max_iterations": max_iterations,
        },
        [],
    )


researcher = Agent[ResearchVerdict](
    name="researcher",
    prompt="research.j2",
    schema=ResearchVerdict,
    system=(
        "You are a meticulous web researcher. You ground a content brief "
        "with fresh, checkable facts — you only ever assert what the "
        "gathered evidence says, and you name the sources you used."
    ),
    assemble=_assemble,
    temperature=0.2,
)
