"""TerminalRefusal kernel probe (d02bf85a 批) — zero LLM, zero DB: a scripted
stub client drives the REAL loop through the latch's repeat shape
(design → refused → design → TerminalRefusal) and asserts the loop ENDS:
no third generation, ToolRejected facts with the real iterations,
``ended_by`` set, ``exhausted`` False.

Run: cd apps/api && PYTHONPATH=. uv run python scratch/terminal_refusal_probe.py
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from app.agents.tool_loop import (
    ChatTool,
    LoopExhausted,
    TerminalRefusal,
    ToolLoopAgent,
    ToolRejected,
)
from app.providers.llm.base import (
    ProviderCapabilities,
    ToolCall,
    ToolGeneration,
)


class StubClient:
    capabilities = ProviderCapabilities(supports_native_tools=True)

    def __init__(self, script: list[ToolGeneration]) -> None:
        self.script = list(script)
        self.entries: list[str] = []

    async def generate_with_tools(self, messages, tools, **kw: Any) -> ToolGeneration:
        self.entries.append("plain")
        return self.script.pop(0)

    async def generate_stream_with_tools(self, messages, tools, on_delta=None, **kw: Any) -> ToolGeneration:
        self.entries.append("stream")
        return self.script.pop(0)


def _call(name: str, prose: str) -> ToolGeneration:
    return ToolGeneration(content=prose, tool_calls=[ToolCall(id="c", name=name, arguments={})])


async def main() -> int:
    client = StubClient([
        _call("design_storyboard", "我来设计"),
        _call("design_storyboard", "再试一次"),
        _call("answer", "NEVER-REACHED"),
    ])
    events: list[object] = []
    calls: list[str] = []

    async def execute(name: str, params: Any, prose: str):
        calls.append(name)
        if len(calls) == 1:
            return "the begin was refused — the design entry is closed this turn"
        return TerminalRefusal("design entry closed: begin already refused")

    agent = ToolLoopAgent(
        name="terminal_refusal_probe",
        prompt="intent_router.j2",
        system="probe",
        assemble=lambda **ctx: ({"recent": []}, []),
        tools=[ChatTool("design_storyboard", "Design.", None, terminal=False)],
        max_iterations=12,  # the incident's own budget
        client=client,
    )
    result = await agent.call_loop(execute, on_loop_event=lambda e: events.append(e))

    checks = [
        ("execute ran exactly twice (the repeat hit the latch)", calls == ["design_storyboard"] * 2),
        ("no third model generation (12-iteration budget untouched)", len(client.entries) == 2),
        ("ended_by names the refusing tool", result.ended_by == "design_storyboard"),
        ("exhausted stays False (closed, not budget-burned)", result.exhausted is False),
        ("two ToolRejected facts (first refusal + the latched repeat)",
         [e.kind for e in events if isinstance(e, ToolRejected)] == ["execute_guardrail"] * 2),
        ("the latched repeat's fact carries the REAL iteration",
         [e.iteration for e in events if isinstance(e, ToolRejected)] == [0, 1]),
        ("no LoopExhausted event", not any(isinstance(e, LoopExhausted) for e in events)),
    ]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
