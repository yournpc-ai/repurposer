"""Final Hardening B3 — live acceptance driver v2 (walkthrough 拍1–拍6b + billing).

v2 forensics (2026-09-24, after drive 1): every edit beat records WHERE the op
actually landed (assistant_message.intent.target_output_id) vs the @output pin
— pin divergence is first-class evidence, not a silent INVALID. Ops deltas are
read on BOTH clips. Quote selection is robust to word-level caption cues.

Runs against the live local stack (API :8000 + resident worker). Real fixture
video, REAL ASR, REAL plan → run → render chain, REAL MiniMax chat turns.

Usage:
    cd apps/api && uv run python ../../scratch/precise_edit_live_drive.py
Env:
    KEEP=1   keep the scenario project (skip cleanup)
"""

import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent / "apps" / "api"
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(API_DIR / "scripts"))

from sqlalchemy import select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Asset, Operation, Output, RenderStatus  # noqa: E402
from app.pipeline.edit_ops import kept_range  # noqa: E402

import chat_scenarios as cs  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []  # (beat, verdict, evidence)


def record(beat: str, ok: bool, evidence: object = "", *, invalid: bool = False) -> None:
    verdict = "INVALID" if invalid else ("PASS" if ok else "RED")
    text = evidence if isinstance(evidence, str) else json.dumps(evidence, ensure_ascii=False)[:700]
    RESULTS.append((beat, verdict, text))
    print(f"\n=== {beat}: {verdict} ===\n{text[:700]}\n", flush=True)


# ---- DB ground-truth helpers ------------------------------------------------


async def db_output(oid: str | uuid.UUID) -> dict | None:
    """Plain-dict snapshot (no detached ORM objects cross the session)."""
    async with AsyncSessionLocal() as db:
        row = await db.get(Output, uuid.UUID(str(oid)))
        if row is None:
            return None
        return {
            "id": str(row.id),
            "work_id": str(row.work_id) if row.work_id else None,
            "archived_at": row.archived_at,
            "render_status": row.render_status,
            "render_spec": row.render_spec,
        }


async def db_ops(oid: str | uuid.UUID) -> list[dict]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Operation)
                .where(Operation.output_id == uuid.UUID(str(oid)))
                .order_by(Operation.seq)
            )
        ).scalars().all()
        return [
            {"op": r.op, "seq": r.seq, "undone_at": r.undone_at, "params": r.params}
            for r in rows
        ]


async def ops_count(oid: str) -> int:
    return len(await db_ops(oid))


async def wait_asset_completed(asset_id: str, timeout: float = 420.0) -> bool:
    from app.models.tables import AssetStatus

    for _ in range(int(timeout / 4)):
        async with AsyncSessionLocal() as db:
            asset = await db.get(Asset, uuid.UUID(asset_id))
            if asset is not None and asset.processing_status == AssetStatus.COMPLETED:
                return True
            if asset is not None and asset.processing_status == AssetStatus.FAILED:
                return False
        await asyncio.sleep(4)
    return False


async def wait_render_done(oid: str, timeout: float = 600.0) -> str:
    terminal = {RenderStatus.COMPLETED, RenderStatus.FAILED}
    for _ in range(int(timeout / 5)):
        row = await db_output(oid)
        if row is not None and row["render_status"] in terminal:
            return str(row["render_status"].value)
        await asyncio.sleep(5)
    return "TIMEOUT"


def cues_of(spec: dict) -> list[dict]:
    return list((spec or {}).get("caption_track") or [])


# ---- chat helpers ------------------------------------------------------------


def assistant_text(turn: dict) -> str:
    return ((turn.get("assistant_message") or {}).get("content")) or ""


def intent_of(turn: dict) -> dict:
    return ((turn.get("assistant_message") or {}).get("intent")) or {}


async def chat_edit(ctx: cs.Ctx, pid: str, message: str, pin: str | None = None) -> dict:
    extra = {}
    if pin:
        extra["mentions"] = [{"type": "output", "id": pin, "label": "clip"}]
    return await ctx.chat(pid, message, **extra)


