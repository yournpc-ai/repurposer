"""Prompt gate (ADR-071 Consequences, T2 2026-09-12): the pre-deploy
behavioral threshold for the intent router's system prompt.

NOT an A/B instrument (that is `scratch/router_ab_probe.py`, for prompt
editing sessions) — this gate asserts ABSOLUTE minimum rates for the LIVE
prompt, so a regression is caught before deploy, not after. Three probes,
same contexts as the A/B instrument:

- A:start-call — a plan on the table + "looks good, start" must call
  start_run (never a same-chain re-plan). Measured band 9-11/12 across all
  prompt versions; threshold 8 catches a real regression (the 2/5-era
  degradation) with flake headroom.
- B:slot-handshake — pending topic question + free-text answer must propose
  brief.topic user-stated on the terminal call (else the user's answer falls
  on the floor). Measured 8/8 and 12/12; threshold 8/12 fails a return to
  the old prompt's ~2/3 band.
- C:rootless-wish — a rootless wish must end at ask_user slot='topic'. The
  stub execute MIRRORS the production guardrail (a rootless present_plan is
  rejected with the gate's feedback), so both the direct ask and the
  corrected-after-rejection path count — only docking groundless work or
  answering away fails. Measured 11-12/12; threshold 10.
- D:discovery-goal (iter-2 ⑤ R6) — with material attached, a
  where-in-the-material ask must run the discovery chain: the terminal call
  is propose_plans with propose_candidates earlier in ``r.calls`` and
  present_plan NEVER called. (Contract deviation, documented: the brief's
  literal「终态必须是 propose_candidates」predates the R2 one-turn-chain
  ruling — production continuity carries candidates → selects → plans in
  the SAME turn, so the chain's terminal IS propose_plans.) The stub hands
  the verbs their observation ids exactly like production.
- E:post-run-discovery (iter-3 S2, R6 chat-path parity) — the CHAT path's
  shape (chat_intent_system + _assemble_chat_turn + the chat tool set with
  the exploration projection): post-run '再找两段…剪成短片' must run the
  SAME discovery chain — propose_plans terminal, propose_candidates in the
  trace, propose_tasks / edit_graph NEVER called (the discovery ask never
  falls back to the router-drafted verbs).
- F:package-revision (iter-3 S3, review 注记②) — a docked decision package
  + '把第二个方案改成法语' must end at revise_plan carrying the SECOND
  plan's plan_id (序位→id 精确命中, 验收 #3), read off the get_pending_plan
  stub — propose_tasks / edit_graph never called (a package revision never
  re-derives the chain).
- G:craft-revision (iter-3 S3, N-58) — post-run 'plan 2 的帖子语气再尖锐
  一点' must end at revise_output with plan_ref relayed verbatim
  (containing '2'), never edit_graph / propose_tasks.
- H:precise-edit routing (精确编辑迭代 S3, ADR-090; Final Hardening B1
  扩为四族 2026-09-24) — a landed clip + a mechanically executable change
  must end at edit_output with the verb decoded from WHICH param is
  filled (schemas.edit_kind_for_params — there is no kind field): H =
  remove_range (quote verbatim), H2 = set_trim (seconds=3), H3 =
  set_title (title verbatim), H4 = set_caption_style (preset enum via the
  list_caption_styles stub). revise_output / propose_tasks / edit_graph
  are misroutes for changes this definite. B1's structural invariant is
  asserted at startup: the chat tool set carries NO raw-ops verb.

Tool-loop form (ADR-077 判词②, 2026-09-14): the agent is the ToolLoopAgent,
the action IS the terminal tool call, and the predicates read
``LoopResult`` — the thresholds are UNCHANGED. T2b (2026-09-15): the gate's
agent carries the production tool set INCLUDING the plan path's read tools
(PLAN_READ_TOOLS — the registry perturbation is the thing being gated), and
the stub execute answers reads with a ToolObservation so the loop iterates
to its terminal call exactly like production. Iter-2 ⑤: the exploration
verbs ride too (``exploration_chat_tools()`` — the production projection,
candidates/selects non-terminal), and the stub answers them from the SAME
observation builders the production seat uses (zero wording drift).

A gate failure means: re-run once (provider drift exists even at these
thresholds), then bisect with the A/B instrument — never tune the
thresholds to make a regression pass.

Usage (from apps/api):
    uv run python scripts/prompt_gate.py [--n 12] [--probe A|B|C|D|E|F|G|H|H2|H3|H4] [--provider minimax]
"""

