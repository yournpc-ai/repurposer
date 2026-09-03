"""research node (ADR-052 B4 pilot): the bounded agent loop's first seat.

Grounds the run's copy with fresh web facts: the researcher agent drives
search/fetch iterations (the tool set = this package's fixed zero-key web
pair — the agent picks actions, never invents tools) up to the declared
cap, then closes with a ResearchBrief stamped into the step's spec
(``spec.research_brief``). ``consumes_research`` writers append it to their
asset texts (derivative_dispatch).

Best-effort enrichment, NEVER a blocker (honest degradation): a funnel
failure, a dry search trail, or cap exhaustion all complete the step with
a caveated brief and the run continues — ``run`` raises only for DB/system
errors, never for research-side failure. ``retries = 0``: retrying a
degraded loop just buys the same empty trail at double the web calls.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.models.schemas import ResearchBrief, ResearchSource
from app.models.tables import Project, WorkflowRun, WorkflowStep
from app.pipeline.graph import BoundedLoopNode, estimate_agent
from app.pipeline.step_display import (
    _fill_summary,
    _set_spec_field,
    _set_stage,
    ui_lang_of,
)
from app.providers.llm.minimax import MiniMaxError
from app.tools.research.agents import researcher
from app.tools.research.web import fetch_text, web_search

logger = structlog.get_logger()

# Evidence text caps: a search's hits compress to title+snippet lines; a
# fetch's page text arrives capped by FETCH_TEXT_CAP already.
_SEARCH_SNIPPET_CAP = 300


class ResearchNode(BoundedLoopNode):
    kind = "research"
    task_name = "Research"
    task_name_zh = "调研"
    # Zero-material legal (requires=()): grounding a topic-only draft is the
    # pilot's main case — the writer lift (2026-08-24) covers the rest.
    requires = ()
    needs_plan_prelude = False
    produces_outputs = False
    retries = 0
    max_iterations = 8
    agents = (researcher,)

    def loop_estimate(self, ctx: dict) -> dict | None:
        """One iteration ≈ one researcher pass over the accumulating
        evidence (web calls carry no provider-priced units)."""
        return estimate_agent([800, 4000], [200, 900])

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        spec = node.spec or {}
        query = (spec.get("query") or "").strip()
        if not query:
            # Compile validates params, so this is only a hand-built-spec
            # guard — degrade honestly instead of failing the run.
            query = ((run.context or {}).get("prompt") or "").strip() or "the run's topic"
        angle = (spec.get("angle") or "").strip() or None

        await _set_stage(node.id, "researching")

        evidence: list[dict[str, str]] = []
        brief: ResearchBrief | None = None
        caveat: str | None = None
        try:
            for iteration in range(1, self.max_iterations + 1):
                verdict = await researcher.call(
                    query=query,
                    angle=angle,
                    evidence=evidence,
                    iteration=iteration,
                    max_iterations=self.max_iterations,
                )
                if verdict.action == "brief" and verdict.brief is not None:
                    brief = verdict.brief
                    break
                if verdict.action == "search" and verdict.query:
                    hits = await web_search(verdict.query)
                    evidence.append(
                        {
                            "kind": "search",
                            "label": verdict.query,
                            "text": _format_hits(hits),
                        }
                    )
                elif verdict.action == "fetch" and verdict.url:
                    text = await fetch_text(verdict.url)
                    evidence.append(
                        {
                            "kind": "fetch",
                            "label": verdict.url,
                            "text": text or "(the page yielded no readable text)",
                        }
                    )
                # A malformed verdict (action without its payload) costs one
                # iteration — the next pass sees the same evidence and picks
                # again; the cap bounds the waste.
        except MiniMaxError as e:
            logger.warning("research_funnel_failed", run_id=str(run.id), error=str(e))
            caveat = "Research unavailable (the researcher failed) — continuing without fresh grounding."

        if brief is None:
            brief = _synthesize_fallback(evidence, caveat)
        elif caveat:
            brief.caveat = brief.caveat or caveat

        await _set_spec_field(
            node.id, "research_brief", brief.model_dump(mode="json")
        )
        await _fill_summary(
            node.id,
            self.kind,
            ui_language=ui_lang_of(run, project),
            n=len(brief.sources),
        )
        return []


def _format_hits(hits: list[dict[str, str]]) -> str:
    if not hits:
        return "(no results — this trail ran dry)"
    return "\n".join(
        f"- {h['title']} — {h['url']}\n  {h['snippet'][:_SEARCH_SNIPPET_CAP]}"
        for h in hits
    )


def _synthesize_fallback(
    evidence: list[dict[str, str]], caveat: str | None
) -> ResearchBrief:
    """The code-owned closing path (cap exhausted without a brief verdict,
    or the funnel failed): assemble whatever the evidence holds, ZERO extra
    LLM calls, the caveat saying exactly which path produced it."""
    sources = [
        ResearchSource(title=item["label"], url=item["label"])
        for item in evidence
        if item["kind"] == "fetch" and item["label"].startswith("http")
    ]
    if caveat is None:
        caveat = (
            "Research incomplete (iteration cap reached) — this brief was "
            "assembled mechanically from the gathered evidence, not written "
            "by the researcher."
        )
    return ResearchBrief(
        summary=caveat if not evidence else "",
        key_facts=[],
        sources=sources,
        caveat=caveat,
    )
