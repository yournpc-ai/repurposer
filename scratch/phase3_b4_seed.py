"""Phase 3 Batch B ④ seed — a project with a docked plan at PLAN_READY ∧
CONFIRMATION_READY (real /chat SSE turn, fake-bytes COMPLETED asset), plus a
funded wallet (Start's create_run hold needs balance). Prints ONE JSON line
{project_id, token, user} for the CDP driver.

Run: cd apps/api && PYTHONPATH=. uv run python ../../scratch/phase3_b4_seed.py
Cleanup: same script with --cleanup <project_id> <user_id>
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import httpx

from app.models.database import AsyncSessionLocal
from app.models.tables import Asset, AssetStatus, AssetType, User
from app.platform.auth import create_access_token
from app.platform.billing import get_or_create_wallet

BASE = "http://127.0.0.1:8000/api/v1"
TIMEOUT = httpx.Timeout(180.0)


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"phase3-b4-{uuid.uuid4().hex[:8]}@test.local",
            name="b4-deadwindow-probe",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = uuid.UUID(str(user.id))
        # Start's create_run holds credits at birth — fund the wallet.
        wallet = await get_or_create_wallet(db, user_id)
        print(f"wallet balance: {wallet.balance}", file=sys.stderr)

        token = create_access_token(user_id)
        client = httpx.AsyncClient(
            base_url=BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )

        res = await client.post("/projects", json={"title": "B4 dead-window probe", "event_name": ""})
        assert res.status_code == 201, res.text
        pid = res.json()["id"]

        asset = Asset(
            user_id=user_id,
            project_id=uuid.UUID(pid),
            type=AssetType.TRANSCRIPT,
            file_url=f"scenario/b4-{uuid.uuid4().hex[:6]}.txt",
            title="talk-notes.txt",
            extracted_text=(
                "This year we cut three products and doubled down on the one "
                "workflow our users actually loved. Focus beat breadth: every "
                "meeting, every roadmap review, we asked whether the work "
                "compounded the core loop. The result was fewer launches and "
                "a healthier business."
            ),
            meta={"language": "en"},
            processing_status=AssetStatus.COMPLETED,
        )
        db.add(asset)
        await db.commit()

    # Dock a plan via a REAL SSE chat turn (LLM variance: allow one nudge).
    async def chat_turn(message: str) -> dict:
        envelope: dict = {}
        async with client.stream(
            "POST",
            "/chat",
            json={"project_id": pid, "message": message},
            headers={"Accept": "text/event-stream"},
        ) as res:
            assert res.status_code == 200, res.status_code
            event = ""
            async for line in res.aiter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:") and event == "turn.completed":
                    envelope = json.loads(line[5:].strip())
        return envelope

    docked = False
    for message in (
        "Write a LinkedIn post and a short article from my notes.",
        "Just do it — English, one post and one article.",
    ):
        turn = await chat_turn(message)
        q = (turn.get("assistant_message") or {}).get("question") or {}
        if q.get("kind") == "task_book":
            docked = True
            break
    assert docked, "plan did not dock after two turns — LLM variance, re-run the seed"

    # The stamp must land BOTH flags (the B4 preconditions).
    res = await client.get(f"/projects/{pid}/graph")
    assert res.status_code == 200, res.text
    stamp = (res.json() or {}).get("lifecycle") or {}
    assert stamp.get("plan_ready") is True, f"plan_ready not stamped: {stamp}"
    assert stamp.get("confirmation_ready") is True, (
        f"confirmation_ready not stamped: blockers={stamp.get('blockers')}"
    )

    print(json.dumps({
        "project_id": pid,
        "token": token,
        "user": {"id": str(user_id), "email": user.email, "name": user.name},
    }))


async def cleanup(pid: str, uid: str) -> None:
    async with AsyncSessionLocal() as db:
        user = await db.get(User, uuid.UUID(uid))
        if user is not None:
            # API delete keeps the sharing invariants (asset unlink etc.).
            token = create_access_token(user.id)
            async with httpx.AsyncClient(
                base_url=BASE,
                headers={"Authorization": f"Bearer {token}"},
                timeout=TIMEOUT,
            ) as client:
                await client.delete(f"/projects/{pid}")
            # FK order: the chat turn auto-provisions a persona and the run's
            # hold writes credit_transactions — both outlive the project delete.
            from app.models.tables import CreditTransaction, Persona, Wallet

            await db.execute(
                CreditTransaction.__table__.delete().where(
                    CreditTransaction.user_id == user.id
                )
            )
            await db.execute(Wallet.__table__.delete().where(Wallet.user_id == user.id))
            await db.execute(Persona.__table__.delete().where(Persona.user_id == user.id))
            await db.delete(user)
            await db.commit()
    print("cleaned", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--cleanup":
        asyncio.run(cleanup(sys.argv[2], sys.argv[3]))
    else:
        asyncio.run(seed())
