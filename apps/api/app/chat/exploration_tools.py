"""exploration_tools — the exploration terminal tool family (ADR-088 §2, R12).

Agent Working Loop 迭代一 (docs/tasks/agent-working-loop-iter-1.md): the
agent's product-semantic proposal verbs for the discovery chain —

- ``propose_candidates`` — the evidence collection the agent found for the
  user's goal (拍 2/3: 检索 → 评估 → 合集上画布);
- ``propose_selects`` — the定版 picks with verdict + one user-safe reason
  (拍 4; R3 理由是属性, R7 证据引用);
- ``propose_plans`` — the Content Plans, one per Select (拍 5; R8 产品
  语义, 完整性自检 draft → ready);
- ``revise_plan`` — the plan-level revision verb (iter-2 ⑦: in-place
  restatement → whole-journey recompile → re-dock on the same seat);
- ``revise_selects`` — the pick-swap verb (iter-3 S4, N-58: member_index
  edit + bounds re-validation + idem preserved + state → revised; the three
  money states adjudicate in the turn layer).

**Production wiring (iter-2 ⑤ plan path + iter-3 S2 chat path, R6)**: the
registry projects into BOTH loops' tool sets via ``exploration_chat_tools()``
(candidates/selects non-terminal — the discovery chain rides one turn;
propose_plans / revise_plan / revise_selects terminal — the dock is the
paid-boundary stop, R15). The harness seat (``execute_exploration_tool``)
drives the same door directly for the deterministic scenario tails.
Descriptions stay product-semantic (R12: no workflow internals — no UUID
lore beyond the ids the observations themselves hand back, no graph
vocabulary).

The execute half (``execute_exploration_tool``) adapts the door's
rejections into observation text (the loop-echo precedent — a rejection
is information for the next iteration, never a crash).
"""

from typing import Any, Literal
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
    revise_plan,
    revise_selects,
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


class ReviseSelectItem(BaseModel):
    """One pick swap (iter-3 S4, N-58): the Select re-points at a DIFFERENT
    member of the SAME candidate set, and the judgment restates for it."""

    model_config = ConfigDict(extra="forbid")
    select_id: UUID = Field(
        description="The pick to swap — from the propose_selects observation or the canvas's pick row, never invented."
    )
    member_index: int = Field(
        description="The NEW member's index in the same candidate set (0-based, in the set's own order)."
    )
    # max_length mirrors the door's SelectSpec (校验分层律 ADR-064 — the
    # constraint bites at the tool boundary, same seat as SelectItem).
    verdict: str = Field(
        max_length=300,
        description="The restated verdict line for the NEW pick — it vouches for the new member, never carries over.",
    )
    reason: str = Field(
        max_length=300,
        description="The restated one-line reason for the NEW pick — the conclusion, never your reasoning process.",
    )


class ReviseSelectsArgs(BaseModel):
    """iter-3 S4 (ADR-089 §6 修订分类, N-58): the select-level revision verb
    — the ONLY way a landed pick swaps. Full restatement of the pick, never
    a patch (the verdict/reason move with the member)."""

    model_config = ConfigDict(extra="forbid")
    selects: list[ReviseSelectItem] = Field(
        description="The pick swaps — one per Select the user wants changed. One call revises one journey."
    )
    # 插话判定座 (ADR-053 R2, iter-3 S2) — same dual-path envelope seat as
    # ProposePlansArgs / RevisePlanArgs: the chat path settles by it; the
    # plan path never reads it.
    pending_disposition: Literal["answer", "skip", "none"] = "none"


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
        description="A compact noun phrase naming the plan (2-6 words, the turn's speech language — name the work).",
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
            "the turn's speech language — name the work, not the tools)."
        ),
    )
    plans: list[PlanItem] = Field(
        description="The Content Plans — one per Select the user should see. One call plans one journey."
    )
    # 插话判定座 (ADR-053 R2, iter-3 S2 双路扩座): the chat path's envelope
    # seat — the turn's pending-question judgment rides the TERMINAL call.
    # The plan path never reads it (its pending settlement is the brief
    # machinery's); there it stays "none".
    pending_disposition: Literal["answer", "skip", "none"] = "none"


