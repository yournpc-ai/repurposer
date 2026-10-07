"""Materialize legacy ``activity_log`` aggregate rows into per-frame array
rows (ADR-108 W5 — 一次性迁移).

Pre-array persistence stored a turn's settled activity frames as ONE message
row (``intent.type='activity_log'``, ``frames: [...]``); the array model
(ADR-108) is 每帧一行 — every visible element is its own array row written
at open and updated in place at settle. This script rewrites history into
the new shape so the frontend's single render path (no legacy parser) still
shows the old turns' work evidence.

Per affected conversation, in ONE transaction:

1. Load every message in array order (seq, created_at, id).
2. Expand each ``activity_log`` row into its frames (intra-log ``seq``
   order), inserted at the log row's own position:
   - frame ``at`` rebases to the TRUE WORK START (``settle_at −
     duration_ms``) — the pre-array dumps stamped the settle moment, the
     array row's ``at`` is the birth stamp (execute entry);
   - draft/run span frames (``chat.activity.*`` keys) DROP — 落定即退役
     (the docked plan card / the run receipt is their evidence; the old
     client filtered them at render, so dropping is display-faithful);
   - the frame's intra-log ``seq`` drops (array position carries order);
   - off-shape frames (no activity_id/kind/status) drop, counted.
3. Delete the log rows themselves.
4. Renumber ``messages.seq`` to a clean 1..N across the conversation (seq
   is an order key with no external references — rows are joined by id).
5. Upsert ``message_seq_counters.last_seq = N``.

What it does NOT touch: ``activity_forensics`` rows (already array-era,
never rendered), ``material_beat`` rows (already born-settled single rows),
``candidates_log`` rows (aggregate by design — see the W5 brief Status:
the candidate card is one repaintable surface, not timeline rows).

Dry-run by default — prints the plan (conversations, log rows, frames
materialized/dropped). Pass ``--yes`` to execute.

Usage (from apps/api/):
    uv run python scripts/migrate_activity_log_rows.py           # dry-run
    uv run python scripts/migrate_activity_log_rows.py --yes     # apply
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# Make ``app`` importable when run as a file (apps/api on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Message, MessageSeqCounter  # noqa: E402

ACTIVITY_LOG_TYPE = "activity_log"
ACTIVITY_ROW_TYPE = "activity"
# 落定即退役: span frames whose settled receipt is another surface's
# evidence (the plan card / the run receipt) never materialize.
_RETIRED_SPAN_PREFIX = "chat.activity."
_FRAME_KINDS = {"read", "draft", "run", "repair"}
_FRAME_STATUSES = {"completed", "failed", "cancelled"}


def _parse_stamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _rebase_frame(raw: dict) -> dict | None:
    """One legacy dump frame → the array-row frame shape, or None to drop.

    The dump's ``at`` is the SETTLE moment; the array row's birth stamp is
    the true work start (settle − duration) — the same derivation the old
    client applied at render (ADR-104 排序律), baked into the row here so
    no reader ever re-derives it.
    """
    activity_id = raw.get("activity_id")
    kind = raw.get("kind")
    status = raw.get("status")
    if (
        not isinstance(activity_id, str)
        or kind not in _FRAME_KINDS
        or status not in _FRAME_STATUSES
    ):
        return None
    key = raw.get("key") if isinstance(raw.get("key"), str) else None
    if kind in ("draft", "run") and (key or "").startswith(_RETIRED_SPAN_PREFIX):
        return None
    at = raw.get("at") if isinstance(raw.get("at"), str) else None
    duration_ms = raw.get("duration_ms")
    if not isinstance(duration_ms, (int, float)):
        duration_ms = None
    if at is not None and duration_ms is not None:
        settle_at = _parse_stamp(at)
        if settle_at is not None:
            rebased = datetime.fromtimestamp(
                settle_at.timestamp() - duration_ms / 1000, tz=UTC
            )
            at = rebased.isoformat()
    frame = {
        "activity_id": activity_id,
        "kind": kind,
        "status": status,
        "key": key,
    }
    if at is not None:
        frame["at"] = at
    if isinstance(raw.get("count"), int):
        frame["count"] = raw["count"]
    if duration_ms is not None:
        frame["duration_ms"] = duration_ms
    return frame


async def _load_plan(db) -> dict:
    """The dry-run/apply shared read: per conversation, the log rows and
    their frame expansion counts."""
    log_rows = (
        (
            await db.execute(
                select(Message).where(
                    Message.intent["type"].astext == ACTIVITY_LOG_TYPE
                )
            )
        )
        .scalars()
        .all()
    )
    by_conversation: dict[str, list[Message]] = {}
    for row in log_rows:
        by_conversation.setdefault(str(row.conversation_id), []).append(row)
    plan = {"log_rows": len(log_rows), "conversations": {}}
    for conv_id, rows in by_conversation.items():
        materialized = dropped = 0
        for row in rows:
            frames = (row.intent or {}).get("frames")
            if not isinstance(frames, list):
                dropped += 1  # the whole off-shape dump
                continue
            for raw in frames:
                if isinstance(raw, dict) and _rebase_frame(raw) is not None:
                    materialized += 1
                else:
                    dropped += 1
        plan["conversations"][conv_id] = {
            "log_rows": len(rows),
            "materialized": materialized,
            "dropped": dropped,
        }
    return plan


async def _migrate_conversation(db, conversation_id) -> tuple[int, int]:
    """Expand + renumber one conversation. Returns (materialized, dropped)."""
    rows = (
        (
            await db.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(
                    Message.seq.asc().nulls_last(),
                    Message.created_at.asc(),
                    Message.id.asc(),
                )
            )
        )
        .scalars()
        .all()
    )
    # Build the final array: existing rows in order, log rows replaced by
    # their expanded frames (new Message objects pending insert).
    final: list[Message] = []
    new_rows: list[Message] = []
    materialized = dropped = 0
    log_rows: list[Message] = []
    for row in rows:
        if (row.intent or {}).get("type") != ACTIVITY_LOG_TYPE:
            final.append(row)
            continue
        log_rows.append(row)
        frames = (row.intent or {}).get("frames")
        if not isinstance(frames, list):
            dropped += 1
            continue
        ordered = sorted(
            (f for f in frames if isinstance(f, dict)),
            key=lambda f: f.get("seq") if isinstance(f.get("seq"), (int, float)) else 0,
        )
        for raw in ordered:
            frame = _rebase_frame(raw)
            if frame is None:
                dropped += 1
                continue
            birth = None
            if isinstance(frame.get("at"), str):
                birth = _parse_stamp(frame["at"])
            new_row = Message(
                id=uuid4(),
                conversation_id=conversation_id,
                role="assistant",
                content="",
                attachments=[],
                mentions=[],
                intent={"type": ACTIVITY_ROW_TYPE, "frame": frame},
                created_at=birth or row.created_at or datetime.now(UTC),
            )
            final.append(new_row)
            new_rows.append(new_row)
            materialized += 1
    for row in log_rows:
        await db.delete(row)
    db.add_all(new_rows)
    # Renumber: seq is an order key only — every join goes by id, so a clean
    # 1..N rewrite is safe and keeps the counter honest. Persistent rows
    # mark dirty on attribute assignment; new rows flush with their seq.
    for position, message in enumerate(final, start=1):
        message.seq = position
    await db.flush()
    await db.execute(
        pg_insert(MessageSeqCounter)
        .values(conversation_id=conversation_id, last_seq=len(final))
        .on_conflict_do_update(
            index_elements=["conversation_id"],
            set_={"last_seq": len(final)},
        )
    )
    return materialized, dropped


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="apply (default: dry-run)")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        plan = await _load_plan(db)
    total_log = plan["log_rows"]
    conversations = plan["conversations"]
    total_materialized = sum(c["materialized"] for c in conversations.values())
    total_dropped = sum(c["dropped"] for c in conversations.values())

    print("== migrate_activity_log_rows (ADR-108 W5) ==")
    print(f"legacy activity_log rows : {total_log}")
    print(f"conversations affected   : {len(conversations)}")
    print(f"frames to materialize    : {total_materialized}")
    print(f"frames dropped           : {total_dropped} (落定即退役 spans + off-shape)")
    for conv_id, c in conversations.items():
        print(
            f"  - {conv_id}: {c['log_rows']} log rows → "
            f"{c['materialized']} array rows ({c['dropped']} dropped)"
        )

    if not args.yes:
        print("\nDRY-RUN — no changes written. Re-run with --yes to apply.")
        return
    if total_log == 0:
        print("\nNothing to do.")
        return

    async with AsyncSessionLocal() as db:
        async with db.begin():
            for conv_id in conversations:
                materialized, dropped = await _migrate_conversation(db, conv_id)
                print(f"migrated {conv_id}: {materialized} rows materialized, {dropped} dropped")
    print("\nDone. Verify a replay: open one affected conversation and confirm "
          "the old turns' activity rows render in place.")


if __name__ == "__main__":
    asyncio.run(main())
