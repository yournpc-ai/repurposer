"""Composite (ADR-140) version lifecycle over a REAL isolated database:
version persist → re-read → partial edit → confirmed-version handoff →
compile/execute. No LLM (the hand-authored board stands in for the model's
draft — every seat downstream of the draft is the real one), no paid
peripherals (voiceover off, music off, render only PENDED — no worker
claims it), no user projects (a disposable database is created and dropped
on the configured local Postgres server; the test skips when the server is
unreachable or CREATE DATABASE is denied).

Two review-defect regressions ride the journey:

- 缺陷① (element identity): a tampered element numbering is a DIFFERENT
  base — the read-minted reference no longer applies (base_mismatch),
  never a silent edit of the same-named handle.
- 缺陷③ (probe precision): the probed duration's sub-second truth survives
  the write-back / re-read roundtrip — the Integer column floors for
  display, ``meta["probed_duration_seconds"]`` pins the exact value, and a
  source window ending AT the truth validates on every later seat.
"""

import re
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.asyncio

TEXT = "开场\n左边文字\n逐字出现\n收尾"


def _board(asset_id: str, source_end: float) -> dict:
    """The anchor shape in miniature: words → composite(video right + text
    left) → words. Text-mode bands (5–120s total) hold; every element
    window is comfortably inside its scene."""
    return {
        "scenes": [
            {"type": "words", "seconds": 3.0, "dark": False, "lines": ["开场"]},
            {
                "type": "composite",
                "seconds": 4.0,
                "elements": [
                    {
                        "kind": "video",
                        "asset": asset_id,
                        "source_start": 0.0,
                        "source_end": source_end,
                        "at": 0.0,
                        "rect": {"x": 0.5, "y": 0.0, "w": 0.5, "h": 1.0},
                    },
                    {
                        "kind": "text",
                        "lines": ["左边文字", "逐字出现"],
                        "at": 0.5,
                        "until": 3.5,
                        "rect": {"x": 0.05, "y": 0.2, "w": 0.4, "h": 0.6},
                        "enter": "words",
                        "enter_interval": 0.3,
                    },
                ],
            },
            {"type": "words", "seconds": 3.0, "dark": True, "lines": ["收尾"]},
        ]
    }


def _make_clip(path: Path, frames: int = 75) -> None:
    """A real 2.5s (75 frames @ 30fps) video clip — the probe reads its
    container header, no stub."""
    import av
    import numpy as np

    container = av.open(str(path), "w")
    stream = container.add_stream("h264", rate=30)
    stream.width, stream.height, stream.pix_fmt = 64, 64, "yuv420p"
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    for f in range(frames):
        vf = av.VideoFrame.from_ndarray(img, format="rgb24")
        vf.pts = f
        vf.time_base = Fraction(1, 30)
        for pkt in stream.encode(vf):
            container.mux(pkt)
    for pkt in stream.encode(None):
        container.mux(pkt)
    container.close()


