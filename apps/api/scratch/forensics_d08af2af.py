"""Read-only forensics for project d08af2af — film multi-turn edit incident.

Dumps: messages (seq order), pending_brief film envelope, runs+context film
keys, workflow steps, outputs render_spec scene summary. NO writes.
"""

import asyncio
import json

import asyncpg

PROJECT = "d08af2af-02d4-4a04-9483-4db03ff6ef0d"


def _j(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return v


def _scene_line(s):
    if not isinstance(s, dict):
        return str(s)[:120]
    keys = {k: s[k] for k in (
        "id", "type", "seconds", "dark", "motion", "enter", "word", "lines",
        "narration", "background", "polarity", "theme", "label", "name",
        "title", "sub", "lead", "cards", "roll", "frames",
    ) if k in s}
    for k in ("lines", "cards"):
        if isinstance(keys.get(k), list):
            keys[k] = [str(x)[:40] for x in keys[k]]
    if isinstance(keys.get("narration"), str):
        keys["narration"] = keys["narration"][:50]
    return json.dumps(keys, ensure_ascii=False, default=str)


def _brief_summary(pb):
    pb = _j(pb)
    if not isinstance(pb, dict):
        return {"_raw_type": type(pb).__name__}
    out = {"_keys": sorted(pb.keys())}
    fds = pb.get("film_design_state") or {}
    if isinstance(fds, dict):
        env = {"_keys": sorted(fds.keys())}
        for k in ("version", "created_via", "change_set", "base_ref"):
            if k in fds:
                env[k] = fds[k]
        params = fds.get("params") or {}
        env["params"] = params
        board = fds.get("board") or {}
        scenes = board.get("scenes") or []
        env["board_scenes"] = [_scene_line(s) for s in scenes]
        env["board_keys"] = sorted(board.keys()) if isinstance(board, dict) else None
        out["film_design_state"] = env
    for k in ("film_kept_frames", "film_kept_reveal_onsets", "film_review_hold",
              "film_storyboard_params", "film_storyboard_digest"):
        if k in pb:
            out[k] = pb[k]
    tasks = pb.get("tasks")
    if tasks:
        out["tasks"] = [
            {"kind": t.get("kind"), "name": t.get("name"),
             "slot": {kk: vv for kk, vv in (t.get("slot") or {}).items()
                      if kk in ("voiceover", "music_mood", "aspect", "text",
                                "verbatim", "target_seconds", "scene_count",
                                "source_url", "asset_ids")},
             }
            for t in tasks if isinstance(t, dict)
        ]
    return out


async def main():
    conn = await asyncpg.connect(
        "postgresql://postgres:postgres@localhost:5432/repurposer"
    )

    print("=" * 100)
    print("PROJECT ROW")
    proj = await conn.fetchrow(
        "SELECT id, title, status, language, created_at, updated_at, pending_brief IS NOT NULL AS has_pending FROM projects WHERE id=$1",
        PROJECT)
    print(dict(proj) if proj else "NOT FOUND")

    print("=" * 100)
    print("MESSAGES (seq order)")
    msgs = await conn.fetch(
        """SELECT m.id, m.seq, m.created_at, m.role, m.content, m.intent,
                  m.question IS NOT NULL AS has_q, m.answer IS NOT NULL AS has_a,
                  m.workflow_run_id, m.turn_state
           FROM messages m JOIN conversations c ON c.id = m.conversation_id
           WHERE c.project_id=$1 ORDER BY m.seq NULLS LAST, m.created_at""",
        PROJECT)
    for m in msgs:
        intent = _j(m["intent"])
        trig = None
        if isinstance(intent, dict):
            trig = intent.get("trigger")
        content = (m["content"] or "").replace("\n", " ⏎ ")
        print(f"\n--- seq={m['seq']} {m['created_at']} role={m['role']} id={str(m['id'])[:8]} "
              f"run={str(m['workflow_run_id'])[:8] if m['workflow_run_id'] else '-'} "
              f"turn={m['turn_state']} q={m['has_q']}/{m['has_a']} trigger={trig}")
        print(f"    {content[:1500]}")

    print("=" * 100)
    print("PENDING_BRIEF (current live)")
    pb = await conn.fetchval("SELECT pending_brief FROM projects WHERE id=$1", PROJECT)
    print(json.dumps(_brief_summary(pb), ensure_ascii=False, indent=1, default=str)[:8000])

    print("=" * 100)
    print("RUNS")
    runs = await conn.fetch(
        "SELECT id, status, error, context, created_at, updated_at FROM workflow_runs WHERE project_id=$1 ORDER BY created_at",
        PROJECT)
    for r in runs:
        ctx = _j(r["context"]) or {}
        fsp = ctx.get("film_storyboard_params")
        print(f"\n--- run {r['id']} {r['created_at']} status={r['status']} err={str(r['error'])[:200]}")
        print("    ctx keys:", sorted(ctx.keys()))
        print("    film_storyboard_params:", json.dumps(fsp, ensure_ascii=False, default=str)[:600])
        for k in ("film_review_hold", "film_kept_frames", "film_kept_reveal_onsets",
                  "film_storyboard_digest", "film_storyboard_version"):
            if k in ctx:
                print(f"    {k}:", json.dumps(ctx[k], ensure_ascii=False, default=str)[:300])
        tasks = ctx.get("tasks")
        if tasks:
            for t in tasks:
                if isinstance(t, dict):
                    print("    task:", t.get("kind"), "| slot:",
                          json.dumps(t.get("slot"), ensure_ascii=False, default=str)[:500])

        steps = await conn.fetch(
            "SELECT id, kind, status, seq, spec, error, started_at, finished_at, cost FROM workflow_steps WHERE run_id=$1 ORDER BY seq",
            r["id"])
        for s in steps:
            spec = _j(s["spec"]) or {}
            slot = spec.get("slot") or {}
            slot_s = json.dumps({k: v for k, v in slot.items()}, ensure_ascii=False, default=str)[:700]
            print(f"      step seq={s['seq']} kind={s['kind']} status={s['status']} "
                  f"{s['started_at']}→{s['finished_at']} err={str(s['error'])[:150]}")
            print(f"        slot: {slot_s}")
            print(f"        cost: {json.dumps(_j(s['cost']), default=str)[:200]}")

    print("=" * 100)
    print("OUTPUTS")
    outs = await conn.fetch(
        "SELECT id, type, status, created_at, render_spec, payload, files, render_status, render_error, work_id FROM outputs WHERE project_id=$1 ORDER BY created_at",
        PROJECT)
    for o in outs:
        print(f"\n--- output {o['id']} type={o['type']} status={o['status']} render={o['render_status']} {o['created_at']} work={str(o['work_id'])[:8]}")
        rs = _j(o["render_spec"])
        if isinstance(rs, dict):
            print("    spec keys:", sorted(rs.keys()))
            print("    fps:", rs.get("fps"), "| width/height:", rs.get("width"), rs.get("height"))
            mus = rs.get("music")
            print("    music:", json.dumps(mus, ensure_ascii=False, default=str)[:200] if mus else None)
            scenes = rs.get("scenes") or []
            print(f"    scenes ({len(scenes)}):")
            for i, sc in enumerate(scenes):
                print(f"      [{i}] {_scene_line(sc)}")
            caps = rs.get("captions")
            if caps:
                print("    captions:", json.dumps(caps, ensure_ascii=False, default=str)[:400])
        files = _j(o["files"]) or {}
        print("    files:", {k: str(v)[:80] for k, v in files.items()})
        print("    render_error:", str(o["render_error"])[:300])

    await conn.close()


asyncio.run(main())
