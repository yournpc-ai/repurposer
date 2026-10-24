"""d02bf85a 定点诊断 — the answer continuation's input-durability seam vs the
design beat's NOWAIT begin, on REAL transactions (disposable DB, zero LLM,
zero paid calls).

Entry under test: the PRODUCTION answer continuation — ``answer_question``
with ``_plan_turn`` truncated AT the model boundary (the stub runs the REAL
``begin_film_draft`` instead of the LLM loop). No hand-written commit order
stands in for the production seam.

Assertions (numbered to the batch's evidence list):
1. PRE-FIX order self-locks: backfill → flush (the turn holds the row lock)
   → the REAL begin refuses "locked". (Mechanism proof against the
   production begin — the pre-fix order itself no longer exists in code.)
2. POST-FIX entry: the real answer_question continuation begins the draft —
   the option answer + the user-stated backfill are committed at the seam,
   and the marker is committed + visible from ANOTHER session.
3. A continuation failure after the seam (the stub raises — the LLM
   boundary's failure shape) revokes NEITHER the answer NOR the backfill.
4. True external holds still refuse: a live committed marker → "in_flight";
   a held row lock → "locked".

Isolation: a disposable ``rep_diag_*`` database on the configured Postgres
server (the marker-DB suite's same pattern), dropped at the end. The app's
session factory is rebound to the isolated engine for the process's
duration — the dev database is never touched.

Run: cd apps/api && uv run python scratch/answer_seam_begin_diagnosis.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))


async def _isolated_database():
    """A disposable database on the configured Postgres server (the marker
    suite's ``_isolated_database`` pattern): jsonb + row locks speak real
    SQL; SQLite cannot stand in."""
    from app.config import settings
    from app.models.database import Base
    from app.models import tables  # noqa: F401 — register every table

    url = settings.database_url
    if not url.startswith("postgresql"):
        print(f"SKIP: configured database is not Postgres ({url.split('://')[0]})")
        sys.exit(2)
    server = url.rsplit("/", 1)[0]
    name = f"rep_diag_{uuid4().hex[:12]}"
    admin = create_async_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(f"{server}/{name}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, admin, name


async def main() -> int:
    import app.models.database as db_mod
    from app.models.schemas import Option, OptionAnswerRequest, QuestionPayload
    from app.models.tables import Conversation, Message, Project, User

    engine, admin, db_name = await _isolated_database()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # The side-session seats (begin / clear / committed reads) import the
    # factory deferred from this module — rebind it to the isolated engine.
    db_mod.AsyncSessionLocal = factory

    import app.chat.service as svc
    from app.tools.film import storyboard as sb

    question = QuestionPayload(
        kind="question",
        question="这些文字在片子里怎么处理？",
        options=[Option(id="verbatim", label="逐字全片")],
        allow_freeform=True,
        slot="topic",
    )

    try:
        # ---- seed: user + project + conversation + TWO pending questions --
        async with factory() as db:
            user = User(email=f"diag-{uuid4().hex[:8]}@example.com")
            db.add(user)
            await db.flush()
            project = Project(user_id=user.id, title="seam-diagnosis")
            db.add(project)
            await db.flush()
            conversation = Conversation(
                user_id=user.id, project_id=project.id, title="diag"
            )
            db.add(conversation)
            await db.flush()
            msg_ok = Message(
                conversation_id=conversation.id,
                role="assistant",
                content="这些文字在片子里怎么处理？",
                question=question.model_dump(mode="json"),
            )
            msg_fail = Message(
                conversation_id=conversation.id,
                role="assistant",
                content="这些文字在片子里怎么处理？",
                question=question.model_dump(mode="json"),
            )
            db.add_all([msg_ok, msg_fail])
            await db.commit()
            user_id, project_id = user.id, project.id
            msg_ok_id, msg_fail_id = msg_ok.id, msg_fail.id

        # ---- 1. the PRE-FIX order self-locks (mechanism proof) ------------
        async with factory() as db:
            proj = await db.get(Project, project_id)
            svc._backfill_brief_slot(proj, "topic", "逐字全片")
            await db.flush()  # the old order: the turn's write holds the lock
            begin = await sb.begin_film_draft(
                db, proj, base_version=None, user_message_id=None
            )
            check(
                "1. pre-fix order (backfill→flush→begin) self-locks: refusal=locked",
                begin.draft_id is None and begin.refusal == "locked",
                f"got draft_id={begin.draft_id} refusal={begin.refusal}",
            )
            await db.rollback()

        # ---- 2. the REAL answer entry begins the draft --------------------
        captured: dict = {}

        async def _stub_plan_turn(db, user_id, conversation, project, request,
                                  recent=None, **kw):
            # Truncated AT the model boundary: instead of the LLM loop, run
            # the design beat's REAL begin — the seat the incident refused.
            captured["begin"] = await sb.begin_film_draft(
                db, project, base_version=None, user_message_id=None
            )
            return None, None, {"truncated": True}, []

        orig_plan_turn = svc._plan_turn
        svc._plan_turn = _stub_plan_turn
        try:
            async with factory() as db:
                await svc.answer_question(
                    db, user_id, msg_ok_id,
                    OptionAnswerRequest(kind="option", option_id="verbatim"),
                )
        finally:
            svc._plan_turn = orig_plan_turn

        begin = captured.get("begin")
        check(
            "2a. post-fix entry: the REAL begin lands the draft",
            begin is not None and begin.draft_id is not None,
            f"got {begin}",
        )
        marker = await sb.read_committed_film_marker(UUID(str(project_id)))
        check(
            "2b. the marker is COMMITTED + visible from another session",
            isinstance(marker, dict)
            and begin is not None
            and marker.get("draft_id") == begin.draft_id,
            f"marker={marker}",
        )
        async with factory() as db:
            answered = await db.get(Message, msg_ok_id)
            proj = await db.get(Project, project_id)
            pend = proj.pending_brief or {}
            topic = ((pend.get("brief") or {}).get("topic") or {})
            check(
                "2c. the option answer + user-stated backfill are durable",
                isinstance(answered.answer, dict)
                and answered.answer.get("text") == "逐字全片"
                and topic.get("value") == "逐字全片"
                and topic.get("source") == "user-stated",
                f"answer={answered.answer} topic={topic}",
            )
        # tidy: retire our own marker through the production clear seat
        async with factory() as db:
            proj = await db.get(Project, project_id)
            await sb.clear_film_draft_marker(db, proj, draft_id=begin.draft_id)

        # ---- 3. a continuation failure after the seam revokes nothing -----
        async def _failing_plan_turn(*args, **kw):
            raise RuntimeError("simulated LLM boundary failure")

        svc._plan_turn = _failing_plan_turn
        try:
            try:
                async with factory() as db:
                    await svc.answer_question(
                        db, user_id, msg_fail_id,
                        OptionAnswerRequest(kind="option", option_id="verbatim"),
                    )
                check("3a. the failing continuation propagates", False, "no raise")
            except RuntimeError:
                check("3a. the failing continuation propagates", True)
        finally:
            svc._plan_turn = orig_plan_turn
        async with factory() as db:
            answered = await db.get(Message, msg_fail_id)
            proj = await db.get(Project, project_id)
            topic = (((proj.pending_brief or {}).get("brief") or {}).get("topic") or {})
            check(
                "3b. the answer + backfill survive the continuation's rollback",
                isinstance(answered.answer, dict)
                and answered.answer.get("text") == "逐字全片"
                and topic.get("value") == "逐字全片",
                f"answer={answered.answer} topic={topic}",
            )

        # ---- 4. true external holds still refuse ---------------------------
        async with factory() as db:
            row = await db.get(Project, project_id, with_for_update=True)
            pend = dict(row.pending_brief or {})
            pend["film_draft_inflight"] = {
                "draft_id": "foreign-draft",
                "base_version": None,
                "started_at": time.time(),
                "user_message_id": None,
            }
            row.pending_brief = pend
            await db.commit()
        async with factory() as db:
            proj = await db.get(Project, project_id)
            begin = await sb.begin_film_draft(
                db, proj, base_version=None, user_message_id=None
            )
            check(
                "4a. a live foreign marker refuses 'in_flight'",
                begin.draft_id is None and begin.refusal == "in_flight",
                f"got {begin}",
            )
        holder = factory()
        held = await holder.get(Project, project_id, with_for_update=True)
        assert held is not None
        try:
            async with factory() as db:
                proj = await db.get(Project, project_id)
                begin = await sb.begin_film_draft(
                    db, proj, base_version=None, user_message_id=None
                )
                check(
                    "4b. a held row lock refuses 'locked' (holder unknown)",
                    begin.draft_id is None and begin.refusal == "locked",
                    f"got {begin}",
                )
        finally:
            await holder.rollback()
            await holder.close()
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        await admin.dispose()

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
