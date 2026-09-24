"""Probe: present_plan rejected while the material is still processing.

Reproduces the 2026-09-24 production incident (project 641cb9fc): the user
sends "你看下这个视频呢，这是我参加的一个采访" with a video whose ASR is
still running; the router's present_plan was rejected ≥2× (struck 0s draft
rows in the dock), the turn looped ~7 minutes, then recovered via ask_user.
The rejection detail rides only the in-loop echo + the API's structlog —
this probe runs the REAL turn in-process so ``tool_loop_rejection`` (kind +
detail) prints here.

Fixture honesty: the asset row is inserted directly as PROCESSING
(attempt=1) — the resident worker claims only PENDING rows, so nothing
races; file_url is a fake key (present_plan never reads the file — the
material gate reads row state only); cleanup is raw DELETEs, never
delete_project (the shared-key unlink trap).

Run (from apps/api, dev DB up):
    uv run python ../../scratch/probe_plan_reject_processing.py
"""

import asyncio
import sys
import time
import uuid
from pathlib import Path

import structlog

# Bind structlog to THIS console before app modules get_logger().
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        structlog.dev.ConsoleRenderer(colors=False),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api" / "scripts"))

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import ChatRequest  # noqa: E402
from app.models.tables import Asset, AssetStatus, AssetType, Conversation, Message, Project, User  # noqa: E402
from app.chat.service import execute_chat_turn, prepare_chat_turn  # noqa: E402
from chat_scenarios import make_user  # noqa: E402

MESSAGE = "你看下这个视频呢，这是我参加的一个采访"


async def main() -> None:
    user_id = await make_user()
    project_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    conv_id: uuid.UUID | None = None
    started = time.monotonic()

    async with AsyncSessionLocal() as db:
        db.add(Project(id=project_id, user_id=user_id, title="probe plan-reject", event_name=""))
        # Staged flush (裸 FK 混插轮盘赌 — no relationship drives the order,
        # so parent lands first explicitly).
        await db.flush()
        db.add(
            Asset(
                id=asset_id,
                user_id=user_id,
                project_id=project_id,
                type=AssetType.VIDEO,
                title="xy_1.mp4",
                file_url="probe/xy_1.mp4",  # fake key — never read, never deleted
                processing_status=AssetStatus.PROCESSING,  # the incident's exact state
                attempt=1,
            )
        )
        await db.commit()

    def on_delta(fragment: str) -> None:
        print(f"  [delta] {fragment}", end="", flush=True)

    def on_phase(phase: str) -> None:
        print(f"\n  [phase] {phase}")

    def on_tool_call(name: str) -> None:
        print(f"\n  [tool name-known] {name}  (+{time.monotonic()-started:.0f}s)")

    def on_tool_ready(name: str, params) -> None:
        print(f"  [tool ready] {name}")

    def on_loop_event(event) -> None:
        print(f"  [loop] {type(event).__name__}: {event}")

    def on_checkpoint(text: str) -> None:
        print(f"\n  [checkpoint] {text}")

    try:
        async with AsyncSessionLocal() as db:
            prepared = await prepare_chat_turn(
                db, user_id, ChatRequest(project_id=project_id, message=MESSAGE)
            )
            conv_id = uuid.UUID(str(prepared.conversation.id))
            print(f"plan_path={prepared.plan_path} — driving the real turn…")
            response = await execute_chat_turn(
                db,
                prepared,
                ChatRequest(project_id=project_id, message=MESSAGE),
                on_delta=on_delta,
                on_phase=on_phase,
                on_tool_call=on_tool_call,
                on_tool_ready=on_tool_ready,
                on_checkpoint=on_checkpoint,
                on_loop_event=on_loop_event,
            )
        print(f"\n=== LANDED (+{time.monotonic()-started:.0f}s) ===")
        print("reply:", (response.assistant_message.content or "")[:400])
        print("run_id:", response.run_id)
    finally:
        # FK-order cleanup, raw DELETEs only — the fake key never touches storage.
        async with AsyncSessionLocal() as db:
            if conv_id:
                await db.execute(
                    Message.__table__.delete().where(Message.conversation_id == conv_id)
                )
                await db.execute(
                    Conversation.__table__.delete().where(Conversation.id == conv_id)
                )
            await db.execute(Asset.__table__.delete().where(Asset.id == asset_id))
            await db.execute(Project.__table__.delete().where(Project.id == project_id))
            await db.execute(User.__table__.delete().where(User.id == user_id))
            await db.commit()
        print("cleaned up (rows only; no storage objects exist)")


if __name__ == "__main__":
    asyncio.run(main())
