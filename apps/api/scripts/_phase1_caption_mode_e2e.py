import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""Phase 1 e2e verification: chat 反问 caption_mode.

Run with: uv run python /tmp/phase1_caption_mode_e2e.py

Exercises the full flow:
  1. POST /projects → fresh project
  2. POST /chat "make a quote card from this talk" → expect AskPayload choice
     with 3 caption_mode_* options (NOT a task_book dock — Phase 1 docks the
     caption mode question BEFORE letting the run start).
  3. POST /chat/messages/{qid}/answer caption_mode_bilingual → expect a
     task_book question dock on the assistant_message (the answer path
     replays the stashed TaskListProposal as InferredIntent + PendingIntent).
  4. Inspect pending_intent → caption_mode="bilingual" must be set.
  5. "Start" via /chat "开始吧" → run.context.caption_mode lands as
     "bilingual" on the WorkflowRun row (verify via /results or DB).
"""

import json
import os
import sys
import uuid

import httpx

BASE = os.getenv("SCENARIO_API_BASE", "http://127.0.0.1:8000/api/v1")


def fail(msg: str, ctx=None) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    if ctx is not None:
        print(json.dumps(ctx, indent=2, ensure_ascii=False, default=str), file=sys.stderr)
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"✓ {msg}")


def main() -> None:
    from app.platform.auth import create_access_token  # noqa: PLC0415
    from app.models.tables import User  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415
    from app.models.database import AsyncSessionLocal  # noqa: PLC0415
    import asyncio

    async def setup() -> tuple[str, str]:
        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
            if user is None:
                fail("no test user in DB — abort")
            token = create_access_token(user.id)
            async with httpx.AsyncClient(
                base_url=BASE,
                headers={"Authorization": f"Bearer {token}"},
                timeout=60.0,
            ) as client:
                # Fresh project
                res = await client.post(
                    "/projects",
                    json={"title": "Phase1 caption_mode e2e", "event_name": ""},
                )
                if res.status_code != 201:
                    fail("create project", res.text)
                pid = res.json()["id"]
                return token, pid

    async def run(token: str, pid: str) -> None:
        async with httpx.AsyncClient(
            base_url=BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0,
        ) as client:
            # --- Turn 1: chat "make a quote card" ---
            res = await client.post(
                "/chat",
                json={"project_id": pid, "message": "make a quote card"},
            )
            if res.status_code != 201:
                fail("turn1 chat", res.text)
            turn1 = res.json()
            assistant_msg = turn1["assistant_message"]
            question = assistant_msg.get("question")
            if not question:
                fail("turn1 must dock a question", assistant_msg)
            if question.get("kind") != "choice":
                fail("turn1 must dock a choice question (not task_book)", question)
            options = question.get("options") or []
            option_ids = [o.get("id") for o in options]
            expected_ids = [
                "caption_mode_bilingual",
                "caption_mode_source_only",
                "caption_mode_target_only",
            ]
            if option_ids != expected_ids:
                fail(
                    f"turn1 options must be {expected_ids}",
                    {"got": option_ids, "options": options},
                )
            ok("turn1 docks a 3-option caption_mode choice question")
            question_id = assistant_msg["id"]
            ok(f"question id = {question_id}")

            # --- Turn 2: answer with caption_mode_bilingual ---
            res = await client.post(
                f"/chat/messages/{question_id}/answer",
                json={"kind": "option", "option_id": "caption_mode_bilingual"},
            )
            if res.status_code not in (200, 201):
                fail("turn2 answer", res.text)
            turn2 = res.json()
            # The answer endpoint returns {answered_question, follow_up}
            # (CHAT_ARCH §3.3). The new docked task_book is in follow_up.
            new_assistant_msg = turn2.get("follow_up")
            if not new_assistant_msg:
                fail("turn2 must return a follow_up task_book question", turn2)
            new_question = new_assistant_msg.get("question")
            if not new_question:
                fail(
                    "follow_up must carry a question (task_book)",
                    new_assistant_msg,
                )
            if new_question.get("kind") != "task_book":
                fail(
                    "follow_up must be a task_book question",
                    new_question,
                )
            ok("turn2 docks a task_book question after caption_mode answer")
            ok(f"follow-up question id = {new_assistant_msg['id']}")

            # --- Verify caption_mode lands in pending_intent ---
            res = await client.get(f"/projects/{pid}/results")
            if res.status_code != 200:
                fail("get /projects/{pid}/results", res.text)
            results_body = res.json()
            pending_intent = results_body.get("pending_intent")
            if not pending_intent:
                fail("no pending_intent on /results", results_body)
            intent = pending_intent.get("intent") or {}
            caption_mode = intent.get("caption_mode")
            if caption_mode != "bilingual":
                fail(
                    "pending_intent.intent.caption_mode must be 'bilingual'",
                    {"got": caption_mode, "intent": intent},
                )
            ok(f"pending_intent.intent.caption_mode = {caption_mode!r}")

            tasks = intent.get("tasks") or []
            if not any(t.get("tool") == "write_quotes" for t in tasks):
                fail("task_book must contain a write_quotes task", tasks)
            ok("task_book contains write_quotes task")

            # --- Turn 3: "Start" → run lands with caption_mode in context ---
            res = await client.post(
                "/chat",
                json={"project_id": pid, "message": "开始吧"},
            )
            if res.status_code != 201:
                fail("turn3 start", res.text)
            turn3 = res.json()
            if turn3.get("answered_question") is None:
                fail(
                    "turn3 should archive the task_book question as QA",
                    turn3,
                )
            ok("turn3 archived the task_book question (Start fired)")

    token, pid = asyncio.run(setup())
    print(f"project = {pid}")
    asyncio.run(run(token, pid))
    print()
    print("ALL PHASE 1 E2E CHECKS GREEN")


if __name__ == "__main__":
    main()