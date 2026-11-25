"""Chat creation, package discovery and motion candidate playback contracts."""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.chat.intent import intent_router
from app.models.tables import CompositionVersion, SkillVersion, SourceSnapshot, User
from app.providers.llm.base import ToolCall, ToolGeneration
from app.skills.external import build_skill_draft
from app.skills.store import import_external_skill
from app.tools.video.presets import MOTION_PREVIEW_CATALOG
from scripts.eval_chat_e2e import parse_sse_frames
from test.support.db_helpers import ScriptedToolClient, _project, _user, bind_test_database, full_api_client

pytestmark = [pytest.mark.chat_origin, pytest.mark.asyncio]


def call(name, args, text=""):
    return ToolGeneration(content=text, tool_calls=[ToolCall(id=str(uuid4()), name=name, arguments=args)])


async def post(client, project, message):
    response = await client.post("/api/v1/chat", json={"project_id": str(project), "message": message},
                                 headers={"Accept": "text/event-stream"})
    assert response.status_code == 200
    frames = parse_sse_frames(response.text)
    assert not [payload for kind, payload in frames if kind == "error"]
    return frames


def wire(client, index):
    return json.dumps(client.calls[index]["messages"], ensure_ascii=False)


def methods(client, index):
    return {tool["function"]["name"] for tool in client.calls[index]["tools"]}


async def test_launch_from_free_text_through_saved_template_and_candidate_stream(database, monkeypatch):
    bind_test_database(monkeypatch, database)
    uid = await _user(database)
    pid = await _project(database, uid)
    screens = [uuid4(), uuid4()]
    async with database() as db:
        owner = await db.get(User, uid)
        for i, sid in enumerate(screens):
            db.add(SourceSnapshot(id=sid, owner_id=uid, origin_project_id=pid, kind="image",
                                  storage_key=f"screens/{i}.png", digest=str(i + 1) * 64))
        await db.commit()

    ids = list(MOTION_PREVIEW_CATALOG)
    blocks = []
    for i in range(30):
        key = ids[i % len(ids)]
        block, mode = key.split(":")
        props = {**MOTION_PREVIEW_CATALOG[key], "theme": "light" if i % 2 else "dark"}
        props["mode" if block == "kinetic_beat" else "layout_mode"] = mode
        blocks.append({"block_id": block, "duration_seconds": 0.35 if i % 2 else 1.25, "props": props,
                       "resources": [str(s) for s in screens] if block == "ui_montage" else []})
    previews = ["kinetic_beat:typewriter_swap", "kinetic_beat:marquee_wall", "ui_montage:fan_slide"]
    llm = ScriptedToolClient([
        call("load_skill", {"skill_id": "kinetic-launch"}),
        call("create_video", {"name": "Beat launch", "motion_blocks": blocks, "style_preset": "swiss_paper"}),
        call("answer", {}, "初稿已保存。"),
        call("save_composition_as_skill", {"name": "launch-template", "description": "Reusable launch template"}),
        call("answer", {}, "模板已保存。"),
        call("show_video_presets", {"preset_ids": previews}),
        call("answer", {}, "选一款动效。"),
    ], streaming=True)
    monkeypatch.setattr(intent_router, "client", llm)
    monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: llm)
    async with full_api_client(database, owner) as client:
        await post(client, pid, "按鼓点给产品做一条无旁白发布片。")
        assert "available_skills" in wire(llm, 0) and "kinetic-launch" in wire(llm, 0)
        assert "以强鼓点为主时钟" not in wire(llm, 0) and "以强鼓点为主时钟" in wire(llm, 1)
        assert "load_skill" in methods(llm, 0) and "read_skill_reference" not in methods(llm, 0)
        async with database() as db:
            version = (await db.scalars(select(CompositionVersion))).one()
            assert version.skill_provenance["skill_reference"]["skill_id"] == "kinetic-launch"
            assert len(version.scenes) == 30
            assert {track["role"] for track in version.timeline["tracks"]} == {"main"}
            clips = version.timeline["tracks"][0]["clips"]
            assert [clip["object"]["props"]["theme"] for clip in clips] == [b["props"]["theme"] for b in blocks]
            assert clips[1]["range"]["end"] - clips[1]["range"]["start"] == round(0.35 * version.settings["timebase"])
        await post(client, pid, "保存成可复用模板")
        async with database() as db:
            template = (await db.scalars(select(SkillVersion))).one()
            assert "slot_blueprint_v1" in template.capability_report["supported"]
        response = await client.get(f"/api/v1/skills/{template.id}/slot-preview")
        assert response.status_code == 200, response.text
        assert "[01]" in response.json()["copyable_checklist"]
        frames = await post(client, pid, "展示三个动效候选")
        candidates = next(p for kind, p in frames if kind == "assistant.candidates" and p["kind"] == "video_preset_set")
        assert [m["preset_id"] for m in candidates["members"]] == previews
        from app.editing.styles import CompositionStyle, resolve_style_tokens
        assert all(m["preview_spec"]["style"] == resolve_style_tokens(CompositionStyle(preset_id="swiss_paper"))
                   for m in candidates["members"])
        llm._generations.extend([
            call("select_video_preset", {"candidate_set_id": candidates["candidate_set_id"], "member_index": 1}),
            call("answer", {}, "已选用第二款。"),
        ])
        selection_round = len(llm.calls)
        selection = await post(client, pid, "选用动效 02（交错跑马灯）")
        assert candidates["candidate_set_id"] in wire(llm, selection_round)
        assert any(p.get("selected") == [1] and p.get("candidate_set_id") == candidates["candidate_set_id"]
                   for kind, p in selection if kind == "assistant.candidates")


async def test_external_method_reads_are_scoped_and_package_tools_activate(database, monkeypatch):
    bind_test_database(monkeypatch, database)
    uid, foreign = await _user(database), await _user(database)
    pid = await _project(database, uid)
    async with database() as db:
        owner = await db.get(User, uid)
        for who, slug in [(uid, "my-method"), (foreign, "foreign-method")]:
            draft = build_skill_draft({
                "SKILL.md": f"---\nname: {slug}\ndescription: Screen direction\n---\nDirector notes for {slug}.".encode(),
                "references/cuts.md": b"Align the cut with the pickup.",
            }, declared_capabilities=[])
            version, _ = await import_external_skill(db, owner_id=who, draft=draft)
            if who == foreign:
                foreign_id = str(version.skill_id)
        await db.commit()
    llm = ScriptedToolClient([
        call("load_skill", {"skill_id": foreign_id}), call("load_skill", {"skill_id": "my-method"}),
        call("read_skill_reference", {"path": "references/cuts.md"}),
        call("answer", {}, "Direction is ready."),
    ], streaming=True)
    monkeypatch.setattr(intent_router, "client", llm)
    monkeypatch.setattr("app.providers.llm.get_llm_client", lambda: llm)
    async with full_api_client(database, owner) as client:
        await post(client, pid, "Plan the screen cuts.")
    assert "my-method" in wire(llm, 0) and "foreign-method" not in wire(llm, 0)
    assert "unavailable" in wire(llm, 1) and "read_skill_reference" not in methods(llm, 1)
    assert "Director notes for my-method" in wire(llm, 2)
    assert {"read_skill_reference", "read_skill_demo", "list_skill_shots", "get_skill_preview"} <= methods(llm, 2)
    assert "Align the cut with the pickup" in wire(llm, 3)
