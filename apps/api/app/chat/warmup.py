"""Startup prefix-cache warmup (provider 硬化批 3, 2026-09-27).

MiniMax's passive prefix cache (``prompt_cache="passive_prefix"``) matches
the request prefix in tools→system→history order, per backend pod, with a
load-dependent TTL — a cold pod's first call always misses (forensics:
verbatim replay hits 17221/17222 tokens; wild calls on cold pods see 128,
the floor). Our assembly is already cache-shaped (byte-stable tools+system,
append-only history, per-turn variance in the tail), so the ONLY lever left
is seeding the cache at boot: one throwaway call per chat agent warms
whichever pod answers.

Cost: ~17k input tokens per agent per process start (full write price, a
few cents). Failure posture: warmup NEVER blocks or fails startup — each
call is guarded, errors are logged and dropped. The user message content is
irrelevant to the cached prefix; the reply is discarded.

Scope: the three chat agents (plan path / chat path / trigger turn) — the
user-perceived-latency surfaces. Pipeline agents (worker process) stay
unwarmed: run latency is not first-byte-critical and their prompts are
smaller.
"""

import structlog

from app.config import settings
from app.agents.tool_loop import ToolLoopAgent, tool_spec
from app.providers.llm.minimax import minimax_client

logger = structlog.get_logger()


def _chat_agents() -> list[ToolLoopAgent]:
    """The three chat-path agents, imported lazily (this module is loaded by
    app.main's lifespan — the agents' modules must not load earlier than
    they already do)."""
    from app.chat.intent import chat_intent_agent, intent_router
    from app.chat.trigger_turn import trigger_agent

    return [intent_router, chat_intent_agent, trigger_agent]


async def warm_chat_prefixes() -> None:
    """One throwaway tool-formatted call per chat agent. Fire-and-forget."""
    if not settings.minimax_warmup_enabled or not settings.minimax_api_key:
        return
    for agent in _chat_agents():
        try:
            await minimax_client.generate_with_tools(
                messages=[
                    {"role": "system", "content": agent.system},
                    {"role": "user", "content": "ping"},
                ],
                tools=[tool_spec(t) for t in agent.tools],
                temperature=agent.temperature,
            )
            logger.info("minimax_warmup_done", agent=agent.name)
        except Exception as exc:  # noqa: BLE001 — warmup never fails startup
            logger.warning("minimax_warmup_failed", agent=agent.name, error=str(exc)[:200])
