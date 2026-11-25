"""Live Studio turns and their durable browser and PostgreSQL projections."""
import re

from playwright.async_api import expect
import pytest
from sqlalchemy import select

from app.models.tables import Composition, CompositionVersion, SkillVersion
from test.support.chat_http import tool
from scripts.eval_chat_e2e import parse_sse_frames

pytestmark = [pytest.mark.e2e_browser, pytest.mark.asyncio]

PRESETS = ["kinetic_beat:typewriter_swap", "kinetic_beat:marquee_wall", "ui_montage:fan_slide"]
READY = "Your launch draft is ready."


def create_draft(studio):
    studio.script(tool("load_skill", {"skill_id": "kinetic-launch"}),
                  tool("create_video", {"name": "Launch film", "motion_blocks": [
                      {"block_id": "kinetic_beat", "duration_seconds": 3,
                       "props": {"mode": "typewriter_swap", "words": ["Imagine", "Design", "Launch"]}},
                  ]}), tool("answer", {}, READY))


async def test_question_to_video(studio):
    page = studio.page
    question = "Which direction should the launch take?"
    intro = "Let's choose a direction."
    studio.script(tool("list_project_media", {}, intro), tool("ask_user", {"question": question, "options": [
        {"id": "bold", "label": "Bold typography"}, {"id": "quiet", "label": "Quiet editorial"},
    ]}, "Pick a direction below."))
    response = await studio.send("Create a launch film. Ask me about its direction first.")
    frames = parse_sse_frames(await response.text())
    assert any(intro in str(payload) for event, payload in frames if event in {"assistant.interim_prose", "assistant.delta"}), frames
    choice = page.get_by_role("button", name=re.compile("Bold typography"))
    await studio.capture("01-question", page.get_by_text(intro, exact=True), choice)
    create_draft(studio)
    await choice.click()
    reply = page.get_by_text(READY, exact=True)
    await expect(reply).to_be_visible(timeout=15000)
    async with studio.database() as db:
        compositions = list(await db.scalars(select(Composition).where(Composition.origin_project_id == studio.project)))
        assert len(compositions) == 1
        versions = list(await db.scalars(select(CompositionVersion).where(
            CompositionVersion.composition_id == compositions[0].id)))
        assert len(versions) == 1 and versions[0].skill_provenance["skill_reference"]["skill_id"] == "kinetic-launch"
        studio.report["pg"].update(compositions=len(compositions), composition_versions=len(versions))
    rows = await studio.messages()
    assert any(row.answer and row.answer.get("option_id") == "bold" for row in rows)
    assert any(row.content == READY for row in rows)
    await studio.capture("02-draft", reply, page.get_by_role("button", name="Open in Workbench"))
    studio.script(tool("inspect_timeline", {}), tool("answer", {}, "The film has one three-second scene."))
    await studio.send("Review the saved timeline and tell me its length.")
    await expect(page.get_by_text("The film has one three-second scene.", exact=True)).to_be_visible()
    for step in ("03-timeline", "04-reload"):
        if step.endswith("reload"):
            await page.reload()
        await expect(reply).to_be_visible()
        opener = page.get_by_role("button", name="Open workbench", exact=True)
        if await opener.is_visible():
            await opener.click()
        player = page.get_by_role("tabpanel")
        await expect(player.get_by_role("button", name="Play video")).to_be_attached()
        await studio.capture(step, reply, page.get_by_text("Bold typography", exact=True),
                             player.get_by_text("Launch film", exact=True), player.get_by_text("Scenes (1)", exact=True))


async def test_preset_selection(studio):
    page = studio.page
    studio.script(tool("show_video_presets", {"preset_ids": PRESETS}),
                  tool("answer", {}, "Choose a motion study."))
    response = await studio.send("Show me three motion presets.")
    frames = parse_sse_frames(await response.text())
    birth = next(p for e, p in frames if e == "assistant.candidates")
    assert [m["preset_id"] for m in birth["members"]] == PRESETS
    plays = page.get_by_role("button", name=re.compile("^Play "))
    use = page.get_by_role("button", name="Use", exact=True)
    ordinals = [page.get_by_text(n, exact=True) for n in ("01", "02", "03")]
    await expect(plays).to_have_count(3)
    titles = await plays.evaluate_all("buttons => buttons.map(b => b.getAttribute('aria-label'))")
    await expect(use).to_have_count(3)
    await studio.capture("01-candidates", *ordinals)
    studio.script(tool("select_video_preset", {"candidate_set_id": birth["candidate_set_id"], "member_index": 1}),
                  tool("answer", {}, "The second motion study is selected."))
    await use.nth(1).click()
    selected = page.get_by_role("button", name="Selected", exact=True)
    await expect(page.get_by_text("The second motion study is selected.", exact=True)).to_be_visible()
    for step in ("02-selection", "03-reload"):
        if step.endswith("reload"):
            await page.reload()
        await expect(plays).to_have_count(3)
        assert await plays.evaluate_all("buttons => buttons.map(b => b.getAttribute('aria-label'))") == titles
        buttons = page.get_by_role("button", name=re.compile("^(Use|Selected)$"))
        await expect(buttons.nth(1)).to_have_attribute("aria-pressed", "true")
        await expect(use).to_have_count(2)
        await studio.capture(step, *ordinals, selected)
    logs = [r.intent for r in await studio.messages() if (r.intent or {}).get("type") == "candidates_log"]
    assert any(e.get("selected") == [1] and e["candidate_set_id"] == birth["candidate_set_id"]
               for log in logs for e in log["events"])
    studio.report["pg"]["candidates_log"] = len(logs)


async def test_template_slot_preview(studio):
    page = studio.page
    create_draft(studio)
    await studio.send("Create a launch film with kinetic typography.")
    reply = page.get_by_text(READY, exact=True)
    await studio.capture("01-draft", reply)
    studio.script(tool("save_composition_as_skill", {"name": "launch-template", "description": "Reusable launch film."}),
                  tool("answer", {}, "The template is saved."))
    await studio.send("Save the current film as a template.")
    receipt = page.get_by_role("button", name="Slot Promo", exact=True)
    for step in ("02-saved", "03-reload"):
        if step.endswith("reload"):
            await page.reload()
        await expect(page.get_by_text("The template is saved.", exact=True)).to_be_visible()
        await page.get_by_role("button", name=re.compile("^Worked for")).last.click()
        await studio.capture(step, receipt, reply, page.get_by_text("The template is saved.", exact=True))
    async with studio.database() as db:
        versions = list(await db.scalars(select(SkillVersion)))
        assert len(versions) == 1 and "slot_blueprint_v1" in versions[0].capability_report["supported"]
        studio.report["pg"]["skill_versions"] = len(versions)
    assert any(row.content == "The template is saved." for row in await studio.messages())
    async with page.expect_response(lambda r: r.url.endswith(f"/skills/{versions[0].id}/slot-preview")
                                    or f"/skills/{versions[0].id}/slot-preview?" in r.url) as pending:
        await receipt.click()
    response = await pending.value
    assert response.status == 200 and "[01]" in (await response.json())["copyable_checklist"]
    await studio.capture("04-slot-preview", page.get_by_role("dialog"))