def first_multiword_cue(track: list[dict], *, skip: int = 0) -> dict | None:
    """Word-level cue streams make cue[0] a one-letter quote ('I') — pick the
    first cue with ≥2 words so the resolver's exact tier has something to
    bite on."""
    for c in track[skip:]:
        if len(str(c.get("text", "")).split()) >= 2:
            return c
    return track[skip] if len(track) > skip else None


# ---- main --------------------------------------------------------------------


async def main() -> None:
    user_id = await cs.make_user()
    ctx = cs.Ctx(user_id, keep=bool(os.getenv("KEEP")))
    fixture_prefix = f"scenario/final-hard-{uuid.uuid4().hex[:8]}"
    pid = await ctx.new_project("Final-Hardening B3 live drive v2")
    try:
        # ---- Setup: real video → real ASR → real plan → real run → 2 clips
        src_key = await cs.copy_fixture(cs.REMIX_SOURCE_KEY, fixture_prefix)
        asset_id = await cs.seed_asset(
            pid, user_id, cs.AssetType.VIDEO, "b3-talk.mp4", file_url=src_key
        )
        ok = await wait_asset_completed(asset_id)
        record("setup: ASR", ok, "worker processed the real fixture video", invalid=not ok)
        if not ok:
            return

        turn = await ctx.chat(pid, "把这段演讲剪成 2 条竖屏短片，配字幕。")
        run_id = None
        for probe in ("开始生成", "start"):
            turn = await ctx.chat(pid, probe)
            runs = await ctx.runs(pid)
            if runs:
                run_id = runs[0]["id"]
                break
        record("setup: plan→run", run_id is not None,
               {"assistant": assistant_text(turn)[:300], "run_id": run_id},
               invalid=run_id is None)
        if not run_id:
            return

        state = await cs.wait_run_terminal(run_id, timeout=1500.0)
        record("setup: run terminal", "completed" in state.lower() or "COMPLETED" in state,
               {"state": state})

        results = await ctx.results(pid)
        clips = [o for o in results.get("outputs", []) if o["type"] == "clip"]
        clips.sort(key=lambda o: o.get("created_at") or "")
        if len(clips) < 2:
            record("setup: 2 clips", False, {"outputs": [o["type"] for o in results.get("outputs", [])]})
            return
        for c in clips[:2]:
            rs = await wait_render_done(c["id"], timeout=900.0)
            record(f"setup: render {c['id'][:8]}", rs == "completed", {"render_status": rs})
        clip_ids = [str(c["id"]) for c in clips[:2]]
        clip1, clip2 = clip_ids

        row1 = await db_output(clip1)
        track = cues_of(row1["render_spec"])
        record("setup: caption_track", len(track) >= 4,
               {"cues": len(track), "first": (track[0]["text"] if track else None)})
        if len(track) < 4:
            return

        async def edit_beat(beat: str, message: str, pin: str | None,
                            expect_op: str, verify) -> dict:
            """One precise-edit turn with full target forensics. Returns the
            intent dict. Mutation is located via the intent stamp; pin honor
            is separate evidence."""
            n0 = {cid: await ops_count(cid) for cid in clip_ids}
            turn = await chat_edit(ctx, pid, message, pin)
            intent = intent_of(turn)
            target = intent.get("target_output_id")
            n1 = {cid: await ops_count(cid) for cid in clip_ids}
            landed = {cid: n1[cid] - n0[cid] for cid in clip_ids if n1[cid] > n0[cid]}
            ok, extra = await verify(target)
            ev = {
                "pinned": pin, "intent_target": target,
                "pin_honored": (pin is None or target == pin),
                "ops_landed": landed, "intent_kind": intent.get("kind"),
                "assistant": assistant_text(turn)[:280],
                **extra,
            }
            record(beat, ok, ev, invalid=(not landed and not ok))
            return intent

        # ---- 拍 1  remove_range (no pin — prose resolves "第一条")
        # Word-level cue streams make any single cue a one-word quote (drive 1
        # hit "I", drive 2 "But") — join the first cues into a 4-token opening
        # phrase so the resolver's exact tier has a real substring to bite.
        quote = " ".join(c["text"] for c in track[:6]).strip()
        if len(quote.split()) > 6:
            quote = " ".join(quote.split()[:5])

        want_start = float(track[0]["start"])
        want_end = float(track[min(5, len(track) - 1)]["end"])

        async def v1(target):
            if not target:
                return False, {"why": "no target stamped"}
            ops = [o for o in await db_ops(target)
                   if o["op"] == "remove_range" and o["undone_at"] is None]
            if not ops:
                return False, {"why": "no remove_range journaled"}
            p = ops[-1]["params"] or {}
            covered = (abs(float(p.get("start", -1)) - want_start) < 0.75
                       and float(p.get("end", -1)) <= want_end + 0.75
                       and float(p.get("end", 0)) > want_start)
            echo_ok = bool(re.search(r"\d+(\.\d+)?\s*[–\-~]\s*\d+(\.\d+)?\s*s", assistant_text_holder[0]))
            return covered, {"op_span": [p.get("start"), p.get("end")],
                             "want_span_start": want_start, "interval_echo": echo_ok}

        assistant_text_holder = [""]
        n0 = {cid: await ops_count(cid) for cid in clip_ids}
        turn = await chat_edit(ctx, pid, f"把第一条短片开头那句『{quote}』删掉", clip1)
        assistant_text_holder[0] = assistant_text(turn)
        intent = intent_of(turn)
        target = intent.get("target_output_id")
        n1 = {cid: await ops_count(cid) for cid in clip_ids}
        landed = {cid: n1[cid] - n0[cid] for cid in clip_ids if n1[cid] > n0[cid]}
        ok, extra = await v1(target)
        record("拍1 remove_range", ok,
               {"pinned": clip1, "intent_target": target,
                "pin_honored": target == clip1, "ops_landed": landed,
                "quote": quote[:60], **extra, "assistant": assistant_text(turn)[:280]},
               invalid=not landed and not ok)
        if target and landed:
            rs = await wait_render_done(target)
            record("拍1 re-render", rs == "completed", {"render_status": rs})

        # ---- 拍 1b  cross-cue quote (pin clip1)
        # Assertion = the journaled op's span COVERS the quoted cues' span
        # (word-level cue streams repeat tokens — a text-absence check is
        # meaningless there; drive 2's false RED came from that).
        row1 = await db_output(clip1)
        track = cues_of(row1["render_spec"])
        if len(track) >= 6:
            i0 = 2
            span_cues = track[i0:i0 + 3]
            q = " ".join(c["text"] for c in span_cues).strip()
            want_start, want_end = float(span_cues[0]["start"]), float(span_cues[-1]["end"])

            async def v1b(target, _ws=want_start, _we=want_end):
                if not target:
                    return False, {"why": "no target"}
                ops = [o for o in await db_ops(target)
                       if o["op"] == "remove_range" and o["undone_at"] is None]
                if not ops:
                    return False, {"why": "no remove_range journaled"}
                p = ops[-1]["params"] or {}
                covered = (abs(float(p.get("start", -1)) - _ws) < 0.75
                           and abs(float(p.get("end", -1)) - _we) < 0.75)
                return covered, {"op_span": [p.get("start"), p.get("end")],
                                 "want_span": [_ws, _we], "covered": covered}

            intent = await edit_beat("拍1b 跨cue", f"『{q}』这段也删掉", clip1, "remove_range", v1b)
            if intent.get("target_output_id"):
                await wait_render_done(intent["target_output_id"])
        else:
            record("拍1b 跨cue", False, "caption_track too short")

        # ---- 拍 1b  punctuation/case-tolerant quote (pin clip1)
        row1 = await db_output(clip1)
        track = cues_of(row1["render_spec"])
        if len(track) >= 10:
            span_cues = track[6:9]
            raw_q = " ".join(c["text"] for c in span_cues).strip()
            q = re.sub(r"[^0-9A-Za-z一-鿿 ]", "", raw_q).upper()
            ws, we = float(span_cues[0]["start"]), float(span_cues[-1]["end"])

            async def v1c(target, _ws=ws, _we=we):
                if not target:
                    return False, {"why": "no target"}
                ops = [o for o in await db_ops(target)
                       if o["op"] == "remove_range" and o["undone_at"] is None]
                if not ops:
                    return False, {"why": "no remove_range journaled"}
                p = ops[-1]["params"] or {}
                covered = (abs(float(p.get("start", -1)) - _ws) < 0.75
                           and abs(float(p.get("end", -1)) - _we) < 0.75)
                return covered, {"op_span": [p.get("start"), p.get("end")],
                                 "want_span": [_ws, _we], "quote": ""}

            intent = await edit_beat("拍1b 标点/大小写容忍", f"把『{q}』删掉", clip1, "remove_range", v1c)
            if intent.get("target_output_id"):
                await wait_render_done(intent["target_output_id"])
        else:
            record("拍1b 标点/大小写容忍", False, "caption_track too short")

        # ---- 拍 1b  miss → honest refusal, zero mutation anywhere
        specs0 = {cid: json.dumps((await db_output(cid))["render_spec"], sort_keys=True) for cid in clip_ids}
        n0 = {cid: await ops_count(cid) for cid in clip_ids}
        turn = await chat_edit(ctx, pid, "把『zzqq 这句话根本不存在』删掉", clip1)
        n1 = {cid: await ops_count(cid) for cid in clip_ids}
        specs1 = {cid: json.dumps((await db_output(cid))["render_spec"], sort_keys=True) for cid in clip_ids}
        record("拍1b 未命中拒绝", n0 == n1 and specs0 == specs1,
               {"ops_delta": {cid: n1[cid] - n0[cid] for cid in clip_ids},
                "specs_unchanged": specs0 == specs1,
                "assistant": assistant_text(turn)[:280]})

        # ---- 拍 1b  ambiguous → refusal, zero guess
        row1 = await db_output(clip1)
        track = cues_of(row1["render_spec"])
        counts: dict[str, int] = {}
        for c in track:
            for w in set(re.findall(r"[a-zA-Z']{2,}", c["text"].lower())):
                counts[w] = counts.get(w, 0) + 1
        amb = next((w for w, n in sorted(counts.items(), key=lambda kv: -kv[1]) if n >= 2), None)
        if amb:
            n0 = {cid: await ops_count(cid) for cid in clip_ids}
            turn = await chat_edit(ctx, pid, f"把『{amb}』删掉", clip1)
            n1 = {cid: await ops_count(cid) for cid in clip_ids}
            record("拍1b 多义拒绝", n0 == n1,
                   {"word": amb, "cue_occurrences": counts[amb],
                    "ops_delta": {cid: n1[cid] - n0[cid] for cid in clip_ids},
                    "assistant": assistant_text(turn)[:280]})
        else:
            record("拍1b 多义拒绝", False, "no repeated word found in cues")

        # ---- 拍 2  set_trim via @output pin on clip2
        row2 = await db_output(clip2)
        rng_before = kept_range(row2["render_spec"])
        rng1_before = kept_range((await db_output(clip1))["render_spec"])

        async def v2(target):
            if not target:
                return False, {"why": "no target"}
            row = await db_output(target)
            rng_after = kept_range(row["render_spec"])
            before = rng_before if target == clip2 else rng1_before
            delta = (before[1] - rng_after[1]) if (before and rng_after) else None
            ops = [o for o in await db_ops(target) if o["op"] == "set_trim" and o["undone_at"] is None]
            return bool(ops) and delta is not None and abs(delta - 3.0) < 0.6, {
                "kept_before": before, "kept_after": rng_after, "delta": delta}

        intent = await edit_beat("拍2 set_trim", "这条再短 3 秒", clip2, "set_trim", v2)
        if intent.get("target_output_id"):
            rs = await wait_render_done(intent["target_output_id"])
            record("拍2 re-render", rs == "completed", {"render_status": rs})

        # ---- 拍 3  set_caption_style karaoke (pin clip1) + Comic Sans refusal
        async def v3(target):
            if not target:
                return False, {"why": "no target"}
            row = await db_output(target)
            preset = (row["render_spec"] or {}).get("caption_style_preset")
            ops = [o for o in await db_ops(target)
                   if o["op"] == "set_caption_style" and o["undone_at"] is None]
            return preset == "karaoke-highlight" and bool(ops), {"preset": preset}

        intent = await edit_beat("拍3 karaoke", "字幕换成卡拉 OK 高亮那种样式", clip1, "set_caption_style", v3)
        if intent.get("target_output_id"):
            rs = await wait_render_done(intent["target_output_id"])
            record("拍3 re-render", rs == "completed", {"render_status": rs})

        n0 = {cid: await ops_count(cid) for cid in clip_ids}
        presets0 = {cid: ((await db_output(cid))["render_spec"] or {}).get("caption_style_preset") for cid in clip_ids}
        turn = await chat_edit(ctx, pid, "字幕换成黄色 Comic Sans 超大号", clip1)
        n1 = {cid: await ops_count(cid) for cid in clip_ids}
        presets1 = {cid: ((await db_output(cid))["render_spec"] or {}).get("caption_style_preset") for cid in clip_ids}
        record("拍3 Comic Sans 拒绝", n0 == n1 and presets0 == presets1,
               {"presets": presets1, "ops_delta": {cid: n1[cid] - n0[cid] for cid in clip_ids},
                "assistant": assistant_text(turn)[:280]})

        # ---- 拍 4  set_title (pin clip1)
        NEW_TITLE = "AI 时代的内容创作"

        async def v4(target):
            if not target:
                return False, {"why": "no target"}
            row = await db_output(target)
            title = ((row["render_spec"] or {}).get("title") or {}).get("text")
            ops = [o for o in await db_ops(target) if o["op"] == "set_title" and o["undone_at"] is None]
            return title == NEW_TITLE and bool(ops), {"title": title}

        intent = await edit_beat("拍4 set_title", f"标题改成『{NEW_TITLE}』", clip1, "set_title", v4)
        title_target = intent.get("target_output_id")
        title_landed = bool(title_target) and any(
            o["op"] == "set_title" and o["undone_at"] is None
            for o in await db_ops(title_target or clip1)
        )
        if title_target:
            rs = await wait_render_done(title_target)
            record("拍4 re-render", rs == "completed", {"render_status": rs})

        # ---- 拍 5  REST undo + journal (on the row the title edit hit, else clip1)
        undo_id = title_target or clip1
        spec0 = json.dumps((await db_output(undo_id))["render_spec"], sort_keys=True)
        res = await ctx.client.post(f"/outputs/{undo_id}/operations/undo")
        spec1 = json.dumps((await db_output(undo_id))["render_spec"], sort_keys=True)
        journal = await db_ops(undo_id)
        head = journal[-1] if journal else None
        res_j = await ctx.client.get(f"/outputs/{undo_id}/operations")
        undone_reverts = spec0 != spec1
        if title_landed:
            row = await db_output(undo_id)
            undone_reverts = ((row["render_spec"] or {}).get("title") or {}).get("text") != NEW_TITLE
        record("拍5 undo+journal",
               res.status_code == 200 and undone_reverts
               and head is not None and head["undone_at"] is not None
               and res_j.status_code == 200,
               {"undo_status": res.status_code, "spec_reverted": undone_reverts,
                "head_op": head["op"] if head else None,
                "head_undone": bool(head and head["undone_at"]),
                "journal_rows": len(journal)})

        # The undo re-pends a render — let it finish or the revise door
        # refuses with 422 "the node is running its program" (drive 2).
        await wait_render_done(undo_id, timeout=900.0)

        # ---- 拍 6  rerun (deterministic graph-revise door) → archive invariants
        graph = await ctx.graph(pid)
        gen = next(
            (n for n in graph.get("nodes", [])
             if (n.get("spec") or {}).get("tool") == "select_clips"),
            None,
        )
        record("拍6 setup: select_clips node", gen is not None,
               {"nodes": [(n.get("type"), (n.get("spec") or {}).get("tool")) for n in graph.get("nodes", [])]})
        if gen is None:
            return
        runs0 = {r["id"] for r in await ctx.runs(pid)}  # BEFORE the revise — the 202 births the run synchronously (drive 3's snapshot came after and never saw it)
        res = await ctx.client.post(
            f"/projects/{pid}/graph/revise",
            json={"node_id": gen["id"], "prompt": "换一组不同的片段，突出别的论点"},
        )
        record("拍6 revise accepted", res.status_code == 202,
               {"status": res.status_code, "body": res.text[:400]})
        if res.status_code != 202:
            return
        new_run = None
        for _ in range(30):
            runs = await ctx.runs(pid)
            fresh = [r for r in runs if r["id"] not in runs0]
            if fresh:
                new_run = fresh[0]["id"]
                break
            await asyncio.sleep(2)
        if new_run:
            state = await cs.wait_run_terminal(new_run, timeout=1500.0)
            record("拍6 rerun terminal", "completed" in state.lower(), {"state": state})
        else:
            record("拍6 rerun spawned", False, "no new run appeared within 60s")
            return

        old1, old2 = await db_output(clip1), await db_output(clip2)
        results = await ctx.results(pid)
        active = [o for o in results.get("outputs", []) if o["type"] == "clip"]
        work_ids = {str((await db_output(o["id"]))["work_id"]) for o in active}
        old_work = old1["work_id"]
        res_old = await ctx.client.get(f"/outputs/{clip1}")
        record("拍6 归档不变量",
               old1["archived_at"] is not None and old2["archived_at"] is not None
               and len(active) >= 1 and work_ids == {old_work}
               and res_old.status_code == 200,
               {"old1_archived": old1["archived_at"] is not None,
                "old2_archived": old2["archived_at"] is not None,
                "active_clips": len(active), "work_ids": work_ids,
                "old_readable": res_old.status_code})
        for c in active:
            await wait_render_done(c["id"], timeout=900.0)

        # ---- 拍 6b  archived immutability on the REAL rerun's old versions
        res = await ctx.client.post(
            f"/outputs/{clip1}/operations",
            json={"ops": [{"op": "set_title", "params": {"text": "tamper", "enabled": True}}]},
        )
        op_409 = res.status_code
        res = await ctx.client.post(f"/outputs/{clip1}/operations/undo")
        undo_409 = res.status_code
        res = await ctx.client.put(f"/outputs/{clip1}", json={"payload": {"title": "tamper"}})
        put_409 = res.status_code
        res = await ctx.client.post(f"/outputs/{clip1}/regenerate", json={})
        regen_409 = res.status_code
        record("拍6b 归档不可变",
               {op_409, undo_409, put_409, regen_409} == {409},
               {"operations": op_409, "undo": undo_409, "put": put_409, "regenerate": regen_409})

        # ---- billing persistence (披露分级面: PUT/GET round-trip)
        res = await ctx.client.put("/auth/settings", json={"confirm_strategy": "never"})
        got1 = res.json().get("confirm_strategy") if res.status_code == 200 else res.status_code
        res = await ctx.client.get("/auth/settings")
        got2 = res.json().get("confirm_strategy")
        res = await ctx.client.put("/auth/settings", json={"confirm_strategy": "always"})
        got3 = res.json().get("confirm_strategy") if res.status_code == 200 else res.status_code
        res = await ctx.client.get("/auth/settings")
        got4 = res.json().get("confirm_strategy")
        record("billing 持久化",
               got1 == got2 == "never" and got3 == got4 == "always",
               {"write_never": got1, "read_never": got2,
                "write_always": got3, "read_always": got4})
    finally:
        print("\n\n========== SUMMARY ==========")
        for beat, verdict, _ in RESULTS:
            print(f"{verdict:8s} {beat}")
        await ctx.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