async def _isolated_database():
    """A disposable database on the configured Postgres server — the
    journey's seats (set_spec_field/fill_summary) speak jsonb SQL, so
    SQLite cannot stand in. Returns (engine, admin_engine, db_name)."""
    from app.config import settings
    from app.models.database import Base
    from app.models import tables  # noqa: F401 — register every table

    url = settings.database_url
    if not url.startswith("postgresql"):
        pytest.skip("configured database is not Postgres")
    server = url.rsplit("/", 1)[0]
    name = f"rep_itest_{uuid4().hex[:12]}"
    admin = create_async_engine(f"{server}/postgres", isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception:
        await admin.dispose()
        pytest.skip("local Postgres unreachable or CREATE DATABASE denied")
    engine = create_async_engine(f"{server}/{name}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, admin, name


async def test_composite_version_lifecycle_isolated_db(tmp_path, monkeypatch):
    from app.models.schemas import FilmEditOp, FilmStoryboard, PendingPlan
    from app.models.tables import (
        Asset,
        AssetType,
        Output,
        Project,
        User,
        WorkflowRun,
        WorkflowStep,
    )
    from app.tools.film.edits import (
        FilmEditError,
        ensure_scene_ids,
        film_base_cut,
        film_version_identity_digest,
        prepare_film_patch,
    )
    from app.tools.film.storyboard import (
        DockStoryboard,
        LaunchFilm,
        build_film_execution_snapshot,
        build_text_manifest,
        canonical_film_params,
        film_design_state,
        load_storyboard_media,
        resolve_film_revision_base,
        storyboard_content_digest,
        storyboard_presentation,
        validate_storyboard,
    )
    from pydantic import TypeAdapter
    from sqlalchemy import select

    engine, admin, db_name = await _isolated_database()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # The run node's self-session seats (set_spec_field / set_summary) open
    # their OWN sessions — repoint the module's factory at the isolated
    # database so nothing escapes to the dev database.
    monkeypatch.setattr("app.pipeline.step_display.AsyncSessionLocal", factory)

    clip = tmp_path / "clip.mp4"
    _make_clip(clip)

    async def _local_download(key):
        return clip

    monkeypatch.setattr("app.providers.storage.download_to_cache", _local_download)

    try:
        async with factory() as db:
            user = User(email=f"itest-{uuid4().hex[:8]}@example.com", name="itest")
            db.add(user)
            await db.flush()
            project = Project(user_id=user.id, title="itest", language="zh")
            db.add(project)
            await db.flush()
            # Dormant upload: duration unknown (never ASR'd) — the write
            # seats must probe the bytes.
            asset = Asset(
                user_id=user.id,
                project_id=project.id,
                type=AssetType.VIDEO,
                file_url="itest/clip.mp4",
                title="clip",
            )
            db.add(asset)
            await db.flush()
            asset_id = str(asset.id)

            # ---- ① birth: probe + FULL validator (no violation filtering) --
            board = ensure_scene_ids(
                FilmStoryboard.model_validate(_board(asset_id, 2.5))
            )
            text_lines = build_text_manifest(TEXT)
            params = canonical_film_params(
                {
                    "text": TEXT,
                    "verbatim": False,
                    "voiceover": False,
                    "music_mood": "off",
                    "aspect": "16:9",
                    "language": "zh",
                }
            )
            media = await load_storyboard_media(db, project, board, probe_duration=True)
            probed = media.assets[asset_id].duration_seconds
            if probed is None or not (2.4 <= probed <= 2.6):
                pytest.skip(f"probe read {probed} for the 2.5s calibration clip")
            assert asset.duration_seconds == 2  # Integer floor (display seats)
            assert asset.meta["probed_duration_seconds"] == pytest.approx(probed)
            assert validate_storyboard(board, [], text_lines=text_lines, media=media) == []

            # ---- 素材发现座 (下批 A1): project-wide listing, tenant-scoped —
            # the probed duration surfaces, a FOREIGN project's asset never
            # lists, a transcript/text asset never lists.
            from app.tools.film.storyboard import project_media_candidates

            foreign_project = Project(user_id=user.id, title="foreign", language="zh")
            db.add(foreign_project)
            await db.flush()
            foreign_asset = Asset(
                user_id=user.id,
                project_id=foreign_project.id,
                type=AssetType.VIDEO,
                file_url="itest/foreign.mp4",
                title="foreign",
            )
            db.add(foreign_asset)
            db.add(
                Asset(
                    user_id=user.id,
                    project_id=project.id,
                    type=AssetType.TRANSCRIPT,
                    title="notes",
                )
            )
            second = Asset(
                user_id=user.id,
                project_id=project.id,
                type=AssetType.IMAGE,
                file_url="itest/pic.png",
                title="pic",
            )
            db.add(second)
            await db.flush()
            second_id = str(second.id)
            foreign_id = str(foreign_asset.id)
            candidates = await project_media_candidates(db, project)
            assert {c["id"] for c in candidates} == {asset_id, second_id}
            video_row = next(c for c in candidates if c["id"] == asset_id)
            assert video_row["duration_seconds"] == pytest.approx(probed)
            assert video_row["usable"] is True

            # ---- 复审③ pinned ordering: the user's explicit pick leads the
            # listing (a pick beyond the print cap still reaches the
            # director's context); pinning is filtered through the project
            # query itself — a FOREIGN id never materialises a row.
            pinned = await project_media_candidates(
                db, project, pinned_ids=[second_id, foreign_id]
            )
            assert pinned[0]["id"] == second_id
            assert {c["id"] for c in pinned} == {asset_id, second_id}

            # ---- 出生面 (下批 A2): a composite storyboard through the REAL
            # design wiring — the director is stubbed (the LLM seat), every
            # other seat is real: the discovery listing loads, the loader
            # resolves the media universe, assembly mints ids and derives
            # seconds on the frame law, the full validator faces the truth.
            from app.tools.film.storyboard import (
                FilmTextSource,
                draft_film_storyboard,
                film_text_director,
            )

            monkeypatch.setattr(
                "app.config.settings.film_edits_enabled", True
            )
            seen_call: dict = {}

            async def _direction(**kwargs):
                seen_call.update(kwargs)
                from app.tools.film.storyboard import FilmTextDirection

                return FilmTextDirection.model_validate(
                    {
                        "name": "itest-composite",
                        "segments": [
                            {"refs": [{"line": 1}]},
                            {
                                "elements": [
                                    {
                                        "kind": "video",
                                        "asset": asset_id,
                                        "source_start": 0.0,
                                        "source_end": 2.5,
                                        "rect": {"x": 0.5, "y": 0.0,
                                                 "w": 0.5, "h": 1.0},
                                    },
                                    {
                                        "kind": "text",
                                        "refs": [{"line": 2}, {"line": 3}],
                                        "until": 2.0,
                                        "rect": {"x": 0.05, "y": 0.2,
                                                 "w": 0.4, "h": 0.6},
                                    },
                                ]
                            },
                            {"refs": [{"line": 4}]},
                        ],
                    }
                )

            monkeypatch.setattr(film_text_director, "call", _direction)
            drafted = await draft_film_storyboard(
                db,
                project,
                instruction="组合片",
                voiceover=False,
                text_source=FilmTextSource(text=TEXT, verbatim=True),
                # 复审③: the user's @-pick (plus a foreign id — never
                # materialised) rides the draft seat into the director's
                # listing, pinned first.
                pinned_asset_ids=[second_id, foreign_id],
            )
            assert drafted is not None
            born, born_pages = drafted
            assert born_pages == []
            assert [s.type for s in born.scenes] == ["words", "composite", "words"]
            born_composite = born.scenes[1]
            assert [e.element_id for e in born_composite.elements] == ["e1", "e2"]
            # 2.5s span → 75f → scene = 75f snapped to the grid = 2.5s.
            assert born_composite.seconds == 2.5
            # The director's call carried the REAL discovery listing + gate —
            # the pinned pick leads, the foreign id never lists.
            assert seen_call["composite_ok"] is True
            assert seen_call["media"][0]["id"] == second_id
            assert {m["id"] for m in seen_call["media"]} == {asset_id, second_id}
            assert seen_call["media_more"] == 0


            # ---- 缺陷③ regression: the RE-READ keeps the sub-second truth —
            # a source window ending at the truth validates on later seats
            # (pre-fix the floored 2.0 falsely rejected source_end=2.5).
            reread = await load_storyboard_media(db, project, board)
            assert reread.assets[asset_id].duration_seconds == pytest.approx(probed)
            assert (
                validate_storyboard(board, [], text_lines=text_lines, media=reread)
                == []
            )

            # ---- ② version persist (the design beat's real seats) ---------
            execution = build_film_execution_snapshot(pages=[], track=None, media=media)
            dock = DockStoryboard(
                presentation=storyboard_presentation(board, [], media=media),
                storyboard=board.model_dump(mode="json"),
                fingerprint="itest-fp",
                execution=execution,
            )
            state = film_design_state(
                None,
                film=dock,
                design_params=params,
                review_hold=None,
                authorized_by="itest-birth",
            )
            project.pending_brief = PendingPlan(prompt="itest", **state).model_dump(
                mode="json"
            )
            await db.commit()

            # ---- ③ re-read -------------------------------------------------
            base = await resolve_film_revision_base(db, project)
            assert base is not None and base.film_storyboard_version == 1
            base_board = FilmStoryboard.model_validate(base.film_storyboard)
            scene = next(s for s in base_board.scenes if s.type == "composite")
            assert [e.element_id for e in scene.elements] == ["e1", "e2"]

            # The read seat's reference mint (same derivation as the chat
            # read tool: identity over board + params + version + cut).
            ref = film_version_identity_digest(
                base_board, base.film_storyboard_params, version=1,
                cut=film_base_cut(base),
            )

            # ---- 缺陷① regression: a tampered element numbering is a
            # DIFFERENT base — the minted reference stops applying.
            tampered = {
                **project.pending_brief,
                "film_storyboard": {
                    **project.pending_brief["film_storyboard"],
                    "scenes": [
                        *project.pending_brief["film_storyboard"]["scenes"][:1],
                        {
                            **project.pending_brief["film_storyboard"]["scenes"][1],
                            "elements": [
                                project.pending_brief["film_storyboard"]["scenes"][1]["elements"][0],
                                {
                                    **project.pending_brief["film_storyboard"]["scenes"][1]["elements"][1],
                                    "element_id": "e9",
                                },
                            ],
                        },
                        *project.pending_brief["film_storyboard"]["scenes"][2:],
                    ],
                },
            }
            project.pending_brief = tampered
            await db.commit()
            tampered_base = await resolve_film_revision_base(db, project)
            assert tampered_base is not None  # content digest still proves (id-free)
            with pytest.raises(FilmEditError) as exc:
                await prepare_film_patch(
                    db,
                    project,
                    base=tampered_base,
                    ops=[
                        TypeAdapter(FilmEditOp).validate_python(
                            {"op": "update_element", "scene_id": "s2",
                             "element_id": "e2", "at": 1.0}
                        )
                    ],
                    base_ref=ref,
                    instruction="改文字",
                )
            assert exc.value.code == "base_mismatch"
            # Restore the untampered version.
            project.pending_brief = {
                **tampered,
                "film_storyboard": dock.storyboard,
            }
            await db.commit()
            base = await resolve_film_revision_base(db, project)

            # ---- ④ partial edit (the real patch beat, real media probe) ---
            prepared = await prepare_film_patch(
                db,
                project,
                base=base,
                ops=[
                    TypeAdapter(FilmEditOp).validate_python(
                        {"op": "update_element", "scene_id": "s2",
                         "element_id": "e2",
                         "lines": ["改后的文字"], "enter_interval": 0.5}
                    )
                ],
                base_ref=ref,
                instruction="改文字",
            )
            assert prepared.change_set.edited[0].fields == [
                "elements.e2.enter_interval",
                "elements.e2.lines",
            ]
            patched = FilmStoryboard.model_validate(prepared.film.storyboard)
            pscene = next(s for s in patched.scenes if s.type == "composite")
            # The untouched video element is byte-identical (identity aside).
            old_video = next(
                e for e in scene.elements if e.kind == "video"
            ).model_dump(mode="json")
            new_video = next(
                e for e in pscene.elements if e.kind == "video"
            ).model_dump(mode="json")
            assert new_video == old_video
            assert storyboard_content_digest(patched) != storyboard_content_digest(
                base_board
            )

            # ---- persist v2 (the patch beat's state seat) ------------------
            state2 = film_design_state(
                base,
                film=prepared.film,
                design_params=prepared.params,
                review_hold=None,
                authorized_by="itest-patch",
                created_via="patch",
                change_set=prepared.change_set.model_dump(mode="json"),
                kept_frames=prepared.kept_frames,
                kept_reveal_onsets=prepared.kept_reveal_onsets,
            )
            project.pending_brief = PendingPlan(
                **{**project.pending_brief, **state2}
            ).model_dump(mode="json")
            await db.commit()
            pending2 = PendingPlan.model_validate(project.pending_brief)
            assert pending2.film_storyboard_version == 2

            # ---- ⑤ 确认版传递 + 编译执行 (the Start stamp + the node) ------
            run = WorkflowRun(
                project_id=project.id,
                context={
                    "prepared_storyboard": pending2.film_storyboard,
                    "film_storyboard_version": pending2.film_storyboard_version,
                    "film_storyboard_content_digest": (
                        pending2.film_storyboard_content_digest
                    ),
                    "film_storyboard_params": pending2.film_storyboard_params,
                    "film_storyboard_fingerprint": (
                        pending2.film_storyboard_fingerprint
                    ),
                    "film_execution": pending2.film_storyboard_execution,
                    "film_draft_token": pending2.film_draft_token,
                    "film_created_via": pending2.film_created_via,
                    "film_base_version": pending2.film_base_version,
                },
            )
            db.add(run)
            await db.flush()
            # The compiled slot carries the version's pinned params (the
            # plan→step handoff law — text rides the slot verbatim).
            slot_params = dict(pending2.film_storyboard_params or {})
            node = WorkflowStep(
                run_id=run.id,
                kind="launch_film",
                spec={"slot": {"type": "film", **slot_params}},
            )
            db.add(node)
            await db.commit()  # the node's self-session seats must see it

            out_ids = await LaunchFilm().run(db, run, node, project)
            await db.commit()

            assert len(out_ids) == 1
            output = await db.get(Output, out_ids[0])
            spec = output.render_spec
            assert spec is not None and spec["family"] == "film"
            cscene = spec["scenes"][1]
            assert cscene["type"] == "composite" and cscene["frames"] == 120
            video = cscene["elements"][0]
            assert video["src"] == "itest/clip.mp4"
            assert video["source_start"] == 0.0 and video["source_end"] == 2.5
            text_el = cscene["elements"][1]
            assert text_el["lines"] == ["改后的文字"]
            assert text_el["enter_interval"] == 0.5
            # 呈现稿 digest = run context digest = render spec digest.
            assert spec["provenance"]["storyboard_digest"] == (
                pending2.film_storyboard_content_digest
            )
            # The render mirror pended through the one pend seat.
            mirrors = list(
                (
                    await db.execute(
                        select(WorkflowStep).where(
                            WorkflowStep.run_id == run.id,
                            WorkflowStep.kind == "render",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(mirrors) == 1
            # No LLM/paid seat fired: the journey's only outbound call was
            # the (monkeypatched, local) storage download for the probe.
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(
                text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
            )
        await admin.dispose()