import argparse
import asyncio
import functools
import sys
from pathlib import Path

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import BaseModel  # noqa: E402

from app.agents.tool_loop import (  # noqa: E402
    LoopResult,
    ToolLoopAgent,
    ToolObservation,
)
from app.chat.exploration_tools import (  # noqa: E402
    candidates_observation,
    exploration_chat_tools,
    selects_observation,
)
from app.chat.intent import _assemble_chat_turn, _assemble_plan_turn  # noqa: E402
from app.chat.perception import PERCEPTION_TOOLS  # noqa: E402
from app.chat.prompts import chat_intent_system, intent_router_system  # noqa: E402
from app.chat.turn_tools import (  # noqa: E402
    CHAT_READ_TOOLS,
    CHAT_TOOLS,
    PLAN_READ_TOOLS,
    PLAN_TOOLS,
)
from app.models.schemas import (  # noqa: E402
    Brief,
    BriefSlotSource,
    edit_kind_for_params,
)
from app.models.tables import Message  # noqa: E402
from app.pipeline.clip_spec import _CAPTION_STYLE_PRESETS  # noqa: E402
from app.providers.llm.minimax import minimax_client  # noqa: E402

# The provider registry (T4 参数化): --provider picks the client the gate's
# agent runs against. "minimax" is the only seat today; a new provider joins
# here AND must declare native tools (the loud capabilities check in main —
# the tool loop speaks Tier 1, ADR-077 判词④). Factories, not instances:
# the client is built inside main so importing the gate never touches the
# provider's env.
PROVIDERS = {
    "minimax": lambda: minimax_client,
}

# (probe, minimum passes out of N). D's band is measured; E measured at
# introduction (2026-09-23, iter-3 S2): 11/12 band-reading + 9/12 on the
# full-gate rerun — threshold 8 holds with real-regression headroom.
# F/G measured at introduction (2026-09-23, iter-3 S3): F 10/12; G 9/12 on
# the first reading — the failures were a params dialect (plan_ref as a
# bare int), fixed in the SCHEMA (coerce_numbers_to_str, 顺形律), then
# 12/12. Thresholds hold at 8 with headroom — recalibrate from readings,
# never to excuse a regression.
THRESHOLDS = {"A": 8, "B": 8, "C": 10, "D": 8, "E": 8, "F": 8, "G": 8, "H": 8,
              "H2": 8, "H3": 8, "H4": 8}

BRIEF_ANSWERED = Brief.model_validate(
    {
        "topic": {"value": "EU AI Act for researchers", "source": "user-stated"},
        "audience": {"value": "researchers", "source": "user-stated"},
        "material_state": {"value": "none", "source": "default"},
        "asked": ["topic"],
    }
)
BRIEF_EMPTY_ASKED = Brief.model_validate(
    {
        "material_state": {"value": "none", "source": "default"},
        "asked": ["topic"],
    }
)
TOPIC_QUESTION = Message(
    role="assistant",
    content="What topic should the post cover?",
    question={
        "question": "What topic should the post cover — one phrase is enough?",
        "options": [],
        "slot": "topic",
        "default_path": "skip and I'll draft from your persona's style",
        "allow_freeform": True,
    },
)

PROBE_A = {
    "message": "looks good, start",
    "brief": BRIEF_ANSWERED,
    "presented_plan": "write_post (language: en) — 'EU AI Act post for researchers'",
    "recent": [
        "user: I want a social post.",
        "assistant: What topic should the post cover — one phrase is enough?",
        "user: Make it about the EU AI Act for researchers.",
        "assistant: Got it — a post on the EU AI Act for researchers, drafted "
        "in your persona's style. Start it as-is, or tell me what to adjust.",
    ],
}
PROBE_B = {
    "message": "Make it about the EU AI Act for researchers.",
    "brief": BRIEF_EMPTY_ASKED,
    "pending_question": TOPIC_QUESTION,
    "recent": [
        "user: I want a social post.",
        "assistant: What topic should the post cover — one phrase is enough?",
    ],
}
# Scenario users have NO persona (scripts/chat_scenarios.py persona_exists:
# False) — the gate matches or the pantry changes the judgment surface.
# Scenario users have NO persona (scripts/chat_scenarios.py persona_exists:
# False) — the gate matches or the pantry changes the judgment surface.
PROBE_C = {"message": "I want a social post."}

