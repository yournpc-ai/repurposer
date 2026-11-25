"""Live Studio turns and their durable browser and PostgreSQL projections."""
import re
import subprocess
from pathlib import Path

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
    open_btn = page.get_by_role("button", name="Open in Workbench")
    await studio.capture("02-draft", reply, open_btn)
    await open_btn.click()
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


async def open_preset_library(page):
    presets = page.get_by_role("tab", name="Presets", exact=True)
    if not await presets.is_visible():
        await page.get_by_role("button", name="Open workbench", exact=True).click()
    await presets.click()


async def test_sound_lab_preview_and_citation(studio):
    page = studio.page
    await open_preset_library(page)
    await page.get_by_role("radio", name="Sounds", exact=True).click()
    search = page.get_by_role("searchbox", name="Search sounds")
    await page.evaluate("""() => {
        const start = AudioBufferSourceNode.prototype.start;
        AudioBufferSourceNode.prototype.start = function (...args) {
            window.previewBuffer = this.buffer;
            return start.apply(this, args);
        };
    }""")
    await search.fill("glass")
    await page.get_by_text("Tap Glass", exact=True).first.click()
    await page.wait_for_function("window.previewBuffer?.numberOfChannels === 2")
    browser_hash = await page.evaluate("""async () => {
        const buf = window.previewBuffer;
        const pcm = new DataView(new ArrayBuffer(buf.length * 4));
        for (let ch = 0; ch < 2; ch++) {
            buf.getChannelData(ch).forEach((x, i) => pcm.setInt16(4*i + 2*ch, Math.round(32767*x), true));
        }
        const bytes = new Uint8Array(await crypto.subtle.digest("SHA-256", pcm.buffer));
        return Array.from(bytes, x => x.toString(16).padStart(2, "0")).join("");
    }""")
    node_hash = subprocess.check_output(
        ["node", "--import", "tsx", "--input-type=module", "-e",
         """import {synthesizeWav} from './src/index.ts'; import {createHash} from 'node:crypto';
         const {wav} = synthesizeWav({recipeId:'tap_glass'});
         console.log(createHash('sha256').update(wav.subarray(44)).digest('hex'));"""],
        cwd=Path(__file__).resolve().parents[4] / "packages/sound-engine", text=True,
    ).strip()
    assert browser_hash == node_hash
    await expect(page.get_by_role("slider")).to_have_count(7)
    pitch = page.get_by_role("slider", name="Pitch", exact=True)
    await search.fill("")
    await page.get_by_role("combobox", name="Category").click()
    await page.get_by_role("option", name="Tap", exact=True).click()
    await expect(page.get_by_text("Tap Glass", exact=True).first).to_be_visible()
    await page.get_by_text("Tap Glass", exact=True).first.click()
    await pitch.focus()
    await pitch.press("ArrowRight")
    await pitch.blur()
    await studio.capture("05-sound-lab", page)
    await page.get_by_role("button", name="Cite in chat").click()
    await expect(page.get_by_role("textbox")).to_contain_text('"pitch_st":0.5')


async def test_visual_preset_galleries_and_citation(studio):
    page = studio.page
    await page.set_viewport_size({"width": 1440, "height": 900})
    await page.emulate_media(reduced_motion="no-preference")
    await open_preset_library(page)
    for kind, label, name, alternate, count, citation in (
        ("blocks", "Blocks", "Logo Wall", "标志墙", 17, "block_id: logo_wall"),
        ("text", "Text", "Neon Pulse", "霓虹辉光", 24, "text_preset: neon_pulse"),
    ):
        if kind == "text":
            await page.emulate_media(reduced_motion="reduce")
        await page.get_by_role("radio", name=label, exact=True).click()
        gallery = page.get_by_role("region", name=label, exact=True)
        await expect(gallery.get_by_role("article")).to_have_count(count)
        card = gallery.get_by_role("article", name=name, exact=True)
        await expect(card.get_by_text(alternate, exact=True)).to_be_visible()
        await card.evaluate("(el) => el.scrollIntoView({block: 'start'})")
        await card.hover()
        if kind == "text":
            await card.get_by_role("button", name=f"Play {name}").click()
        await expect(card.get_by_role("button", name=f"Pause {name}")).to_be_visible()
        await expect(gallery.locator(".__remotion-player")).to_have_count(1)
        await card.get_by_role("button", name="Cite in chat").click()
        composer = page.get_by_role("textbox")
        await expect(composer).to_contain_text(citation)
        await studio.capture(f"workbench-{kind}-gallery", card, composer)
