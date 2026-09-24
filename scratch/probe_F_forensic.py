"""Probe F forensic: run F's exact gate setup and print per-round tool/params.

Characterizes the 5 failing rounds (wrong plan_id vs extra calls) before any
bisect. Real MiniMax calls — n configurable.

    cd apps/api && uv run python ../../scratch/probe_F_forensic.py [n]
"""

import functools
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(API_DIR / "scripts"))

import asyncio  # noqa: E402

import prompt_gate as pg  # noqa: E402


async def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    client = pg.PROVIDERS["minimax"]()
    chat_agent = pg.ToolLoopAgent(
        name="prompt_gate_chat",
        prompt="chat_intent.j2",
        system=pg.chat_intent_system(),
        temperature=0.2,
        assemble=pg._assemble_chat_turn,
        tools=[*pg.CHAT_TOOLS, *pg.CHAT_READ_TOOLS, *pg.exploration_chat_tools()],
        max_iterations=12,
        client=client,
    )
    execute = functools.partial(
        pg._gate_execute, pending_plan_text=pg._PROBE_F_PENDING_PLAN
    )
    for i in range(n):
        try:
            r = await chat_agent.call_loop(execute, **pg.PROBE_F)
        except Exception as e:  # noqa: BLE001
            print(f"round {i}: PROVIDER ERROR {type(e).__name__}: {e}")
            continue
        plan_id = getattr(r.params, "plan_id", None)
        ok = pg._passed("F", r)
        print(
            f"round {i}: {'PASS' if ok else 'FAIL'} tool={r.tool_name} "
            f"plan_id={plan_id} calls={r.calls}"
        )


if __name__ == "__main__":
    asyncio.run(main())