# E's post-run substrate (iter-3 S2): a project that already produced —
# readable AV material, one landed clip, the latest run completed. The
# context text is hand-assembled in build_context's exact shape (digest
# doctrine — identity lines only, the reads answer the rest).
_PROBE_E_ASSET_ID = "66666666-6666-6666-6666-666666666666"
_PROBE_E_SEARCH_HITS = (
    'Search "{query}" — 3 hit(s) across 1 asset(s):\n'
    f"Asset founder-talk.mp4 (asset_id: {_PROBE_E_ASSET_ID}) — 3 hit(s):\n"
    '- [05.0–11.2] "Onboarding is where users decide to stay." (host)\n'
    '- [22.4–27.8] "The first week sets the habit."\n'
    '- [41.0–46.5] "We redesigned onboarding around one aha moment."'
)
_PROBE_E_SEGMENT = (
    '[05.0–11.2] "Onboarding is where users decide to stay. The first '
    'minute matters most." (host)'
)
PROBE_E = {
    "message": "再找两段我讲到 onboarding 的地方，剪成短片",
    "context": {
        "text": (
            "Project: Founder Talks "
            "(id=77777777-7777-7777-7777-777777777777, language=en)\n"
            "Assets:\n"
            f"- video id={_PROBE_E_ASSET_ID} status=ready language=en\n"
            "Current outputs:\n"
            "- clip id=88888888-8888-8888-8888-888888888888: onboarding highlights\n"
            "Latest run: status=done id=99999999-9999-9999-9999-999999999998\n"
            "Recent rounds:\n"
            "- user: Cut the best onboarding moments into a clip.\n"
            "- assistant: Landed one clip from the onboarding section."
        )
    },
}

# F's docked package (iter-3 S3, review 注记②): a decision package awaiting
# confirmation, readable through the get_pending_plan stub — the reading
# layer's plan_ids are revise_plan's ONLY source on the chat path (A-1).
_PROBE_F_PLAN_A = "aaaaaaaa-1111-1111-1111-111111111111"
_PROBE_F_PLAN_B = "bbbbbbbb-2222-2222-2222-222222222222"
_PROBE_F_PENDING_PLAN = (
    "Docked plan (waiting for the user's confirmation):\n"
    "- Original request: 再挑两段我讲到 onboarding 的地方，一条短片一条帖子\n"
    "- Name: Onboarding picks\n"
    "- Tasks:\n"
    '  - cut_segments {"segments":[{"start":5.0,"end":11.2}],"asset_id":"66666666-6666-6666-6666-666666666666"}\n'
    '  - write_post {"language":"en","source_span":{"start":22.4,"end":27.8}}\n'
    "- Content plans (name them by plan_id when revising):\n"
    f"  1) plan_id={_PROBE_F_PLAN_A} — Onboarding clip: clip [ready]\n"
    f"  2) plan_id={_PROBE_F_PLAN_B} — Onboarding post: post (en) [ready]"
)
PROBE_F = {
    "message": "把第二个方案改成法语",
    "context": {
        "text": (
            "Project: Founder Talks "
            "(id=77777777-7777-7777-7777-777777777777, language=en)\n"
            "Assets:\n"
            f"- video id={_PROBE_E_ASSET_ID} status=ready language=en\n"
            "Current outputs:\n"
            "- clip id=88888888-8888-8888-8888-888888888888: onboarding highlights\n"
            "Latest run: status=done id=99999999-9999-9999-9999-999999999998\n"
            "Pending question awaiting the user's answer: Start this plan?"
        )
    },
}

