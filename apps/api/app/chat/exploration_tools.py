"""exploration_tools — the exploration terminal tool family (ADR-088 §2, R12).

Agent Working Loop 迭代一 (docs/tasks/agent-working-loop-iter-1.md): the
agent's product-semantic proposal verbs for the discovery chain —

- ``propose_candidates`` — the evidence collection the agent found for the
  user's goal (拍 2/3: 检索 → 评估 → 合集上画布);
- ``propose_selects`` — the定版 picks with verdict + one user-safe reason
  (拍 4; R3 理由是属性, R7 证据引用);
- ``propose_plans`` — the Content Plans, one per Select (拍 5; R8 产品
  语义, 完整性自检 draft → ready).

**迁移弧纪律 (ADR-089 §8)**: this registry is HARNESS-LEVEL in iter-1 —
it is NOT registered into the production chat agent's tool set
(``turn_tools.py`` untouched; production wiring lands with R6 routing in
iter-2). The scenario harness composes its own loop with these tools +
the evidence reads (the prompt_gate PLAN_TOOLS precedent). Descriptions
stay product-semantic (R12: no workflow internals — no UUID lore beyond
the ids the observations themselves hand back, no graph vocabulary).

The execute half (``execute_exploration_tool``) adapts the door's
rejections into observation text (the loop-echo precedent — a rejection
is information for the next iteration, never a crash).
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.tool_loop import ChatTool
from app.models.schemas import tolerate_null_keys
from app.models.tables import Project
from app.pipeline.exploration_store import (
    CandidateMember,
    ExplorationRejected,
    PlanOutput,
    propose_candidates,
    propose_plans,
    propose_selects,
)
from sqlalchemy.ext.asyncio import AsyncSession


class ProposeCandidatesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "journey_id")

    asset_id: UUID = Field(
        description="The asset the evidence comes from (from search_transcript's hits)."
    )
    topic: str = Field(
        description="The discovery subject in one or two words (e.g. 'pricing', '定价')."
    )
    goal: str = Field(
        default="",
        description=(
            "The user's goal, restated compactly — it names the journey this "
            "chain belongs to. Required when the call opens the chain "
            "(no journey_id yet); omit afterwards."
        ),
    )
    journey_id: UUID | None = Field(
        default=None,
        description="The journey this chain rides — from a previous exploration observation. Omit when opening a new goal.",
    )
    members: list[CandidateMember] = Field(
        description=(
            "The candidate sections — one per piece of evidence: start/end "
            "in seconds (from the search hits' [start–end] anchors), excerpt "
            "as the VERBATIM speech inside that range (read it first with "
            "get_segment — the door rejects anything not actually said "
            "there), speaker when known."
        )
    )


class SelectItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    member_index: int = Field(
        description="The candidate member's index in its set (0-based, in the order you proposed it)."
    )
    # max_length mirrors the door's SelectSpec (校验分层律 ADR-064): the
    # constraint bites at the tool boundary — the loop's native params
    # repair feeds it back — never as a raw door-side ValidationError,
    # which would escape the echo path and crash the iteration.
    verdict: str = Field(
        max_length=300,
        description="One user-safe verdict line for this pick (e.g. 'Most complete answer on pricing')."
    )
    reason: str = Field(
        max_length=300,
        description="One user-safe reason line — the conclusion, never your reasoning process."
    )


class ProposeSelectsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_set_id: UUID = Field(
        description="The candidate set these picks come from (from the propose_candidates observation)."
    )
    selects: list[SelectItem] = Field(
        description="The定版 picks — evidence pointers with verdicts, never copies."
    )


class PlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "title")

    select_id: UUID = Field(
        description="The Select this plan content-izes (from the propose_selects observation)."
    )
    # max_length mirrors the door's ContentPlanSpec (same 校验分层律 seat).
    title: str = Field(
        max_length=200,
        default="",
        description="A compact noun phrase naming the plan (2-6 words, interface language — name the work).",
    )
    outputs: list[PlanOutput] = Field(
        description=(
            "What the user gets from this plan: each output = its family "
            "(clip / post / article / quotes / carousel) + optional "
            "language / caption_mode / a per-output brief; clips may also "
            "carry aspect (frame format) and dub (re-voiced speech) when "
            "the user names them. Name only what the user named — defaults "
            "absorb the rest."
        )
    )


class ProposePlansArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "name")

    # 展示文案二源律 (ADR-058): the decision package's name — the LLM names
    # the work it structured (the run's receipt title rides it). "" = the
    # display layer's honest fallback.
    name: str = Field(
        default="",
        max_length=200,
        description=(
            "A compact noun phrase naming the whole package (2-6 words, "
            "interface language — name the work, not the tools)."
        ),
    )
    plans: list[PlanItem] = Field(
        description="The Content Plans — one per Select the user should see. One call plans one journey."
    )


EXPLORATION_TOOLS: dict[str, ChatTool] = {
    t.name: t
    for t in (
        ChatTool(
            name="propose_candidates",
            description=(
                "Land the evidence collection you found for the user's goal "
                "— ONE collection card on the canvas (never one card per "
                "section). Call after searching and reading the sections; "
                "the reply carries the journey + set ids for the next step."
            ),
            params_model=ProposeCandidatesArgs,
            terminal=True,
        ),
        ChatTool(
            name="propose_selects",
            description=(
                "Land your picks from a candidate set — each with a verdict "
                "and a one-line reason the user can judge. The user can "
                "swap picks anytime for free, so pick and move on."
            ),
            params_model=ProposeSelectsArgs,
            terminal=True,
        ),
        ChatTool(
            name="propose_plans",
            description=(
                "Land the Content Plans, one per Select — what the user "
                "gets (clips, posts, languages), not how it gets built. A "
                "plan card shows draft until its self-check passes."
            ),
            params_model=ProposePlansArgs,
            terminal=True,
        ),
    )
}

# The harness's loop composition (iter-1): the exploration verbs + the
# evidence reads. Production wiring = iter-2 (R6).
EXPLORATION_READ_NAMES = ("search_transcript", "get_segment", "get_asset", "get_understanding")


# ---- observation text builders (ONE wording, two seats) -------------------------
# The harness seat (execute_exploration_tool below) and the production plan-turn
# seat (iter-2 ③/⑤) both render the agent-facing observation from these — the
# wording never drifts between the two loops.


def candidates_observation(node, *, topic: str, member_count: int) -> str:
    return (
        f"Candidate set landed on the canvas — {member_count} "
        f"member(s) under the topic \"{topic}\".\n"
        f"- candidate_set_id: {node.id}\n- journey_id: {node.journey_id}\n"
        "Next: evaluate the members and call propose_selects with your picks."
    )


def selects_observation(born: list) -> str:
    lines = [f"{len(born)} select(s) landed on the canvas:"]
    for n in born:
        spec = n.spec
        lines.append(f"- select_id: {n.id} — member {spec['member_index']}: {spec['verdict']}")
    lines.append("Next: call propose_plans to structure what the user gets from each Select.")
    return "\n".join(lines)


def plans_observation(born: list) -> str:
    lines = [f"{len(born)} content plan(s) landed on the canvas:"]
    for n in born:
        spec = n.spec
        outputs = ", ".join(
            o["kind"] + (f" ({o['language']})" if o.get("language") else "")
            for o in spec["outputs"]
        )
        state_note = "ready" if n.state == "ready" else f"draft — issues: {'; '.join(spec.get('issues') or [])}"
        lines.append(f"- plan_id: {n.id} — {spec['title'] or '(unnamed)'}: {outputs} [{state_note}]")
    return "\n".join(lines)


def exploration_chat_tools() -> list[ChatTool]:
    """The production projection (iter-2 ⑤, R6 — N-57): the SAME registry
    entries re-formed for the plan path's loop. R2 免费探索区连续工作:
    candidates/selects ride back as observations (NON-terminal — one turn
    carries the whole discovery chain: search → candidates → selects →
    plans); propose_plans stays TERMINAL — landing the plans compiles and
    docks the decision package, which IS the paid-boundary stop (R15)."""
    return [
        ChatTool(
            name=t.name,
            description=t.description,
            params_model=t.params_model,
            terminal=t.name == "propose_plans",
        )
        for t in EXPLORATION_TOOLS.values()
    ]


async def execute_exploration_tool(
    db: AsyncSession,
    project: Project,
    name: str,
    args: dict[str, Any],
    *,
    persona_id: UUID | None = None,
) -> str:
    """Run one exploration terminal call against the door and render its
    observation (success carries the ids the next call needs; a door
    rejection renders as the loop echo, never a crash)."""
    tool = EXPLORATION_TOOLS[name]
    try:
        params = tool.params_model.model_validate(args)  # type: ignore[union-attr]
        if name == "propose_candidates":
            node = await propose_candidates(
                db,
                project,
                asset_id=params.asset_id,
                topic=params.topic,
                members=params.members,
                goal_text=params.goal or None,
                journey_id=params.journey_id,
            )
            return candidates_observation(
                node, topic=params.topic, member_count=len(params.members)
            )
        if name == "propose_selects":
            born = await propose_selects(
                db,
                project,
                candidate_set_id=params.candidate_set_id,
                selects=[s.model_dump() for s in params.selects],
            )
            return selects_observation(born)
        if name == "propose_plans":
            born = await propose_plans(
                db,
                project,
                plans=[p.model_dump() for p in params.plans],
                persona_id=persona_id,
            )
            return plans_observation(born)
        raise KeyError(name)
    except ExplorationRejected as e:
        return f"The door rejected the proposal: {e}"
