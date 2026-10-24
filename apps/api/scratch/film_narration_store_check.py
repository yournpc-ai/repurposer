"""film_narrations 并发五律的 DB 实证 harness（免费；本地 dev Postgres）。

用法（apps/api 下）:
  uv run python scratch/film_narration_store_check.py

覆盖（闸 16 的本地实证层）:
  L1 正常并发: N 个并发 resolve 同一 hash → 恰好 1 个 owner；owner finalize
     后 waiter 全部读到同一 key；行数 == 1。（TTS 单次由 pytest 纯腿 +
     合成路径的 miss-only 合成纪律保证——provider 计数证据归付费面。）
  L2 超时接管 + owner 隔离: owner A 的 lease 过期 → B 接管成功；A 的迟到
     finalize 落 0 行 → A 只删自己的 staging 对象、读到 B 的结果；行与
     文件双向不串台。
  L3 失败不留毒: owner claim 后 fail → 行删除。
  L4 文件丢失自愈: done 行的对象缺失 → 读取 = miss（行删除 + 重新占位）。
  L5 级联: 项目删除 → store 行随之删除。
  L6 过期 owner 的 fail 不得删接管者的行（双条件删除）。
  L7 交错自愈: 两个读者读到同一丢失 done 行、都证实 404；先行者完成自愈
     （删除+占位+finalize 新结果）后，迟到者的自愈删除必须绑定它读到的
     旧行身份（主键+done 状态）落 0 行——不得删并发请求新建的占位或结果，
     随后重读并复用先行者的已提交结果。
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, text as sql_text  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import FilmNarration, Project, User  # noqa: E402
from app.providers import storage  # noqa: E402
from app.tools.film import narration_store as store  # noqa: E402


def _fail(msg: str) -> None:
    raise AssertionError(msg)


async def _fixture() -> tuple[uuid.UUID, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        user = User(email=f"narr-store-check-{uuid.uuid4().hex[:8]}@example.com")
        db.add(user)
        await db.flush()
        project = Project(user_id=user.id, title="narration-store-check")
        db.add(project)
        await db.commit()
        return user.id, project.id


async def _row(project_id, text="Hello world", voice_id="presenter_male"):
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(FilmNarration).where(
                    FilmNarration.project_id == project_id,
                    FilmNarration.content_hash
                    == store.narration_content_hash(
                        text=text,
                        voice_id=voice_id,
                        language="en",
                        config=store.narration_synth_config(),
                    )[0],
                )
            )
        ).scalar_one_or_none()


async def main() -> None:
    # Keep the wait loop fast for the harness.
    store._WAIT_POLL_S = 0.05
    store._WAIT_BUDGET_S = 30.0

    user_id, project_id = await _fixture()
    text, voice = "Hello world", "presenter_male"
    cfg = store.narration_synth_config()

    # L1 正常并发: 8 racers on one hash — exactly one owner wins the INSERT;
    # the rest wait on the placeholder and read the done row after finalize.
    race_text = "race line"
    tasks = [
        asyncio.create_task(
            store.resolve_narration(
                project_id, text=race_text, voice_id=voice, language="en", config=cfg
            )
        )
        for _ in range(8)
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    owners = [t.result() for t in done if t.result().owner_token is not None]
    if len(owners) != 1 or not pending:
        _fail(f"L1: first-completed shape wrong (owners={len(owners)} pending={len(pending)})")
    owner = owners[0]
    # Land a REAL object at the staging key first — done-reads verify the
    # object exists (the self-heal law), so a key with nothing behind it
    # would read as a miss and the waiters would re-claim instead of reuse.
    l1_key = f"narrations/check/{uuid.uuid4().hex}.mp3"
    await storage.save(l1_key, b"harness-bytes", content_type="audio/mpeg")
    key, _dur = await store.finalize_narration(
        project_id,
        text=race_text,
        voice_id=voice,
        language="en",
        owner_token=owner.owner_token,
        staging_key=l1_key,
        duration_s=1.23,
        config=cfg,
    )
    row = await _row(project_id, race_text, voice)
    if row is None or row.status != "done" or row.storage_key != key:
        _fail("L1: finalize did not land the done row")
    rest = await asyncio.gather(*pending)
    results = [t.result() for t in done] + list(rest)
    if sum(1 for r in results if r.owner_token is not None) != 1:
        _fail("L1: more than one owner across the race")
    if not all(r.reusable for r in results if r.owner_token is None):
        _fail("L1: done row did not serve all concurrent readers")
    async with AsyncSessionLocal() as db:
        count = len(
            (
                await db.execute(
                    select(FilmNarration).where(FilmNarration.project_id == project_id)
                )
            ).all()
        )
    if count != 1:
        _fail(f"L1: expected 1 row, got {count}")
    print("L1 ok: one owner, one row, concurrent readers reuse")

    # L2 接管 + owner 隔离: expire the lease, B takes over, A's late finalize
    # lands 0 rows, deletes only its own staging, reads B's result.
    # L6 first (on the L1 done row): a non-owner fail must NOT delete it.
    await store.fail_narration(
        project_id, text=race_text, voice_id=voice, language="en",
        owner_token="whatever",  # not the owner → no-op (double condition)
    )
    row2 = await _row(project_id, race_text, voice)
    if row2 is None:
        _fail("L6: a non-owner fail deleted the row")
    # The L1 object's row is wiped below — reap the object itself so the
    # harness leaves no orphans in dev storage.
    await storage.delete(l1_key)
    # Force expiry then claim as A.
    async with AsyncSessionLocal() as db:
        await db.execute(delete(FilmNarration).where(FilmNarration.project_id == project_id))
        await db.commit()
    claim_a = await store.resolve_narration(
        project_id, text=text, voice_id=voice, language="en", config=cfg
    )
    if claim_a.owner_token is None:
        _fail("L2: A never became owner")
    async with AsyncSessionLocal() as db:
        await db.execute(
            sql_text("UPDATE film_narrations SET lease_expires_at = now() - interval '1s' "
            "WHERE project_id = :p"),
            {"p": project_id},
        )
        await db.commit()
    claim_b = await store.resolve_narration(
        project_id, text=text, voice_id=voice, language="en", config=cfg
    )
    if claim_b.owner_token is None or claim_b.owner_token == claim_a.owner_token:
        _fail("L2: takeover never happened")
    key_b, dur_b = await store.finalize_narration(
        project_id, text=text, voice_id=voice, language="en",
        owner_token=claim_b.owner_token,
        staging_key=f"narrations/check/{uuid.uuid4().hex}-B.mp3",
        duration_s=2.34, config=cfg,
    )
    # A's LATE finalize must lose: it deletes its own staging (a bogus key —
    # delete is best-effort) and reads B's committed (key, duration) PAIR —
    # never its own decode coupled to someone else's audio.
    a_key, a_dur = await store.finalize_narration(
        project_id, text=text, voice_id=voice, language="en",
        owner_token=claim_a.owner_token,
        staging_key=f"narrations/check/{uuid.uuid4().hex}-A-stale.mp3",
        duration_s=9.99, config=cfg,
    )
    if a_key != key_b or abs(a_dur - dur_b) > 1e-6:
        _fail(
            f"L2: expired owner's finalize did not read the winner's pair: "
            f"({a_key}, {a_dur}) != ({key_b}, {dur_b})"
        )
    row3 = await _row(project_id, text, voice)
    if row3 is None or row3.storage_key != key_b or abs(row3.duration_s - 2.34) > 1e-6:
        _fail("L2: the committed row does not carry the takeover's result")
    print("L2 ok: takeover + expired owner isolation (row + result)")

    # L3 失败不留毒
    claim_c = await store.resolve_narration(
        project_id, text="another line", voice_id=voice, language="en", config=cfg
    )
    if claim_c.owner_token is None:
        _fail("L3: claim never landed")
    await store.fail_narration(
        project_id, text="another line", voice_id=voice, language="en",
        owner_token=claim_c.owner_token,
    )
    if (await _row(project_id, "another line", voice)) is not None:
        _fail("L3: failed synthesis left a poison row")
    print("L3 ok: failed synthesis leaves no poison")

    # L4 文件丢失自愈: point the done row at a bogus key → read = miss + re-claim
    async with AsyncSessionLocal() as db:
        await db.execute(
            sql_text("UPDATE film_narrations SET storage_key = 'narrations/check/gone.mp3' "
            "WHERE project_id = :p"),
            {"p": project_id},
        )
        await db.commit()
    claim_d = await store.resolve_narration(
        project_id, text=text, voice_id=voice, language="en", config=cfg
    )
    if claim_d.owner_token is None:
        _fail("L4: lost-object row did not self-heal into a fresh claim")
    if (await _row(project_id, text, voice)) is None:
        _fail("L4: the re-claim's placeholder is missing")
    print("L4 ok: lost object self-heals to a miss")

    # L7 交错自愈: two readers read the SAME lost done-row and both prove the
    # object gone. The first proceeds — heals (delete + placeholder) and the
    # harness finalizes its result — while the second is STILL parked at the
    # existence check. The latecomer's self-heal delete is bound to the row
    # identity it read (primary key + the seen ``done`` status): it must land
    # ZERO rows on the winner's fresh result, then re-read and REUSE it. On
    # the old unconditional delete this leg loses the winner's committed row.
    l7_text = "interleave line"
    claim7 = await store.resolve_narration(
        project_id, text=l7_text, voice_id=voice, language="en", config=cfg
    )
    if claim7.owner_token is None:
        _fail("L7: seed claim never landed")
    seed_obj = f"narrations/check/{uuid.uuid4().hex}-l7seed.mp3"
    await storage.save(seed_obj, b"harness-bytes", content_type="audio/mpeg")
    await store.finalize_narration(
        project_id, text=l7_text, voice_id=voice, language="en",
        owner_token=claim7.owner_token, staging_key=seed_obj,
        duration_s=1.5, config=cfg,
    )
    lost_key = "narrations/check/gone-l7.mp3"
    async with AsyncSessionLocal() as db:
        await db.execute(
            sql_text(
                "UPDATE film_narrations SET storage_key = :k "
                "WHERE project_id = :p AND status = 'done'"
            ),
            {"k": lost_key, "p": project_id},
        )
        await db.commit()
    lost_row = await _row(project_id, l7_text, voice)
    if lost_row is None:
        _fail("L7: seed row missing")
    await storage.delete(seed_obj)

    # Sequence the two readers through the existence check: both must ARRIVE
    # (⇒ both read the same lost row) before the first proceeds; the second
    # stays parked until the winner's result is committed. Any existence
    # check on another key (the re-read of the winner's object) rides the
    # real storage seat.
    real_exists = store._storage_exists
    arrived = 0
    both_arrived = asyncio.Event()
    release_latecomer = asyncio.Event()

    async def _sequenced_exists(key):
        nonlocal arrived
        if key != lost_key:
            return await real_exists(key)
        arrived += 1
        if arrived == 1:
            await both_arrived.wait()
        else:
            both_arrived.set()
            await release_latecomer.wait()
        return False

    store._storage_exists = _sequenced_exists
    try:
        racers = [
            asyncio.create_task(
                store.resolve_narration(
                    project_id, text=l7_text, voice_id=voice, language="en", config=cfg
                )
            )
            for _ in range(2)
        ]
        await asyncio.wait_for(both_arrived.wait(), timeout=10)
        done7, pending7 = await asyncio.wait(racers, return_when=asyncio.FIRST_COMPLETED)
        winners = [t.result() for t in done7]
        if len(winners) != 1 or winners[0].owner_token is None:
            _fail("L7: the first reader did not heal into a fresh claim")
        winner_key = f"narrations/check/{uuid.uuid4().hex}-l7win.mp3"
        await storage.save(winner_key, b"harness-bytes", content_type="audio/mpeg")
        committed_key, committed_dur = await store.finalize_narration(
            project_id, text=l7_text, voice_id=voice, language="en",
            owner_token=winners[0].owner_token, staging_key=winner_key,
            duration_s=2.5, config=cfg,
        )
        release_latecomer.set()
        late = (await asyncio.gather(*pending7))[0]
    finally:
        store._storage_exists = real_exists
    # The latecomer's bound delete reaped NOTHING of the winner's world: it
    # re-read the committed result and rides it — no new claim, no loss.
    if late.owner_token is not None:
        _fail("L7: the latecomer re-claimed over the winner's committed result")
    if late.storage_key != committed_key or abs((late.duration_s or 0) - committed_dur) > 1e-6:
        _fail("L7: the latecomer did not reuse the winner's committed pair")
    row7 = await _row(project_id, l7_text, voice)
    if row7 is None or row7.status != "done" or row7.storage_key != committed_key:
        _fail("L7: the winner's committed row was reaped by the late self-heal")
    if row7.id == lost_row.id:
        _fail("L7: the lost row itself survived the heal")
    await storage.delete(winner_key)
    print("L7 ok: interleaved self-heal deletes bind the read identity")

    # L6 already proven above (non-owner fail no-op). L5 cascade:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Project).where(Project.id == project_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    async with AsyncSessionLocal() as db:
        remaining = (
            await db.execute(
                select(FilmNarration).where(FilmNarration.project_id == project_id)
            )
        ).all()
    if remaining:
        _fail("L5: project delete did not cascade the store rows")
    print("L5 ok: project cascade reaps the store")
    print("ALL LEGS GREEN")


if __name__ == "__main__":
    asyncio.run(main())