# G's post-run craft ask (iter-3 S3): confirmed work exists; the message
# points by ordinal ('plan 2') — the model relays it verbatim, the router
# resolves.
PROBE_G = {
    "message": "plan 2 的帖子语气再尖锐一点",
    "context": {
        "text": (
            "Project: Founder Talks "
            "(id=77777777-7777-7777-7777-777777777777, language=en)\n"
            "Assets:\n"
            f"- video id={_PROBE_E_ASSET_ID} status=ready language=en\n"
            "Current outputs:\n"
            "- clip id=88888888-8888-8888-8888-888888888888: onboarding highlights\n"
            "- post id=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee: onboarding post\n"
            "Latest run: status=done id=99999999-9999-9999-9999-999999999998"
        )
    },
}

# H's precise edit (精确编辑迭代 S3, ADR-090): a landed clip with visible
# captions; the message names a mechanically executable change. The model
# must route edit_output with kind=remove_range and relay the quoted words
# verbatim — revise_output (open craft) / propose_tasks / edit_graph are
# all misroutes for a change this definite.
PROBE_H = {
    "message": '把开头那句 "Onboarding is where users decide to stay" 删掉',
    "context": {
        "text": (
            "Project: Founder Talks "
            "(id=77777777-7777-7777-7777-777777777777, language=zh)\n"
            "Assets:\n"
            f"- video id={_PROBE_E_ASSET_ID} status=ready language=en\n"
            "Current outputs:\n"
            "- clip id=88888888-8888-8888-8888-888888888888: onboarding highlights\n"
            "Latest run: status=done id=99999999-9999-9999-9999-999999999998\n"
            "Recent rounds:\n"
            "- user: Cut the best onboarding moments into a clip.\n"
            "- assistant: Landed one clip from the onboarding section."
        )
    },
}

# Final Hardening B1 (2026-09-24): the four request families each get a
# probe — same landed-clip context, one mechanically executable change per
# family. The verb must decode from WHICH param is filled
# (schemas.edit_kind_for_params — there is no kind field to assert on).
PROBE_H2 = {
    "message": "把这条视频结尾剪掉 3 秒",
    "context": PROBE_H["context"],
}
PROBE_H3 = {
    "message": "把这条视频的标题改成「AI 时代的内容创作」",
    "context": PROBE_H["context"],
}
PROBE_H4 = {
    "message": "把这条视频的字幕换成卡拉 OK 高亮那种样式",
    "context": PROBE_H["context"],
}

# D's discovery substrate: material attached and readable (the excerpt is
# the search read's honest footing — the stub's search observation below
# quotes from it verbatim so the chain has real evidence to propose).
_PROBE_D_CSET_ID = "11111111-1111-1111-1111-111111111111"
_PROBE_D_JOURNEY_ID = "99999999-9999-9999-9999-999999999999"
# The stub asset's id — the canned search observation names it in the
# header (the production observation's same handoff: get_segment /
# propose_candidates read their asset_id from the search hits).
_PROBE_D_ASSET_ID = "33333333-3333-3333-3333-333333333333"
_PROBE_D_SEARCH_HITS = (
    'Search "{query}" — 3 hit(s) across 1 asset(s):\n'
    f"Asset keynote-2026.mp4 (asset_id: {_PROBE_D_ASSET_ID}) — 3 hit(s):\n"
    '- [12.0–18.9] "Our pricing is simple." (host)\n'
    '- [34.0–39.4] "Every tier includes the dashboard."\n'
    '- [58.2–63.0] "You only pay when you grow."'
)
_PROBE_D_SEGMENT = (
    '[12.0–18.9] "Now let me talk about pricing. Our pricing is '
    'simple." (host)'
)
PROBE_D = {
    "message": (
        "Find the parts where I talk about pricing — cut those into a clip, "
        "and write an English post from them."
    ),
    "brief": Brief.model_validate(
        {"material_state": {"value": "attached", "source": "default"}}
    ),
    "filename": "keynote-2026.mp4",
    "material_excerpt": (
        "…Now let me talk about pricing. Our pricing is simple. Every tier "
        "includes the dashboard. You only pay when you grow…"
    ),
}


class _StubNode:
    """The gate stub's stand-in for a door-born row (the observation
    builders read id / journey_id / spec off it — same duck-typing as the
    compiler's preview rows)."""

    def __init__(self, id: str, journey_id: str | None = None, spec: dict | None = None):
        self.id = id
        self.journey_id = journey_id
        self.spec = spec or {}


