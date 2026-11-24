"""Core deterministic tests for Wave 4B-1: text-animation, blueprint_summary,
all-13-block numbered Slot Promo compiler, Zod videoSpecSchema parity, and
owner-scoped /api/v1/skills endpoints."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.chat.activity_receipts import skill_saved_receipt
from app.dependencies import get_current_user_required, get_db
from app.editing.catalog import MOTION_BLOCK_CATALOG
from app.editing.styles import CompositionStyle, STYLE_PRESETS
from app.editing.timing import SOURCE_TIMEBASE, seconds_to_ticks
from app.main import app
from app.models.tables import User
from app.skills import SKILL_REGISTRY
from app.skills.blueprint import (
    BLUEPRINT_CAPABILITY,
    BLUEPRINT_PATH,
    BlueprintAct,
    BlueprintAudioProfile,
    BlueprintOverlay,
    BlueprintSfxCue,
    BlueprintTransition,
    SkillBlueprintV1,
)
from app.skills.external import (
    SkillCapabilityReport,
    SkillDraft,
    SkillPolicy,
    SkillSource,
)
from app.skills.resolution import (
    _external_option,
    get_builtin_skill_option,
    list_available_skills,
)
from app.skills.slot_preview import (
    ALLOWED_FONT_FILENAMES,
    build_slot_preview_video_spec,
    compile_blueprint_slot_preview,
    count_blueprint_slots,
    format_slot_checklist,
)
from app.skills.store import import_external_skill

REPO_ROOT = Path(__file__).resolve().parents[4]


def _make_all_13_blocks_blueprint() -> SkillBlueprintV1:
    acts = [
        BlueprintAct(
            act_id="act_1",
            block_id="statement_hook",
            role="opener",
            target_duration_s=4.0,
            min_duration_s=2.5,
            required_slots=["headline"],
            optional_slots=["subheadline"],
            transition_after=BlueprintTransition(kind="wipe_reveal", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_2",
            block_id="kinetic_title",
            role="title",
            target_duration_s=3.0,
            min_duration_s=2.0,
            required_slots=["headline"],
            optional_slots=["subheadline"],
        ),
        BlueprintAct(
            act_id="act_3",
            block_id="product_showcase",
            role="showcase",
            target_duration_s=6.0,
            min_duration_s=3.5,
            style_defaults={"camera_preset": "tilt_left", "chrome_mode": "browser"},
            required_slots=["image_resource"],
            optional_slots=["url_bar", "callout_steps"],
            callout_windows_s=[(1.0, 2.8), (3.1, 5.2)],
            cursor_click_at_s=2.0,
            overlays=[
                BlueprintOverlay(
                    overlay_id="act_3_overlay_1",
                    rel_start_s=0.6,
                    rel_end_s=3.4,
                    style_defaults={"surface_style": "pill_caption", "position": "bottom_left"},
                )
            ],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_4",
            block_id="device_mockup",
            role="showcase",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"layout": "dual", "reveal_at_s": 1.2},
            required_slots=["image_resource", "mobile_image_resource"],
            transition_after=BlueprintTransition(kind="whip_pan", duration_s=0.4),
        ),
        BlueprintAct(
            act_id="act_5",
            block_id="chat_demo",
            role="demo",
            target_duration_s=6.0,
            min_duration_s=3.5,
            required_slots=["messages", "preview_resource"],
            optional_slots=["work_steps", "result_card"],
            item_reveals_s=[0.4, 1.4, 2.6, 3.6],
            secondary_reveals_s=[1.8, 2.2],
            transition_after=BlueprintTransition(kind="zoom_through", duration_s=0.4),
        ),
        BlueprintAct(
            act_id="act_6",
            block_id="metric_grid",
            role="metrics",
            target_duration_s=5.0,
            min_duration_s=3.0,
            required_slots=["items"],
            metric_reveals_s=[0.5, 1.1, 1.7],
            transition_after=BlueprintTransition(kind="iris_focus", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_7",
            block_id="bento_features",
            role="features",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"highlight_index": 1},
            required_slots=["cards"],
            item_reveals_s=[0.4, 1.0, 1.6, 2.2],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_8",
            block_id="flow_diagram",
            role="workflow",
            target_duration_s=5.0,
            min_duration_s=3.0,
            required_slots=["nodes"],
            item_reveals_s=[0.4, 1.1, 1.8, 2.5],
            transition_after=BlueprintTransition(kind="wipe_reveal", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_9",
            block_id="step_timeline",
            role="roadmap",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"active_step": 2},
            required_slots=["steps"],
            item_reveals_s=[0.5, 1.3, 2.1],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_10",
            block_id="split_compare",
            role="compare",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"dim_left": True},
            required_slots=["left_heading", "left_items", "right_heading", "right_items"],
            item_reveals_s=[0.4, 1.0, 1.6],
            secondary_reveals_s=[0.8, 1.4, 2.0],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_11",
            block_id="data_chart",
            role="data",
            target_duration_s=5.0,
            min_duration_s=3.0,
            style_defaults={"chart_type": "bar", "highlight_index": 3},
            required_slots=["title", "points"],
            item_reveals_s=[0.5, 1.0, 1.5, 2.0],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_12",
            block_id="quote_proof",
            role="proof",
            target_duration_s=4.5,
            min_duration_s=3.0,
            style_defaults={"highlight_at_s": 1.2},
            required_slots=["quote", "author"],
            transition_after=BlueprintTransition(kind="crossfade", duration_s=0.5),
        ),
        BlueprintAct(
            act_id="act_13",
            block_id="closing_cta",
            role="closing",
            target_duration_s=4.5,
            min_duration_s=3.0,
            required_slots=["brand_name", "tagline"],
        ),
    ]
    sfx_cues = [
        BlueprintSfxCue(cue_id="sfx_1", recipe_id="sub_swell", act_index=0, anchor="act_start", offset_s=0.0, gain_db=-12.0),
        BlueprintSfxCue(cue_id="sfx_2", recipe_id="callout_ping", act_index=2, anchor="act_start", offset_s=1.0, gain_db=-11.0),
        BlueprintSfxCue(cue_id="sfx_3", recipe_id="swoosh_cut", act_index=5, anchor="cut_after", offset_s=-0.15, gain_db=-12.0),
        BlueprintSfxCue(cue_id="sfx_4", recipe_id="stinger", act_index=12, anchor="act_start", offset_s=0.2, gain_db=-11.0),
    ]
    return SkillBlueprintV1(
        canvas={"width": 1920, "height": 1080, "fps_num": 30, "fps_den": 1, "background": "#0A0F16"},
        style=CompositionStyle(preset_id="vox_editorial"),
        acts=acts,
        audio_profile=BlueprintAudioProfile(has_bgm=False),
        sfx_cues=sfx_cues,
    )


def _make_6_act_blueprint() -> SkillBlueprintV1:
    full = _make_all_13_blocks_blueprint()
    picked_ids = {
        "product_showcase",
        "metric_grid",
        "bento_features",
        "data_chart",
        "quote_proof",
        "closing_cta",
    }
    acts = [a for a in full.acts if a.block_id in picked_ids]
    return SkillBlueprintV1(
        canvas=full.canvas,
        style=CompositionStyle(preset_id="vox_editorial"),
        acts=acts,
        audio_profile=BlueprintAudioProfile(),
        sfx_cues=[
            BlueprintSfxCue(cue_id="sfx_open", recipe_id="title_bloom", act_index=0, anchor="act_start", offset_s=0.0),
            BlueprintSfxCue(cue_id="sfx_cut", recipe_id="velvet_pass", act_index=1, anchor="cut_after", offset_s=-0.1),
            BlueprintSfxCue(cue_id="sfx_close", recipe_id="stinger", act_index=5, anchor="act_start", offset_s=0.2),
        ],
    )


def _skill_draft_for_blueprint(name: str, bp: SkillBlueprintV1) -> SkillDraft:
    bp_json = bp.model_dump_json(indent=2)
    bp_digest = hashlib.sha256(bp_json.encode("utf-8")).hexdigest()
    skill_md = f"---\nname: {name}\ndescription: Test blueprint\n---\nUse this template.\n"
    return SkillDraft(
        name=name,
        description="Test slot blueprint template",
        instructions=skill_md,
        references=[
            SkillSource(
                path=BLUEPRINT_PATH,
                role="reference",
                digest=bp_digest,
                text=bp_json,
            )
        ],
        media=[],
        declared_inputs=[],
        capability_report=SkillCapabilityReport(
            supported=[BLUEPRINT_CAPABILITY, "native_motion_graphics"]
        ),
        policy=SkillPolicy(),
        source_uri=f"composition://test-{name}@v1",
        source_revision="v1",
        source_hash=bp_digest,
    )


def test_text_animation_skill_loaded_and_registered():
    assert "text-animation" in SKILL_REGISTRY
    pack = SKILL_REGISTRY["text-animation"]
    assert pack.metadata.get("version") == "1.0.0"
    assert "Beat-Led" in pack.body or "节拍" in pack.body
    assert "generate_image" in pack.body

    opt = get_builtin_skill_option("text-animation")
    assert opt.reference.kind == "builtin"
    assert opt.reference.skill_id == "text-animation"
    assert opt.reference.version == "1.0.0"
    assert opt.capabilities == [
        "native_motion_graphics",
        "beat_led_typography",
        "text_style_presets",
    ]


def test_blueprint_summary_attached_and_fault_tolerant():
    bp = _make_6_act_blueprint()
    bp_json = bp.model_dump_json()
    skill = SimpleNamespace(id=uuid4(), name="saas-promo", description="SaaS promo")
    good_ver = SimpleNamespace(
        id=uuid4(),
        version=2,
        capability_report={"supported": [BLUEPRINT_CAPABILITY]},
        references=[{"path": BLUEPRINT_PATH, "text": bp_json}],
    )
    opt = _external_option(skill, good_ver)
    assert opt.blueprint_summary is not None
    assert opt.blueprint_summary.act_count == 6
    assert opt.blueprint_summary.slot_count == count_blueprint_slots(bp)
    assert opt.blueprint_summary.slot_count > 10
    assert opt.blueprint_summary.style_preset == "vox_editorial"
    assert opt.blueprint_summary.duration_s == pytest.approx(sum(a.target_duration_s for a in bp.acts))

    # Malformed JSON must never crash /chat/skills — gracefully yields None
    bad_ver = SimpleNamespace(
        id=uuid4(),
        version=1,
        capability_report={"supported": [BLUEPRINT_CAPABILITY]},
        references=[{"path": BLUEPRINT_PATH, "text": "{not valid json"}],
    )
    bad_opt = _external_option(skill, bad_ver)
    assert bad_opt.blueprint_summary is None


def test_compile_all_13_motion_blocks_and_zod_video_spec_parity():
    bp = _make_all_13_blocks_blueprint()
    assert {a.block_id for a in bp.acts} == set(MOTION_BLOCK_CATALOG.keys())

    # Provide synthetic SFX snapshots for all 4 blueprint SFX cues
    sfx_snapshots: dict[str, tuple[UUID, str, int, str]] = {}
    for cue in bp.sfx_cues:
        digest = hashlib.sha256(cue.cue_id.encode()).hexdigest()
        sfx_snapshots[cue.cue_id] = (
            uuid4(),
            digest,
            seconds_to_ticks(0.6, SOURCE_TIMEBASE),
            f"http://127.0.0.1:9999/sfx/{cue.cue_id}.wav",
        )

    expected_count = count_blueprint_slots(bp)
    specs_to_validate: list[dict] = []

    for preset_id in STYLE_PRESETS:
        for locale in ("zh", "en"):
            spec, slots, assets, duration_s = build_slot_preview_video_spec(
                bp,
                skill_version_id=uuid4(),
                style_preset=preset_id,
                locale=locale,
                sfx_snapshots=sfx_snapshots,
            )
            assert len(slots) == expected_count
            assert [s.slot_number for s in slots] == list(range(1, expected_count + 1))
            assert [s.code for s in slots] == [f"[{i:02d}]" for i in range(1, expected_count + 1)]
            assert spec["style"]["preset_id"] == preset_id
            assert duration_s > 50.0

            # Verify Pillow wireframe PNGs exist for product_showcase (16:9),
            # device_mockup dual (16:9 + 9:16), and chat_demo preview (16:9)
            assert len(assets) == 4
            dims = [(a.width, a.height) for a in assets]
            assert (1280, 720) in dims
            assert (540, 960) in dims
            for asset in assets:
                with Image.open(io.BytesIO(asset.png_bytes)) as im:
                    assert im.format == "PNG"
                    assert im.size == (asset.width, asset.height)

            # Verify HUD track has 1 corner TextObject badge per act
            hud_track = next(t for t in spec["tracks"] if t["track_id"] == "trk_slot_hud")
            assert len(hud_track["clips"]) == 13
            for clip in hud_track["clips"]:
                assert clip["object"]["kind"] == "text"
                assert clip["object"]["style"]["background_mode"] == "pill"

            # Verify transitions & SFX audio tracks preserved
            assert len(spec.get("transitions") or []) >= 9
            effect_clips = [
                c
                for t in spec["tracks"]
                if t["kind"] == "audio" and t["role"] == "effect"
                for c in t["clips"]
            ]
            assert len(effect_clips) == 4

            # Verify checklist text contains every [NN] code
            checklist = format_slot_checklist(slots, locale=locale, template_name="demo")
            for s in slots:
                assert s.code in checklist

            # Verify font URLs point to /api/v1/skills/fonts/...
            assert all(f["url"].startswith("/api/v1/skills/fonts/") for f in spec["fonts"])

            if preset_id in ("vox_editorial", "institutional_dark"):
                specs_to_validate.append(spec)

    # Verify exact parity against packages/video-spec Zod videoSpecSchema.parse!
    node_script = (
        'import { videoSpecSchema } from "./src/index.ts";'
        'import fs from "node:fs";'
        'const specs = JSON.parse(fs.readFileSync(0, "utf-8"));'
        'for (const s of specs) { videoSpecSchema.parse(s); }'
        'console.log("OK:" + specs.length);'
    )
    proc = subprocess.run(
        ["node", "--import", "tsx", "-e", node_script],
        cwd=str(REPO_ROOT / "packages" / "video-spec"),
        input=json.dumps(specs_to_validate),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"Zod videoSpecSchema validation failed:\n{proc.stderr}\n{proc.stdout}"
    assert f"OK:{len(specs_to_validate)}" in proc.stdout


def test_skill_saved_receipt_validation():
    vid = str(uuid4())
    sid = str(uuid4())
    receipt = skill_saved_receipt({
        "skill_id": sid,
        "skill_version_id": vid,
        "name": "saas-promo",
        "version": 1,
        "acts_count": 6,
        "sfx_cues_count": 4,
    })
    assert receipt is not None
    assert receipt.kind == "skill_saved"
    assert receipt.skill_version_id == vid
    assert receipt.acts_count == 6


@pytest.mark.asyncio
async def test_skills_api_endpoints_owner_isolation_and_fonts(database, installed_promo, monkeypatch):
    owner = User(id=uuid4(), email="owner@example.com")
    other = User(id=uuid4(), email="other@example.com")
    bp = _make_6_act_blueprint()

    async with database() as db:
        db.add_all([owner, other])
        await db.flush()
        bp_ver, _ = await import_external_skill(
            db, owner_id=owner.id, draft=_skill_draft_for_blueprint("oxvalue-template", bp)
        )
        non_bp_draft = SkillDraft(
            name="plain-method",
            description="Plain instructions without blueprint",
            instructions="---\nname: plain-method\ndescription: Plain\n---\nInstructions.\n",
            references=[],
            media=[],
            declared_inputs=[],
            capability_report=SkillCapabilityReport(supported=["progressive_skill_package"]),
            policy=SkillPolicy(),
            source_uri="local://plain",
            source_revision="1",
            source_hash="c" * 64,
        )
        plain_ver, _ = await import_external_skill(db, owner_id=owner.id, draft=non_bp_draft)
        await db.commit()

        # Verify list_available_skills returns all 4 builtins + blueprint_summary on external
        available = await list_available_skills(db, owner_id=owner.id)
        builtin_ids = {o.reference.skill_id for o in available if o.reference.kind == "builtin"}
        assert builtin_ids == {
            "promo-video",
            "talking-head-video",
            "text-animation",
            "knowledge-explainer",
        }
        ext_bp = next(
            o for o in available
            if o.reference.kind == "external" and o.reference.skill_version_id == bp_ver.id
        )
        assert ext_bp.blueprint_summary is not None
        assert ext_bp.blueprint_summary.act_count == 6

    active_user = {"user": owner}

    async def override_db():
        async with database() as session:
            yield session

    async def override_user():
        return active_user["user"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user_required] = override_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Font route: strict allowlist + immutable cache header
            for fname in ALLOWED_FONT_FILENAMES:
                r = await client.get(f"/api/v1/skills/fonts/{fname}")
                assert r.status_code == 200
                assert "immutable" in r.headers.get("cache-control", "")
                assert len(r.content) > 1000
            bad_font = await client.get("/api/v1/skills/fonts/OFL.txt")
            assert bad_font.status_code == 404
            traversal = await client.get("/api/v1/skills/fonts/..%2F..%2Fmain.py")
            assert traversal.status_code == 404

            # 2. Owner gets valid slot-preview JSON
            r = await client.get(
                f"/api/v1/skills/{bp_ver.id}/slot-preview",
                params={"style_preset": "institutional_dark", "locale": "en"},
            )
            assert r.status_code == 200
            payload = r.json()
            assert payload["style_preset"] == "institutional_dark"
            assert payload["locale"] == "en"
            assert payload["name"] == "oxvalue-template"
            assert len(payload["slots"]) == count_blueprint_slots(bp)
            assert payload["video_spec"]["fonts"][0]["url"].startswith("/api/v1/skills/fonts/")
            main_track = next(
                t for t in payload["video_spec"]["tracks"] if t["track_id"] == "trk_slot_main"
            )
            ps_clip = next(
                c for c in main_track["clips"] if c["object"]["block_id"] == "product_showcase"
            )
            assert ps_clip["object"]["resources"][0]["url"].startswith("data:image/png;base64,")

            # 3. Non-blueprint skill returns 400
            r_non_bp = await client.get(f"/api/v1/skills/{plain_ver.id}/slot-preview")
            assert r_non_bp.status_code == 400

            # 4. Missing UUID returns 404
            r_missing = await client.get(f"/api/v1/skills/{uuid4()}/slot-preview")
            assert r_missing.status_code == 404

            # 5. Foreign owner gets 404 (strict isolation)
            active_user["user"] = other
            r_foreign = await client.get(f"/api/v1/skills/{bp_ver.id}/slot-preview")
            assert r_foreign.status_code == 404

            # 6. Export endpoint: returns structured 503 when render service is unreachable
            active_user["user"] = owner

            class _FailingClient:
                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return False

                async def post(self, *args, **kwargs):
                    raise httpx.ConnectError("render offline")

            monkeypatch.setattr("app.skills.routes.httpx.AsyncClient", _FailingClient)
            r_503 = await client.post(
                f"/api/v1/skills/{bp_ver.id}/slot-preview/export",
                json={"style_preset": "vox_editorial", "locale": "zh", "include_sfx": False},
            )
            assert r_503.status_code == 503
            assert "detail" in r_503.json()
    finally:
        app.dependency_overrides.clear()
