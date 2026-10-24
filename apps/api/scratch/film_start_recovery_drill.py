"""F3 断流恢复本地演练的种子/清理座（免费，零 LLM，零付费）——2026-10-22。

把「后端已接受但回执丢失」的两种世界状态种进 R3 smoke fixture 项目 R 的
对话（隔离 fixture，不碰真实项目），node 侧演练脚本随即用**真实的**
`reconcileStartAfterAbort`（strip-types 直接 import TS 源码）打**真实的**
本地 API（127.0.0.1:8000）验证三态决策的线形。每个子命令向 stdout 打印
JSON；种子 id 同时落 ``/tmp/f3_drill_state.json`` 供 ``cleanup`` 按 id 删
（WorkflowRun.context 是 generic JSON，无 .astext 可筛），另按内容前缀
"F3 drill" 兜底扫一遍，幂等。

  case1   原 Start 成功且已有新 pending：已答 task_book（带真实 run 行
          的 workflow_run_id）+ 更新的未答 question（成为 pending）
  case2   原请求处理中：未答 task_book（pending，无 run）；先清 case1
  cleanup 删除全部演练行（幂等）

Run: cd apps/api && uv run python scratch/film_start_recovery_drill.py <cmd>
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.database import AsyncSessionLocal
from app.models.schemas import WorkflowStatus
from app.models.tables import Conversation, Message, WorkflowRun
from sqlalchemy import delete, select

PROJECT_R = uuid.UUID("fbb61c92-c86e-4e44-a82d-01e689f8d0e3")
CONTENT_PREFIX = "F3 drill"
STATE_FILE = Path("/tmp/f3_drill_state.json")
BASE = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)


async def _conv_id(db) -> uuid.UUID:
    conv = (
        await db.execute(select(Conversation).where(Conversation.project_id == PROJECT_R))
    ).scalars().first()
    assert conv is not None, "fixture project R conversation missing — run the smoke seed first"
    return conv.id


async def _cleanup(db) -> int:
    deleted = 0
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        for mid in state.get("message_ids", []):
            res = await db.execute(delete(Message).where(Message.id == uuid.UUID(mid)))
            deleted += res.rowcount or 0
        for rid in state.get("run_ids", []):
            res = await db.execute(delete(WorkflowRun).where(WorkflowRun.id == uuid.UUID(rid)))
            deleted += res.rowcount or 0
        STATE_FILE.unlink()
    # 兜底：按内容前缀扫（STATE_FILE 丢了也能清干净）。
    res = await db.execute(
        delete(Message).where(
            Message.conversation_id == await _conv_id(db),
            Message.content.like(f"{CONTENT_PREFIX}%"),
        )
    )
    deleted += res.rowcount or 0
    await db.commit()
    return deleted


async def case1() -> dict:
    """原 Start 成功 + 已有新 pending：已答 task_book 带 run + 更新未答行。"""
    async with AsyncSessionLocal() as db:
        await _cleanup(db)
        conv_id = await _conv_id(db)
        run = WorkflowRun(
            project_id=PROJECT_R,
            status=WorkflowStatus.COMPLETED,
            context={"type": "f3_drill", "note": "simulated accepted start"},
            progress=100,
        )
        db.add(run)
        await db.flush()
        original = Message(
            conversation_id=conv_id,
            role="assistant",
            content=f"{CONTENT_PREFIX} case1 — original start dock",
            intent={"type": "f3_drill"},
            question={"kind": "task_book", "question": "F3 drill original dock", "options": []},
            answer={"kind": "start"},
            workflow_run_id=run.id,
            created_at=BASE,
        )
        newer = Message(
            conversation_id=conv_id,
            role="assistant",
            content=f"{CONTENT_PREFIX} case1 — newer pending question",
            intent={"type": "f3_drill"},
            question={
                "kind": "question",
                "question": "F3 drill newer question",
                "options": [{"id": "a", "label": "A"}],
            },
            answer=None,
            created_at=BASE + timedelta(minutes=1),
        )
        db.add_all([original, newer])
        await db.commit()
        result = {
            "case": "case1",
            "question_id": str(original.id),
            "run_id": str(run.id),
            "newer_pending_id": str(newer.id),
        }
        STATE_FILE.write_text(json.dumps({
            **result,
            "message_ids": [str(original.id), str(newer.id)],
            "run_ids": [str(run.id)],
        }))
        return result


async def case2() -> dict:
    """原请求处理中：未答 task_book 成为 pending（无 run）。先清 case1。"""
    async with AsyncSessionLocal() as db:
        await _cleanup(db)
        conv_id = await _conv_id(db)
        original = Message(
            conversation_id=conv_id,
            role="assistant",
            content=f"{CONTENT_PREFIX} case2 — pending start dock",
            intent={"type": "f3_drill"},
            question={"kind": "task_book", "question": "F3 drill pending dock", "options": []},
            answer=None,
            created_at=BASE,
        )
        db.add(original)
        await db.commit()
        result = {"case": "case2", "question_id": str(original.id)}
        STATE_FILE.write_text(json.dumps({
            **result,
            "message_ids": [str(original.id)],
            "run_ids": [],
        }))
        return result


async def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cleanup"
    if cmd == "case1":
        print(json.dumps(await case1()))
    elif cmd == "case2":
        print(json.dumps(await case2()))
    elif cmd == "cleanup":
        async with AsyncSessionLocal() as db:
            print(json.dumps({"deleted": await _cleanup(db)}))
    else:
        raise SystemExit(f"unknown command {cmd!r}")


asyncio.run(main())