async def _gate_execute(
    name: str,
    params: BaseModel | None,
    prose: str,
    *,
    search_hits: str = _PROBE_D_SEARCH_HITS,
    segment_text: str = _PROBE_D_SEGMENT,
    pending_plan_text: str | None = None,
):
    """The gate's execution stub — accepts everything EXCEPT the rootless
    present_plan (mirrors the production 出书门槛 probe C measures: no
    user-stated topic, no material, and the topic never asked → the gate
    rejects toward ask_user). None = accepted (terminal). T2b: a read tool
    answers with a ToolObservation (the probe contexts have nothing readable)
    so the loop iterates on to its terminal call exactly like production.

    ``search_hits`` / ``segment_text`` theme the canned evidence reads per
    probe (D = pricing, E = onboarding) — the header echoes the call's own
    query exactly like production (``Search "<query>" — …``)."""
    if name in PERCEPTION_TOOLS:
        if name == "search_transcript":
            # The discovery probes' evidence substrate: plausible hits
            # quoting the excerpt verbatim, so the chain has real ranges to
            # propose from. The header mirrors the production observation's
            # shape — asset label + the asset_id handoff (the get_segment
            # seat's input).
            query = getattr(params, "query", None) or ""
            return ToolObservation(search_hits.format(query=query))
        if name == "get_segment":
            return ToolObservation(segment_text)
        if name == "get_pending_plan" and pending_plan_text is not None:
            # F's docked package (iter-3 S3): the reading layer the chat
            # path's revise_plan reads its plan_id from.
            return ToolObservation(pending_plan_text)
        if name == "list_caption_styles":
            # H4's enum substrate (Final Hardening B1): the preset catalog
            # read, mirroring production's list_caption_styles seat — the
            # model must map the user's words to one of THESE ids, never a
            # free-form style.
            return ToolObservation(
                "Caption style presets (the full catalog):\n"
                + "\n".join(f"- {p}" for p in sorted(_CAPTION_STYLE_PRESETS))
            )
        return ToolObservation(
            "(gate stub: nothing readable in this probe context)"
        )
    # The exploration verbs (iter-2 ⑤): the stub stands in for the door —
    # candidates/selects ride back as observations built from the SAME
    # builders production uses (the ids the next call needs ride along);
    # propose_plans is terminal here (accepted → None).
    if name == "propose_candidates":
        return ToolObservation(
            candidates_observation(
                _StubNode(id=_PROBE_D_CSET_ID, journey_id=_PROBE_D_JOURNEY_ID),
                topic=params.topic,
                member_count=len(params.members),
            )
        )
    if name == "propose_selects":
        return ToolObservation(
            selects_observation(
                [
                    _StubNode(
                        id=f"22222222-2222-2222-2222-22222222222{i}",
                        spec={
                            "member_index": s.member_index,
                            "verdict": s.verdict,
                        },
                    )
                    for i, s in enumerate(params.selects)
                ]
            )
        )
    if name == "propose_plans":
        return None
    if name == "edit_output":
        # Mirror the production verb-decode law (Final Hardening B1 —
        # schemas.edit_kind_for_params, propose_turn._edit_output): the verb
        # comes from WHICH single param is filled (there is no kind field);
        # zero/2+ filled is refused and the loop repairs — the stub must not
        # ACCEPT what production refuses, or the probe measures the
        # malformed call as terminal.
        if not edit_kind_for_params(params.params):
            return (
                "edit_output takes exactly ONE filled param — quote "
                "(remove_range) / seconds (set_trim) / style "
                "(set_caption_style) / title (set_title); an open-ended "
                "change goes to revise_output, a deliverables change to "
                "revise_plan."
            )
        return None
    if name == "present_plan":
        brief = getattr(params, "brief", None)
        topic = brief.topic if brief else None
        rooted = (
            topic is not None
            and bool((topic.value or "").strip())
            and topic.source == BriefSlotSource.USER_STATED
        ) or bool((getattr(params, "material_text", None) or "").strip())
        if not rooted:
            return (
                "the brief has no root (no topic, no material, no explicitly "
                "named grounded recipe) and the topic was never asked — a "
                "rootless plan never docks. Call ask_user with slot='topic' "
                "asking the ONE topic question."
            )
    return None


