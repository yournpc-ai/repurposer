"""quote-cards 家族形态验收闸（durable, LLM-free）——帧卡 Output 化 +
形态 A/B + 宽槽路径（简报 quote-cards-redesign §2.2/§2.3/§2.6）。

Exercises ``_materialize_quote_card_outputs`` directly against real
fixtures and saves the produced PNGs for visual inspection:

  1. **形态 A** (needs_speaker_frame=True, real video): 3-entry bilingual
     EN/ZH chain → 3 quote_frame frame cards + 1 composite quote_frame
     (source_ref.parents == frame ids) + 1 clip MP4 child
     (source_ref.parents == [composite_id]) + render step fan-out.
  2. **形态 B** (needs_speaker_frame=False, same video): composite =
     full-bleed dimmed background branch.
  3. **照片底** (image asset only, no video): photo-bottom cards + clip
     anchored on the image asset.
  4. **纯文稿** (transcript only): dark cards, NO motion MP4.
  5. **N=1 with video**: single clip via build_quote_card_spec
     (target_only → caption = quote_alt, D5).
  6. **alt 推导**: derive_quote_alt_language + _caption_choice_is_meaningful
     (EN source + ZH locale → alt=zh meaningful; all-EN → skip).

Products land in project storage scope (never demo/). Fixture rows are
cleaned FK-safe at the end (outputs → steps → runs → assets → project →
persona); the shared test user stays. Sample PNGs: /tmp/p2-quote-frames/.

Run: uv run python scripts/accept_quote_card_family.py
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import delete, select

from app.models.database import AsyncSessionLocal
from app.models.schemas import AssetType, RenderStatus
from app.models.tables import (
    Asset,
    Output,
    Persona,
    Project,
    User,
    WorkflowRun,
    WorkflowStep,
)
from app.pipeline.derivative_dispatch import (
    _materialize_quote_card_outputs,
    derive_quote_alt_language,
)
from app.chat.service import _caption_choice_is_meaningful
from app.models.schemas import TaskItem
from app.providers.storage import save

OUT_DIR = Path("/tmp/p2-quote-frames")


def fail(msg, ctx=None):
    print(f"✗ {msg}", file=sys.stderr)
    if ctx is not None:
        print(json.dumps(ctx, indent=2, ensure_ascii=False, default=str), file=sys.stderr)
    sys.exit(1)


def ok(msg):
    print(f"✓ {msg}")


def _quote(qid, text, alt, start, end, **over):
    base = {
        "quote": text,
        "attribution": "Prof. Xu | xy_2 Keynote",
        "quotable_line_id": qid,
        "source_start": start,
        "source_end": end,
        "frame_at": round((start + end) / 2, 1),
        "quote_source": text,
        "quote_alt": alt,
    }
    base.update(over)
    return base


CHAIN = [
    _quote(0, "The future of education is personal.", "教育的未来是个性化的。", 5.0, 8.0),
    _quote(1, "AI will not replace teachers.", "AI 不会取代老师。", 12.0, 15.0),
    _quote(2, "It will make every teacher ten times better.", "它会让每位老师强大十倍。", 18.0, 21.0),
]


async def _mk_project(db, user, title, language="zh", persona_brand=None):
    project = Project(
        id=uuid.uuid4(), user_id=user.id, title=title,
        language=language, event_name="P2 e2e",
    )
    db.add(project)
    await db.flush()
    persona = Persona(
        id=uuid.uuid4(), user_id=user.id, name=f"{title} persona",
        brand=persona_brand, voice=None,
    )
    db.add(persona)
    await db.flush()
    return project, persona


async def _mk_run_step(db, project, ctx):
    run = WorkflowRun(id=uuid.uuid4(), project_id=project.id, status="running", context=ctx)
    db.add(run)
    await db.flush()
    step = WorkflowStep(
        id=uuid.uuid4(), run_id=run.id, kind="write_quotes",
        status="running", seq=1, inputs=[], spec={},
    )
    db.add(step)
    await db.flush()
    return run, step


async def _mk_video(db, project, user):
    words = [
        {"word": f"w{i}", "start": i * 0.5, "end": i * 0.5 + 0.4}
        for i in range(120)
    ]
    asset = Asset(
        id=uuid.uuid4(), project_id=project.id, user_id=user.id,
        type=AssetType.VIDEO, file_url="demo/uploads/xy_2.mp4",
        duration_seconds=60.0,
        meta={"language": "en", "words": words},
        processing_status="completed",
    )
    db.add(asset)
    await db.flush()
    return asset


async def _outputs(db, project):
    return (await db.execute(
        select(Output).where(Output.project_id == project.id).order_by(Output.created_at)
    )).scalars().all()


async def _download(url, dest):
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(url)
        if r.status_code != 200:
            fail(f"download {url} → {r.status_code}")
        dest.write_bytes(r.content)


async def _check_family(db, project, step, *, expect_clip, label):
    """Assert the P2 family shape: 3 frame cards + 1 composite (+ clip)."""
    outputs = await _outputs(db, project)
    frames = [o for o in outputs if o.type == "quote_frame" and not (o.source_ref or {}).get("quote_chain")]
    composites = [o for o in outputs if o.type == "quote_frame" and (o.source_ref or {}).get("quote_chain")]
    clips = [o for o in outputs if o.type == "clip"]
    if len(frames) != 3:
        fail(f"{label}: expected 3 frame cards, got {len(frames)}")
    if len(composites) != 1:
        fail(f"{label}: expected 1 composite, got {len(composites)}")
    composite = composites[0]
    parents = (composite.source_ref or {}).get("parents") or []
    if sorted(parents) != sorted(str(f.id) for f in frames):
        fail(f"{label}: composite parents mismatch", {"parents": parents, "frames": [str(f.id) for f in frames]})
    for f in frames + [composite]:
        if not (f.files or {}).get("image"):
            fail(f"{label}: {f.id} missing files.image")
        if (f.payload or {}).get("aspect") != "9:16":
            fail(f"{label}: {f.id} payload aspect != 9:16")
        if f.provenance != "real":
            fail(f"{label}: {f.id} provenance != real")
        if str(f.workflow_step_id) != str(step.id):
            fail(f"{label}: {f.id} workflow_step_id mismatch")
    if expect_clip:
        if len(clips) != 1:
            fail(f"{label}: expected 1 motion clip, got {len(clips)}")
        clip = clips[0]
        if (clip.source_ref or {}).get("parents") != [str(composite.id)]:
            fail(f"{label}: clip parents != [composite]", clip.source_ref)
        if clip.render_status != RenderStatus.PENDING:
            fail(f"{label}: clip render_status != PENDING")
        if not clip.render_spec:
            fail(f"{label}: clip missing render_spec")
        renders = (await db.execute(
            select(WorkflowStep).where(
                WorkflowStep.kind == "render",
                WorkflowStep.spec["output_id"].astext == str(clip.id),
            )
        )).scalars().all()
        if len(renders) != 1:
            fail(f"{label}: expected 1 render step, got {len(renders)}")
    else:
        if clips:
            fail(f"{label}: expected NO motion clip, got {len(clips)}")
    ok(f"{label}: 3 帧卡 + 1 合成卡 (parents ✓)" + (" + 1 动效 clip (parents ✓, render 扇出 ✓)" if expect_clip else " + 无动效 clip ✓"))
    return frames, composite, clips


async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if user is None:
            fail("no test user in DB — run dev.sh first")

        # ---------- 1. 形态 A (bilingual EN source + ZH alt) ----------
        project, persona = await _mk_project(db, user, "P2 formA")
        await _mk_video(db, project, user)
        run, step = await _mk_run_step(db, project, {
            "caption_mode": "bilingual", "target_language": "zh", "source_language": "en",
        })
        await db.commit()
        ids = await _materialize_quote_card_outputs(
            db=db, run=run, node=step, project=project, persona=persona,
            quotes=[dict(q) for q in CHAIN],
            target_language="zh", source_language="en",
            caption_mode="bilingual", quote_alt_language="zh",
            needs_speaker_frame=True, core_idea="AI makes teachers better.",
        )
        await db.commit()
        if len(ids) != 5:
            fail(f"formA: expected 5 outputs, got {len(ids)}")
        frames, composite, _ = await _check_family(db, project, step, expect_clip=True, label="形态A")
        for i, f in enumerate(frames):
            await _download(f.files["image"], OUT_DIR / f"formA-frame-{i}.png")
        await _download(composite.files["image"], OUT_DIR / "formA-composite.png")
        ok("形态A: PNG 已存 /tmp/p2-quote-frames/formA-*")
        pa, persona_a = project.id, persona.id

        # ---------- 2. 形态 B ----------
        project, persona = await _mk_project(db, user, "P2 formB")
        await _mk_video(db, project, user)
        run, step = await _mk_run_step(db, project, {
            "caption_mode": "bilingual", "target_language": "zh", "source_language": "en",
        })
        await db.commit()
        ids = await _materialize_quote_card_outputs(
            db=db, run=run, node=step, project=project, persona=persona,
            quotes=[dict(q) for q in CHAIN],
            target_language="zh", source_language="en",
            caption_mode="bilingual", quote_alt_language="zh",
            needs_speaker_frame=False, core_idea="AI makes teachers better.",
        )
        await db.commit()
        if len(ids) != 5:
            fail(f"formB: expected 5 outputs, got {len(ids)}")
        frames, composite, _ = await _check_family(db, project, step, expect_clip=True, label="形态B")
        await _download(composite.files["image"], OUT_DIR / "formB-composite.png")
        await _download(frames[0].files["image"], OUT_DIR / "formB-frame-0.png")
        ok("形态B: PNG 已存 /tmp/p2-quote-frames/formB-*")
        pb, persona_b = project.id, persona.id

        # ---------- 3. 照片底 ----------
        from PIL import Image
        import io as _io
        project, persona = await _mk_project(db, user, "P2 photo")
        buf = _io.BytesIO()
        Image.new("RGB", (1600, 900), (70, 90, 120)).save(buf, format="JPEG")
        img_key = f"{user.id}/uploads/projects/{project.id}/p2-photo.jpg"
        await save(img_key, buf.getvalue())
        photo = Asset(
            id=uuid.uuid4(), project_id=project.id, user_id=user.id,
            type=AssetType.IMAGE, file_url=img_key,
            meta={}, processing_status="completed",
        )
        db.add(photo)
        await db.flush()
        run, step = await _mk_run_step(db, project, {
            "caption_mode": "source_only", "target_language": "zh",
        })
        await db.commit()
        ids = await _materialize_quote_card_outputs(
            db=db, run=run, node=step, project=project, persona=persona,
            quotes=[dict(q, quotable_line_id=None, source_start=None,
                         source_end=None, frame_at=None, quote_alt=None) for q in CHAIN],
            target_language="zh", source_language="en",
            caption_mode="source_only",
            needs_speaker_frame=True, core_idea="AI makes teachers better.",
        )
        await db.commit()
        if len(ids) != 5:
            fail(f"photo: expected 5 outputs (clip anchored on image), got {len(ids)}")
        frames, composite, _ = await _check_family(db, project, step, expect_clip=True, label="照片底")
        await _download(composite.files["image"], OUT_DIR / "photo-composite.png")
        ok("照片底: PNG 已存 /tmp/p2-quote-frames/photo-*")
        pc, persona_c = project.id, persona.id

        # ---------- 4. 纯文稿 ----------
        project, persona = await _mk_project(db, user, "P2 textonly")
        tr = Asset(
            id=uuid.uuid4(), project_id=project.id, user_id=user.id,
            type=AssetType.TRANSCRIPT, file_url="scenario/demo-article.md",
            extracted_text="The future of education is personal. " * 20,
            meta={"language": "en"}, processing_status="completed",
        )
        db.add(tr)
        await db.flush()
        run, step = await _mk_run_step(db, project, {
            "caption_mode": "source_only", "target_language": "zh",
        })
        await db.commit()
        ids = await _materialize_quote_card_outputs(
            db=db, run=run, node=step, project=project, persona=persona,
            quotes=[dict(q, quotable_line_id=None, source_start=None,
                         source_end=None, frame_at=None, quote_alt=None) for q in CHAIN],
            target_language="zh", source_language="en",
            caption_mode="source_only",
            needs_speaker_frame=True, core_idea="AI makes teachers better.",
        )
        await db.commit()
        if len(ids) != 4:
            fail(f"textonly: expected 4 outputs (no MP4), got {len(ids)}")
        frames, composite, _ = await _check_family(db, project, step, expect_clip=False, label="纯文稿")
        await _download(composite.files["image"], OUT_DIR / "textonly-composite.png")
        ok("纯文稿: PNG 已存 /tmp/p2-quote-frames/textonly-*")
        pd_, persona_d = project.id, persona.id

        # ---------- 5. N=1 with video (target_only → D5 quote_alt 上屏) ----------
        project, persona = await _mk_project(db, user, "P2 n1")
        await _mk_video(db, project, user)
        run, step = await _mk_run_step(db, project, {
            "caption_mode": "target_only", "target_language": "zh", "source_language": "en",
        })
        await db.commit()
        ids = await _materialize_quote_card_outputs(
            db=db, run=run, node=step, project=project, persona=persona,
            quotes=[dict(CHAIN[0])],
            target_language="zh", source_language="en",
            caption_mode="target_only", quote_alt_language="zh",
        )
        await db.commit()
        if len(ids) != 1:
            fail(f"n1: expected 1 clip output, got {len(ids)}")
        outputs = await _outputs(db, project)
        clip = next((o for o in outputs if o.type == "clip"), None)
        if clip is None:
            fail("n1: no clip output")
        cues = (clip.render_spec or {}).get("caption_track") or []
        if not cues or "教育" not in cues[0].get("text", ""):
            fail("n1 target_only: caption cue is not quote_alt (D5)", cues)
        if (clip.render_spec or {}).get("translation_track"):
            fail("n1 target_only: translation_track must be empty")
        ok("n=1 target_only: caption = quote_alt（D5 ✓），无副行")
        pe, persona_e = project.id, persona.id

        # ---------- 6. alt 推导 + meaningful 闸 ----------
        assert derive_quote_alt_language("en", "zh", "zh", "zh") == "zh"
        assert derive_quote_alt_language("en", "en", "zh", "en") == "zh"  # 任务=源 → locale 补
        assert derive_quote_alt_language("zh", "zh", "zh", "zh") is None  # 全同语 → 无 alt
        assert derive_quote_alt_language("en", "de", "zh", "en") == "de"  # 用户点名优先
        ok("derive_quote_alt_language: 优先级 + 同语跳过 ✓")
        # meaningful: 项目有 EN 视频 + zh locale → True;全 zh → False
        proj_vid = await db.get(Project, pa)
        meaningful = await _caption_choice_is_meaningful(
            db, proj_vid, [TaskItem(tool="write_quotes", params={"language": "zh"})]
        )
        if not meaningful:
            fail("meaningful: EN source + ZH task should be meaningful")
        proj_vid.language = "en"
        meaningful2 = await _caption_choice_is_meaningful(
            db, proj_vid, [TaskItem(tool="write_quotes", params={"language": "en"})]
        )
        if meaningful2:
            fail("meaningful: all-EN should be skipped (source_only)")
        await db.flush()
        ok("_caption_choice_is_meaningful: 双语有意义 / 全同语跳过 ✓")

        # ---------- cleanup (FK 序) ----------
        for pid, persona_id in ((pa, persona_a), (pb, persona_b), (pc, persona_c), (pd_, persona_d), (pe, persona_e)):
            await db.execute(delete(Output).where(Output.project_id == pid))
            runs = (await db.execute(select(WorkflowRun.id).where(WorkflowRun.project_id == pid))).scalars().all()
            await db.execute(delete(WorkflowStep).where(WorkflowStep.run_id.in_(runs)))
            await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == pid))
            await db.execute(delete(Asset).where(Asset.project_id == pid))
            await db.execute(delete(Project).where(Project.id == pid))
            await db.execute(delete(Persona).where(Persona.id == persona_id))
        await db.commit()
        ok("清场完毕（fixture 行 FK 序删除）")

    print("\nALL P2 E2E PASS — 样张在 /tmp/p2-quote-frames/")


asyncio.run(main())