class RevisePlanArgs(BaseModel):
    """iter-2 ⑦ (ADR-089 §6 修订分类, contract §4.8): the plan-level revision
    verb — the ONLY way an already-landed plan changes. Full restatement,
    never a patch (读容忍: title/instruction null-tolerant)."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _read_tolerance(cls, data: Any) -> Any:
        return tolerate_null_keys(data, "title", "instruction")

    plan_id: UUID = Field(
        description="The plan to revise — from the decision package on the table (the pending-package block's plan_id), never invented."
    )
    instruction: str = Field(
        default="",
        description="The user's change ask, restated in one compact line (what changes) — the revision's own record of the ask.",
    )
    title: str = Field(
        default="",
        max_length=200,
        description="The plan's title after the revision — omit to keep the current one.",
    )
    outputs: list[PlanOutput] = Field(
        description=(
            "The plan's FULL restated outputs after the revision — no patch "
            "semantics: restate everything that stays, add what changes, "
            "drop what goes."
        )
    )
    # 插话判定座 (ADR-053 R2, iter-3 S2) — same dual-path envelope seat as
    # ProposePlansArgs: the chat path settles by it; the plan path never
    # reads it.
    pending_disposition: Literal["answer", "skip", "none"] = "none"


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
        ChatTool(
            name="revise_selects",
            description=(
                "Swap a landed pick for a different member of the SAME "
                "candidate collection (the user's '第二条换成讲 roadmap 的那段', "
                "'use the pricing answer instead'). Restate the verdict and "
                "reason for the NEW pick — they vouch for the new member, "
                "never carry over. Free before anything runs; when the "
                "affected plans were already confirmed and produced, they "
                "re-confirm as a small package."
            ),
            params_model=ReviseSelectsArgs,
            terminal=True,
        ),
        ChatTool(
            name="revise_plan",
            description=(
                "Revise one already-landed Content Plan in place (the user's "
                "change ask — 'make the second plan French too', 'the clip "
                "square instead') restated as the plan's FULL new outputs. "
                "The package re-compiles and re-docks for confirmation — "
                "every plan-level revision re-confirms."
            ),
            params_model=RevisePlanArgs,
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


def revise_selects_observation(revised: list) -> str:
    lines = [f"{len(revised)} select(s) revised in place:"]
    for n in revised:
        spec = n.spec
        lines.append(
            f"- select_id: {n.id} — now member {spec['member_index']}: "
            f"{spec['verdict']} [{n.state}]"
        )
    lines.append(
        "The plans riding these picks follow the new sections — the system "
        "re-quotes and re-confirms what needs it; you never re-author them."
    )
    return "\n".join(lines)


def revise_observation(node) -> str:
    spec = node.spec
    state_note = (
        "ready"
        if node.state in ("ready", "revised")
        else f"draft — issues: {'; '.join(spec.get('issues') or [])}"
    )
    outputs = ", ".join(
        o["kind"] + (f" ({o['language']})" if o.get("language") else "")
        for o in spec["outputs"]
    )
    return (
        f"Plan revised in place — plan_id: {node.id} — "
        f"{spec['title'] or '(unnamed)'}: {outputs} [{state_note}]. The "
        "decision package re-compiles and re-docks for confirmation."
    )


def exploration_chat_tools() -> list[ChatTool]:
    """The production projection (iter-2 ⑤ plan path + iter-3 S2 chat path,
    R6 — N-57): the SAME registry entries re-formed for BOTH loops' tool
    sets. R2 免费探索区连续工作: candidates/selects ride back as observations
    (NON-terminal — one turn carries the whole discovery chain: search →
    candidates → selects → plans); propose_plans / revise_plan /
    revise_selects stay TERMINAL — landing (or re-landing) the plans docks
    the decision package, which IS the paid-boundary stop (R15), and a pick
    swap can dock too (the three money states, iter-3 S4)."""
    return [
        ChatTool(
            name=t.name,
            description=t.description,
            params_model=t.params_model,
            terminal=t.name in ("propose_plans", "revise_plan", "revise_selects"),
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
        if name == "revise_selects":
            revised = await revise_selects(
                db,
                project,
                selects=[s.model_dump() for s in params.selects],
            )
            return revise_selects_observation(revised)
        if name == "revise_plan":
            node = await revise_plan(
                db,
                project,
                plan_id=params.plan_id,
                title=params.title or None,
                outputs=[o.model_dump() for o in params.outputs],
            )
            return revise_observation(node)
        raise KeyError(name)
    except ExplorationRejected as e:
        return f"The door rejected the proposal: {e}"