def _passed(probe: str, r: LoopResult) -> bool:
    if probe == "A":
        return r.tool_name == "start_run"
    if probe == "B":
        brief = getattr(r.params, "brief", None)
        topic = brief.topic if brief else None
        return (
            topic is not None
            and bool((topic.value or "").strip())
            and topic.source == BriefSlotSource.USER_STATED
        )
    # C: the direct ask OR the corrected-after-rejection ask — the terminal
    # call must be the topic question either way.
    if probe == "C":
        return r.tool_name == "ask_user" and getattr(r.params, "slot", None) == "topic"
    # D (iter-2 ⑤): the discovery chain closed — propose_plans terminal,
    # propose_candidates earlier in the trace, present_plan never touched.
    if probe == "D":
        return (
            r.tool_name == "propose_plans"
            and "propose_candidates" in r.calls
            and "present_plan" not in r.calls
        )
    # E (iter-3 S2): same chain law on the CHAT path — propose_plans
    # terminal, propose_candidates in the trace, and the router-drafted
    # verbs (propose_tasks / edit_graph) never touched.
    if probe == "E":
        return (
            r.tool_name == "propose_plans"
            and "propose_candidates" in r.calls
            and "propose_tasks" not in r.calls
            and "edit_graph" not in r.calls
        )
    # F (iter-3 S3, review 注记②): the docked package's revision ends at
    # revise_plan carrying the SECOND plan's id (序位→id 精确命中) — the
    # router-drafted verbs never touched.
    if probe == "F":
        return (
            r.tool_name == "revise_plan"
            and str(getattr(r.params, "plan_id", "")) == _PROBE_F_PLAN_B
            and "propose_tasks" not in r.calls
            and "edit_graph" not in r.calls
            and "revise_output" not in r.calls
        )
    # G (iter-3 S3): the craft revision ends at revise_output with the
    # user's pointing relayed verbatim (plan_ref carries the '2') — never
    # edit_graph / propose_tasks.
    if probe == "G":
        return (
            r.tool_name == "revise_output"
            and "2" in str(getattr(getattr(r.params, "target", None), "plan_ref", "") or "")
            and "edit_graph" not in r.calls
            and "propose_tasks" not in r.calls
        )
    # H/H2/H3/H4 (精确编辑迭代 S3, ADR-090; Final Hardening B1 四族): the
    # precise edit routes edit_output with the verb decoded from WHICH
    # param is filled (schemas.edit_kind_for_params — there is no kind
    # field), the user's words relayed verbatim — the open-craft /
    # proposal / wiring verbs are all misroutes for a change this
    # definite.
    if probe.startswith("H"):
        ep = getattr(r.params, "params", None)
        if r.tool_name != "edit_output" or ep is None:
            return False
        if "revise_output" in r.calls or "propose_tasks" in r.calls or "edit_graph" in r.calls:
            return False
        kind = edit_kind_for_params(ep)
        if probe == "H":
            return kind == "remove_range" and (
                "onboarding is where users decide to stay"
                in str(ep.quote or "").lower()
            )
        if probe == "H2":
            return kind == "set_trim" and ep.seconds is not None and abs(ep.seconds - 3) < 0.01
        if probe == "H3":
            return kind == "set_title" and (ep.title or "").strip() == "AI 时代的内容创作"
        # H4: the style must be the enum id mapped off the catalog read,
        # never a free-form phrase.
        return kind == "set_caption_style" and (ep.style or "") == "karaoke-highlight"
    raise AssertionError(f"no predicate registered for probe {probe!r}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=12)
    parser.add_argument("--probe", choices=["A", "B", "C", "D", "E", "F", "G", "H", "H2", "H3", "H4"], default=None)
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="minimax")
    args = parser.parse_args()

    client = PROVIDERS[args.provider]()
    capabilities = getattr(client, "capabilities", None)
    if capabilities is None or not capabilities.supports_native_tools:
        # The loud capabilities check (T4): the gate probes the tool-loop
        # line — a provider without declared native tools has nothing to
        # gate here (the loop itself would raise LLMError on every turn and
        # a 0/12 read would masquerade as a prompt regression).
        raise SystemExit(
            f"prompt gate: provider {args.provider!r} does not declare native "
            "tool support — the gate probes the tool-loop line (ADR-077 "
            "判词④); a Tier-2 provider has nothing to gate here."
        )
    # max_iterations mirrors the production declarations (intent.py) — live
    # evidence 2026-09-23: the realistic discovery chain is 8-10 (6 evidence
    # reads observed), a plans params rejection at iteration 9 starved
    # recovery at 10 (S-explore-2 runs 1-2); 12 = realistic 9-10 + 2.
    plan_agent = ToolLoopAgent(
        name="prompt_gate_router",
        prompt="intent_router.j2",
        system=intent_router_system(),
        temperature=0.2,
        assemble=_assemble_plan_turn,
        # The production tool set verbatim (iter-2 ⑤): the exploration
        # verbs' production projection rides — the registry perturbation is
        # the thing being gated.
        tools=[*PLAN_TOOLS, *PLAN_READ_TOOLS, *exploration_chat_tools()],
        max_iterations=12,
        client=client,
    )
    # Probe E runs the CHAT path's shape (iter-3 S2, R6 parity): chat_intent
    # system + the chat-turn assembler + the chat tool set with the same
    # exploration projection — the registry perturbation is again the thing
    # being gated.
    chat_agent = ToolLoopAgent(
        name="prompt_gate_chat",
        prompt="chat_intent.j2",
        system=chat_intent_system(),
        temperature=0.2,
        assemble=_assemble_chat_turn,
        tools=[*CHAT_TOOLS, *CHAT_READ_TOOLS, *exploration_chat_tools()],
        max_iterations=12,
        client=client,
    )
    probes = {
        "A": PROBE_A,
        "B": PROBE_B,
        "C": PROBE_C,
        "D": PROBE_D,
        "E": PROBE_E,
        "F": PROBE_F,
        "G": PROBE_G,
        "H": PROBE_H,
        "H2": PROBE_H2,
        "H3": PROBE_H3,
        "H4": PROBE_H4,
    }
    # Final Hardening B1 (2026-09-24): the chat tool set must NOT carry the
    # retired raw-ops verb — its presence would make every routing
    # predicate's "never the raw path" clause vacuous. Asserted once here so
    # the four H-family probes measure a real boundary.
    assert "apply_edit_ops" not in {t.name for t in CHAT_TOOLS}, (
        "apply_edit_ops is back in CHAT_TOOLS — the Agent's raw-ops edit "
        "path must stay closed (Final Hardening B1)"
    )
    failed = False
    for name, ctx in probes.items():
        if args.probe and name != args.probe:
            continue
        agent = chat_agent if name in ("E", "F", "G", "H", "H2", "H3", "H4") else plan_agent
        # E's evidence reads quote onboarding, not pricing (the themed
        # canned observations keep the chain honest to the ask); F's
        # get_pending_plan stub carries the docked package's plan_ids.
        execute = _gate_execute
        if name == "E":
            execute = functools.partial(
                _gate_execute,
                search_hits=_PROBE_E_SEARCH_HITS,
                segment_text=_PROBE_E_SEGMENT,
            )
        elif name == "F":
            execute = functools.partial(
                _gate_execute, pending_plan_text=_PROBE_F_PENDING_PLAN
            )
        outcomes = []
        provider_errors = 0
        for _ in range(args.n):
            try:
                r = await agent.call_loop(execute, **ctx)
                outcomes.append(_passed(name, r))
            except Exception as e:  # noqa: BLE001 — provider errors are NOT behavior
                # 2026-09-24 实测坑: a mid-gate 402 drained the balance and
                # the tail probes read 7/3/0/12 — a financial event
                # masquerading as a prompt regression (same masquerade class
                # as the capabilities check above). Provider errors are
                # tallied separately and INVALIDATE the probe's reading —
                # they never count as behavioral failures.
                provider_errors += 1
                print(f"  probe {name} call error: {type(e).__name__}: {e}", file=sys.stderr)
        if provider_errors:
            print(
                f"probe {name}: INVALID — {provider_errors}/{args.n} round(s) "
                "lost to provider errors (balance/rate/upstream); rerun after "
                "the provider recovers — this is not a behavioral reading."
            )
            failed = True
            continue
        hits = sum(outcomes)
        need = THRESHOLDS[name]
        ok = hits >= need
        failed |= not ok
        print(f"probe {name}: {hits}/{args.n} (threshold {need}) — {'PASS' if ok else 'FAIL'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
