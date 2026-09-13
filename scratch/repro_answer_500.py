"""Replay the failing answer turn (2026-09-13): project 620723cd's docked
topic question answered with option b (技术评估) 500s mid-drafting with a
bare "Internal server error" frame (routes._failure_detail swallows the
traceback). Reproduce here with the real service fn so the traceback lands
in this terminal. Mutates the dev DB exactly like the user's click did.
"""

import asyncio
import traceback
from datetime import datetime, timezone
from uuid import UUID

from app.chat.service import answer_question
from app.models.database import AsyncSessionLocal
from app.models.schemas import OptionAnswerRequest

USER_ID = UUID("52037604-9321-4b70-9212-445ccf5ade60")
MESSAGE_ID = UUID("b0d97a29-bf78-42f3-8bed-15908548c2ac")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        data = OptionAnswerRequest(kind="option", option_id="b")

        async def on_delta(fragment: str) -> None:
            pass

        async def on_phase(phase: str) -> None:
            print(f"[phase] {phase}")

        try:
            message, follow_up = await answer_question(
                db, USER_ID, MESSAGE_ID, data,
                on_delta=on_delta, on_phase=on_phase,
            )
        except Exception:
            traceback.print_exc()
            return
        print("OK:", message.id, "follow_up:", follow_up.id if follow_up else None)


asyncio.run(main())
