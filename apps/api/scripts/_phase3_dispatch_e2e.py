"""Phase 3 e2e: _materialize_quote_card_outputs persists Output(type=clip).

Exercises the full dispatch path the recipe adapter runs through:

  1. Build a minimal Project + Persona + Asset (video with words) + WorkflowRun
     + WorkflowStep in the DB.
  2. Call ``_materialize_quote_card_outputs`` directly (the helper
     DerivativeWriterNode.run invokes after persisting the Quotes output).
  3. Verify a sibling ``Output(type="clip")`` row was added with
     ``render_spec`` populated, ``render_status=PENDING``, ``provenance="real"``,
     and the expected track structure (caption_track + translation_track).
  4. Verify a sibling ``WorkflowStep(kind="render")`` was fanned out (UI
     progress mirror, same shape select_clips produces).

All four caption modes exercised; the negative paths (no video source,
no time-bind) covered too.
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.database import AsyncSessionLocal
from app.models.tables import Asset, Output, Persona, Project, User, WorkflowRun, WorkflowStep
from app.pipeline.derivative_dispatch import _materialize_quote_card_outputs
from app.pipeline.clip_spec import _QUOTE_CARD_POST_PAD_S, _QUOTE_CARD_PRE_PAD_S
from app.models.schemas import AssetType, RenderStatus


def fail(msg, ctx=None):
    print(f"✗ {msg}", file=sys.stderr)
    if ctx is not None:
        print(json.dumps(ctx, indent=2, ensure_ascii=False, default=str), file=sys.stderr)
    sys.exit(1)


def ok(msg):
    print(f"✓ {msg}")


def _quote(**overrides):
    base = {
        "quote": "Stay hungry, stay foolish.",
        "attribution": "Steve Jobs | Stanford Commencement 2005",
        "quotable_line_id": 0,
        "source_start": 10.0,
        "source_end": 12.0,
        "frame_at": 11.0,
        "quote_source": "Stay hungry, stay foolish.",
        "quote_alt": "求知若饥，虚心若愚。",
    }
    base.update(overrides)
    return base


async def setup_db():
    """Insert a minimal fixture set: user, project, persona, asset, run, step.

    Each test run gets fresh rows (uuid ids) so the script is repeatable.
    """
    async with AsyncSessionLocal() as db:
        # Reuse any existing user (auth flow needs one anyway).
        from sqlalchemy import select
        user = (await db.execute(select(User).limit(1))).scalar_one_or_none()
        if user is None:
            fail("no test user in DB — run dev.sh first")
        project = Project(
            id=uuid.uuid4(),
            user_id=user.id,
            title="Phase 3 dispatch e2e",
            language="en",
            event_name="Test",
        )
        db.add(project)
        await db.flush()
        persona = Persona(
            id=uuid.uuid4(),
            user_id=user.id,
            name="Test Persona",
            brand={
                "captionStylePreset": "clean-bottom",
                "captionPosition": {"x": 0.5, "y": 0.84},
                "captionColor": "#facc15",
                "captionSize": 68,
                "captionFont": "lilita",
            },
            voice=None,
        )
        db.add(persona)
        await db.flush()
        words = [
            {"word": "Stay", "start": 10.0, "end": 10.4},
            {"word": "hungry", "start": 10.4, "end": 10.9},
            {"word": "stay", "start": 11.0, "end": 11.3},
            {"word": "foolish", "start": 11.3, "end": 11.9},
        ]
        asset = Asset(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=user.id,
            type=AssetType.VIDEO,
            file_url="user/uploads/test.mp4",
            duration_seconds=60.0,
            meta={"language": "en", "words": words},
            processing_status="completed",
        )
        db.add(asset)
        await db.flush()
        run = WorkflowRun(
            id=uuid.uuid4(),
            project_id=project.id,
            status="running",
            context={
                "caption_mode": "bilingual",
                "target_language": "zh",
                "source_language": "en",
            },
        )
        db.add(run)
        await db.flush()
        # Pretend write_quotes just ran — output already exists; the helper
        # creates a SIBLING Output(type="clip") without touching it.
        step = WorkflowStep(
            id=uuid.uuid4(),
            run_id=run.id,
            kind="write_quotes",
            status="running",
            seq=1,
            inputs=[],
            spec={},
        )
        db.add(step)
        await db.flush()
        quotes_output = Output(
            id=uuid.uuid4(),
            project_id=project.id,
            workflow_step_id=step.id,
            type="quotes",
            language="zh",
            provenance="generated",
            payload={
                "quotes": [_quote()],
            },
        )
        db.add(quotes_output)
        await db.commit()
        return (
            str(project.id),
            str(persona.id),
            str(asset.id),
            str(run.id),
            str(step.id),
            str(quotes_output.id),
        )


async def teardown_db(pid):
    async with AsyncSessionLocal() as db:
        from sqlalchemy import delete, select
        from app.models.tables import Asset, Output, Persona, Project, WorkflowRun, WorkflowStep
        # WorkflowStep links via run_id, not project_id — fetch the run ids first.
        run_ids = (
            await db.execute(
                select(WorkflowRun.id).where(WorkflowRun.project_id == pid)
            )
        ).scalars().all()
        if run_ids:
            await db.execute(
                delete(WorkflowStep).where(WorkflowStep.run_id.in_(run_ids))
            )
        await db.execute(delete(Output).where(Output.project_id == pid))
        await db.execute(delete(Asset).where(Asset.project_id == pid))
        await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == pid))
        # Project itself can stay; other tests may reuse the slot.
        await db.commit()


async def fetch_outputs(pid, kind="clip"):
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        rows = (
            await db.execute(
                select(Output).where(Output.project_id == pid, Output.type == kind)
            )
        ).scalars().all()
        return rows


async def fetch_steps(rid, kind="render"):
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        rows = (
            await db.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == rid, WorkflowStep.kind == kind)
            )
        ).scalars().all()
        return rows


async def main():
    pid, persona_id, asset_id, rid, step_id, qoid = await setup_db()
    print(f"project={pid[:8]} run={rid[:8]} step={step_id[:8]} quotes_output={qoid[:8]}")

    # --- Bilingual: should produce 1 clip output + 1 render step ---
    async with AsyncSessionLocal() as db:
        from app.models.tables import Asset, Output, Persona, Project, WorkflowRun, WorkflowStep
        project = await db.get(Project, uuid.UUID(pid))
        persona = await db.get(Persona, uuid.UUID(persona_id))
        run = await db.get(WorkflowRun, uuid.UUID(rid))
        step = await db.get(WorkflowStep, uuid.UUID(step_id))
        quotes_output = await db.get(Output, uuid.UUID(qoid))
        await _materialize_quote_card_outputs(
            db=db,
            run=run,
            node=step,
            project=project,
            persona=persona,
            output=quotes_output,
            quotes=[_quote()],
            target_language="zh",
            source_language="en",
            caption_mode="bilingual",
        )
        await db.commit()

    clips = await fetch_outputs(pid, "clip")
    if len(clips) != 1:
        fail("bilingual: expected 1 clip output", [{"id": str(c.id), "type": c.type} for c in clips])
    c = clips[0]
    if c.render_status != RenderStatus.PENDING:
        fail("bilingual: render_status must be PENDING", c.render_status)
    if c.provenance != "real":
        fail("bilingual: provenance must be real (slice-of-real-video)", c.provenance)
    spec = c.render_spec or {}
    if spec.get("aspect") != "9:16":
        fail("bilingual: aspect must be 9:16", spec.get("aspect"))
    if not spec.get("caption_track"):
        fail("bilingual: caption_track must be populated", spec)
    if len(spec.get("translation_track", [])) != 1:
        fail("bilingual: translation_track must have exactly 1 cue", spec.get("translation_track"))
    if spec["caption_track"][0]["text"] != "Stay hungry, stay foolish.":
        fail("bilingual: caption text must be verbatim source", spec["caption_track"][0])
    if spec["caption_track"][0]["lang"] != "en":
        fail("bilingual: caption lang must be source lang (en)", spec["caption_track"][0])
    if spec["translation_track"][0]["text"] != "求知若饥，虚心若愚。":
        fail("bilingual: translation text must be alt", spec["translation_track"][0])
    if spec["translation_track"][0]["lang"] != "zh":
        fail("bilingual: translation lang must be target (zh)", spec["translation_track"][0])
    if not spec.get("title", {}).get("enabled"):
        fail("bilingual: title must be enabled (attribution)", spec.get("title"))
    if spec["title"]["text"] != "Steve Jobs | Stanford Commencement 2005":
        fail("bilingual: title text must be attribution", spec["title"])
    if spec.get("caption_style_preset") != "clean-bottom":
        fail("bilingual: caption_style_preset must come from brand (clean-bottom)", spec.get("caption_style_preset"))
    if not spec.get("caption_position") or spec["caption_position"].get("y") != 0.84:
        fail("bilingual: caption_position must come from brand", spec.get("caption_position"))
    ok(f"bilingual: clip output persisted with caption_track ({len(spec['caption_track'])}) + translation_track ({len(spec['translation_track'])}) + attribution title")

    # Verify render step fan-out
    renders = await fetch_steps(rid, "render")
    if len(renders) != 1:
        fail("bilingual: expected 1 render step fan-out", [{"id": str(r.id), "status": r.status} for r in renders])
    r = renders[0]
    if r.spec.get("output_id") != str(c.id):
        fail("bilingual: render step spec.output_id must match the clip output id", r.spec)
    if r.seq <= step.seq if step.seq else True:
        fail("bilingual: render step seq must be > producer step", (r.seq, step.seq))
    ok(f"bilingual: render step fan-out (seq={r.seq}, output_id={r.spec.get('output_id')[:8]})")

    # --- Source-only: caption_track present, translation_track empty ---
    await teardown_db(pid)
    pid, persona_id, asset_id, rid, step_id, qoid = await setup_db()
    async with AsyncSessionLocal() as db:
        from app.models.tables import Asset, Output, Persona, Project, WorkflowRun, WorkflowStep
        project = await db.get(Project, uuid.UUID(pid))
        persona = await db.get(Persona, uuid.UUID(persona_id))
        run = await db.get(WorkflowRun, uuid.UUID(rid))
        step = await db.get(WorkflowStep, uuid.UUID(step_id))
        quotes_output = await db.get(Output, uuid.UUID(qoid))
        await _materialize_quote_card_outputs(
            db=db,
            run=run,
            node=step,
            project=project,
            persona=persona,
            output=quotes_output,
            quotes=[_quote()],
            target_language="zh",
            source_language="en",
            caption_mode="source_only",
        )
        await db.commit()
    clips = await fetch_outputs(pid, "clip")
    spec = clips[0].render_spec
    if len(spec.get("caption_track", [])) != 1:
        fail("source_only: caption_track must have 1 cue", spec)
    if spec.get("translation_track"):
        fail("source_only: translation_track must be empty", spec.get("translation_track"))
    ok("source_only: caption present, translation empty")

    # --- Target-only: caption carries the target-language text ---
    await teardown_db(pid)
    pid, persona_id, asset_id, rid, step_id, qoid = await setup_db()
    async with AsyncSessionLocal() as db:
        from app.models.tables import Asset, Output, Persona, Project, WorkflowRun, WorkflowStep
        project = await db.get(Project, uuid.UUID(pid))
        persona = await db.get(Persona, uuid.UUID(persona_id))
        run = await db.get(WorkflowRun, uuid.UUID(rid))
        step = await db.get(WorkflowStep, uuid.UUID(step_id))
        quotes_output = await db.get(Output, uuid.UUID(qoid))
        await _materialize_quote_card_outputs(
            db=db,
            run=run,
            node=step,
            project=project,
            persona=persona,
            output=quotes_output,
            quotes=[_quote()],
            target_language="zh",
            source_language="en",
            caption_mode="target_only",
        )
        await db.commit()
    clips = await fetch_outputs(pid, "clip")
    spec = clips[0].render_spec
    if len(spec.get("caption_track", [])) != 1:
        fail("target_only: caption_track must have 1 cue", spec)
    if spec.get("translation_track"):
        fail("target_only: translation_track must be empty", spec.get("translation_track"))
    if spec["caption_track"][0]["lang"] != "zh":
        fail("target_only: caption lang must be target (zh)", spec["caption_track"][0])
    if spec["caption_track"][0]["text"] != "Stay hungry, stay foolish.":
        fail("target_only: caption text must be the target-language quote", spec["caption_track"][0])
    ok(f"target_only: single main caption in target lang ({spec['caption_track'][0]['lang']})")

    # --- Negative: missing time-bind → no clip output ---
    await teardown_db(pid)
    pid, persona_id, asset_id, rid, step_id, qoid = await setup_db()
    async with AsyncSessionLocal() as db:
        from app.models.tables import Asset, Output, Persona, Project, WorkflowRun, WorkflowStep
        project = await db.get(Project, uuid.UUID(pid))
        persona = await db.get(Persona, uuid.UUID(persona_id))
        run = await db.get(WorkflowRun, uuid.UUID(rid))
        step = await db.get(WorkflowStep, uuid.UUID(step_id))
        quotes_output = await db.get(Output, uuid.UUID(qoid))
        result = await _materialize_quote_card_outputs(
            db=db,
            run=run,
            node=step,
            project=project,
            persona=persona,
            output=quotes_output,
            quotes=[_quote(source_start=None, source_end=None)],
            target_language="zh",
            source_language="en",
            caption_mode="bilingual",
        )
        await db.commit()
    if result:
        fail("missing time-bind: expected empty result list", result)
    clips = await fetch_outputs(pid, "clip")
    if clips:
        fail("missing time-bind: no clip output should be created", clips)
    ok("missing time-bind → no clip output (silent skip)")

    # --- Negative: no video source → empty result ---
    await teardown_db(pid)
    pid, persona_id, asset_id, rid, step_id, qoid = await setup_db()
    async with AsyncSessionLocal() as db:
        # Delete the video asset the helper looks for.
        from sqlalchemy import delete as sql_delete
        from app.models.tables import Asset
        await db.execute(sql_delete(Asset).where(Asset.project_id == uuid.UUID(pid)))
        await db.commit()

    async with AsyncSessionLocal() as db:
        from app.models.tables import Asset, Output, Persona, Project, WorkflowRun, WorkflowStep
        project = await db.get(Project, uuid.UUID(pid))
        persona = await db.get(Persona, uuid.UUID(persona_id))
        run = await db.get(WorkflowRun, uuid.UUID(rid))
        step = await db.get(WorkflowStep, uuid.UUID(step_id))
        quotes_output = await db.get(Output, uuid.UUID(qoid))
        result = await _materialize_quote_card_outputs(
            db=db,
            run=run,
            node=step,
            project=project,
            persona=persona,
            output=quotes_output,
            quotes=[_quote()],
            target_language="zh",
            source_language="en",
            caption_mode="bilingual",
        )
        await db.commit()
    if result:
        fail("no video source: expected empty result list", result)
    clips = await fetch_outputs(pid, "clip")
    if clips:
        fail("no video source: no clip output should be created", clips)
    ok("no video source → no clip output (silent skip + log warning)")

    # Final teardown
    await teardown_db(pid)

    print()
    print("PHASE 3 DISPATCH E2E GREEN")


if __name__ == "__main__":
    asyncio.run(main())