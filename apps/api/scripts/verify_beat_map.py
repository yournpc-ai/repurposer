"""期 1 acceptance harness — beat map + 素材理解前移 (docs/tasks/output-quality-line.md).

Runs the acceptance trio end-to-end against the REAL pipeline (no mocks):

1. **节拍地图字段齐** — a long lecture (xy_2.mp4, 780 s keynote) is processed
   and warmed; the understanding payload must carry populated beat-map
   fields (topic_boundaries / climax_spans / emphasis_words /
   quotable_lines / narrative_role_hints) with code-resolved times.
2. **词级时间戳零覆写** — asset.meta is deep-equal before/after the warm,
   and every resolved beat-map time is a verbatim ASR word boundary
   (constructive proof: times come FROM the axis, never invented).
3. **同素材二次上传零 LLM** — the same bytes re-uploaded to a second project
   (fresh storage key) hit the content-addressed reuse: exactly one
   understanding row exists for that content across the user's projects.

Usage (worker stopped — the script drives process_asset itself):
    uv run python scripts/verify_beat_map.py [--keep]

Cleans up its rows (FK order) and storage keys unless --keep is passed.
"""

import asyncio
import copy
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.schemas import AssetStatus, AssetType  # noqa: E402
from app.models.tables import Asset, Output, Project, User  # noqa: E402
from app.pipeline.asset_processing import _warm_tasks, process_asset  # noqa: E402
from app.pipeline.node_runners import (  # noqa: E402
    _find_reusable_understanding,
    warm_understanding,
)
from app.providers.storage import delete, download_to_temp, get_upload_path, save  # noqa: E402

VERIFY_EMAIL = "beatmap-verify@local"
LONG_KEY = "demo/uploads/xy_2.mp4"  # 780 s keynote — the lecture leg
SHORT_BYTES_SOURCE = "demo/uploads/xy_2_15s.mp4"  # the reuse leg


async def _mk_project(db, user, title: str) -> Project:
    project = Project(user_id=user.id, title=title, language="en")
    db.add(project)
    await db.flush()
    return project


async def _mk_asset(db, user, project, key: str, title: str, atype=AssetType.VIDEO) -> Asset:
    # Rows are created pre-claimed (PROCESSING): the script drives
    # process_asset directly, and a live worker must never see them PENDING.
    asset = Asset(
        user_id=user.id,
        project_id=project.id,
        type=atype,
        file_url=key,
        title=title,
        processing_status=AssetStatus.PROCESSING,
    )
    db.add(asset)
    await db.flush()
    return asset


async def _process_and_warm(asset_id: UUID) -> None:
    await process_asset(asset_id)
    if _warm_tasks:
        await asyncio.gather(*list(_warm_tasks), return_exceptions=True)


async def _get_asset(asset_id: UUID) -> Asset:
    async with AsyncSessionLocal() as db:
        asset = await db.get(Asset, asset_id)
        assert asset is not None
        db.expunge(asset)
        return asset


async def _understanding_rows(db, user_id: UUID) -> list[Output]:
    return list(
        (
            await db.execute(
                select(Output)
                .join(Project, Output.project_id == Project.id)
                .where(
                    Project.user_id == user_id,
                    Output.type == "material_understanding",
                )
            )
        )
        .scalars()
        .all()
    )


def _check_beat_map(payload: dict, words: list[dict]) -> None:
    """Acceptance 1+2: every field populated; resolved times sit exactly on
    ASR word boundaries (starts on word.start, ends on word.end)."""
    starts = {round(float(w["start"]), 3) for w in words}
    ends = {round(float(w["end"]), 3) for w in words}

    def on_axis(start, end):
        if start is None:
            return True  # unresolved anchor: honest None, never fabricated
        if round(float(start), 3) not in starts:
            return False
        return end is None or round(float(end), 3) in ends

    def offenders(rows):
        return [r for r in rows if not on_axis(r["start"], r["end"])]

    boundaries = payload["topic_boundaries"]
    assert len(boundaries) >= 3, f"topic_boundaries too few: {len(boundaries)}"
    resolved = [b for b in boundaries if b["start"] is not None]
    assert resolved, "no topic boundary resolved onto the word axis"
    assert not offenders(boundaries), f"boundary off-axis: {offenders(boundaries)[:1]}"
    assert all(b["asset_id"] for b in resolved), "boundary missing asset_id"

    climax = payload["climax_spans"]
    assert len(climax) >= 1, "climax_spans empty"
    assert any(c["start"] is not None for c in climax), "no climax resolved"
    assert not offenders(climax), f"climax off-axis: {offenders(climax)[:1]}"

    emphasis = payload["emphasis_words"]
    assert len(emphasis) >= 3, f"emphasis_words too few: {len(emphasis)}"
    assert any(e["start"] is not None for e in emphasis), "no emphasis word resolved"
    bad = [e for e in emphasis if not on_axis(e["start"], None)]
    assert not bad, f"emphasis off-axis: {bad[:1]}"

    quotes = payload["quotable_lines"]
    assert len(quotes) >= 3, f"quotable_lines too few: {len(quotes)}"
    assert any(q["start"] is not None for q in quotes), "no quotable line resolved"
    assert not offenders(quotes), f"quote off-axis: {offenders(quotes)[:1]}"
    assert all(isinstance(q["self_contained"], bool) for q in quotes)

    hints = payload["narrative_role_hints"]
    assert len(hints) >= 2, f"narrative_role_hints too few: {len(hints)}"
    assert {h["role"] for h in hints} <= {"setup", "payoff", "example", "transition"}
    assert not offenders(hints), f"hint off-axis: {offenders(hints)[:1]}"

    print(
        f"  beat map: {len(boundaries)} boundaries ({len(resolved)} timed) · "
        f"{len(climax)} climax · {len(emphasis)} emphasis · "
        f"{len(quotes)} quotes ({sum(1 for q in quotes if q['self_contained'])} self-contained) · "
        f"{len(hints)} role hints",
        flush=True,
    )


async def main() -> None:
    keep = "--keep" in sys.argv
    user_id: UUID | None = None
    extra_keys: list[str] = []
    try:
        async with AsyncSessionLocal() as db:
            user = (
                await db.execute(select(User).where(User.email == VERIFY_EMAIL))
            ).scalars().one_or_none()
            if user is None:
                user = User(email=VERIFY_EMAIL, name="beatmap-verify")
                db.add(user)
                await db.flush()
            user_id = user.id

            # ---- Leg 1: long lecture → beat map + zero-overwrite ----
            project_a = await _mk_project(db, user, "verify: lecture beat map")
            asset_a = await _mk_asset(db, user, project_a, LONG_KEY, "xy_2.mp4")
            await db.commit()
            project_a_id, asset_a_id = project_a.id, asset_a.id

        print("[leg 1] processing 780 s lecture (ASR + speaker_map + prosody)…", flush=True)
        await _process_and_warm(asset_a_id)

        asset_after = await _get_asset(asset_a_id)
        meta = asset_after.meta or {}
        assert meta.get("content_sha256"), "content_sha256 missing after processing"
        assert meta.get("words"), "words missing after processing"
        assert meta.get("prosody"), "prosody missing after processing"
        print(
            f"[leg 1] processed: {len(meta['words'])} words · "
            f"{len(meta['prosody']['emphasis_peaks'])} acoustic peaks · "
            f"sha {meta['content_sha256'][:12]}…",
            flush=True,
        )

        async with AsyncSessionLocal() as db:
            rows = await _understanding_rows(db, user_id)
        assert len(rows) == 1, f"expected 1 warmed understanding, got {len(rows)}"
        row = rows[0]
        assert row.project_id == project_a_id
        assert row.workflow_step_id is None, "warm row must carry no step lineage"
        assert (row.source_ref or {}).get("warmed") is True
        digest = (row.source_ref or {})["asset_hash"]
        payload = row.payload
        _check_beat_map(payload, meta["words"])

        # Zero-overwrite: re-run the warm — the reuse hit must leave the
        # asset meta and the row count untouched (idempotent).
        meta_snapshot = copy.deepcopy(meta)
        await warm_understanding(project_a_id)  # reuse hit — no LLM, no writes
        asset_now = await _get_asset(asset_a_id)
        assert asset_now.meta == meta_snapshot, "asset.meta mutated across warm"
        async with AsyncSessionLocal() as db:
            assert len(await _understanding_rows(db, user_id)) == 1, "warm is not idempotent"
        print("[leg 1] zero-overwrite + idempotent warm OK", flush=True)

        # The run-path reuse sees the warm row from the same project.
        async with AsyncSessionLocal() as db:
            project_a = await db.get(Project, project_a_id)
            hit = await _find_reusable_understanding(db, project_a, digest)
            assert hit is not None and hit.id == row.id
        print("[leg 1] run-path reuse resolves the warm row OK", flush=True)

        # ---- Leg 2: same bytes, second project → zero LLM ----
        src = await download_to_temp(SHORT_BYTES_SOURCE)
        assert src is not None, f"demo asset missing from storage: {SHORT_BYTES_SOURCE}"
        payload_bytes = src.read_bytes()
        src.unlink(missing_ok=True)

        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            project_b1 = await _mk_project(db, user, "verify: reuse first upload")
            key1 = await get_upload_path(project_b1.id, user_id, "clip-a.mp4")
            await save(key1, payload_bytes, content_type="video/mp4")
            extra_keys.append(key1)
            asset_b1 = await _mk_asset(db, user, project_b1, key1, "clip-a.mp4")
            await db.commit()
            asset_b1_id = asset_b1.id
        await _process_and_warm(asset_b1_id)

        async with AsyncSessionLocal() as db:
            rows = await _understanding_rows(db, user_id)
        assert len(rows) == 2, f"first upload should materialize once, got {len(rows)} rows"
        row_b1 = next(r for r in rows if r.project_id != project_a_id)
        digest_b = (row_b1.source_ref or {})["asset_hash"]

        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            project_b2 = await _mk_project(db, user, "verify: reuse second upload")
            key2 = await get_upload_path(project_b2.id, user_id, "clip-b.mp4")
            await save(key2, payload_bytes, content_type="video/mp4")
            extra_keys.append(key2)
            asset_b2 = await _mk_asset(db, user, project_b2, key2, "clip-b.mp4")
            await db.commit()
            asset_b2_id, project_b2_id = asset_b2.id, project_b2.id
        await _process_and_warm(asset_b2_id)

        asset_b2_row = await _get_asset(asset_b2_id)
        asset_b1_row = await _get_asset(asset_b1_id)
        assert (
            asset_b2_row.meta["content_sha256"] == asset_b1_row.meta["content_sha256"]
        ), "same bytes must hash identically across uploads"

        async with AsyncSessionLocal() as db:
            rows = await _understanding_rows(db, user_id)
        assert len(rows) == 2, (
            f"second upload must NOT materialize a new understanding (zero LLM), "
            f"got {len(rows)} rows"
        )
        # And the run path in project B2 resolves the FIRST upload's row.
        async with AsyncSessionLocal() as db:
            project_b2 = await db.get(Project, project_b2_id)
            hit = await _find_reusable_understanding(db, project_b2, digest_b)
            assert hit is not None and hit.id == row_b1.id
        print("[leg 2] same-bytes second upload → reuse hit, zero LLM OK", flush=True)

        # ---- Leg 3: image-bearing project → visual anchors, both halves ----
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            project_c = await _mk_project(db, user, "verify: visual anchors")
            await _mk_asset(
                db, user, project_c, "demo/uploads/demo-article.md", "article.md",
                atype=AssetType.TRANSCRIPT,
            )
            image_ids: list[UUID] = []
            for name in ("title", "industries", "outcomes"):
                img = await _mk_asset(
                    db, user, project_c, f"demo/uploads/teasers-photo-{name}.jpg",
                    f"teasers-photo-{name}.jpg", atype=AssetType.IMAGE,
                )
                image_ids.append(img.id)
            await db.commit()
            project_c_id = project_c.id

        print("[leg 3] processing doc + 3 photos (extract + hashes + vision)…", flush=True)
        for image_id in image_ids:
            await process_asset(image_id)
        async with AsyncSessionLocal() as db:
            doc = (
                await db.execute(
                    select(Asset).where(
                        Asset.project_id == project_c_id,
                        Asset.type == AssetType.TRANSCRIPT,
                    )
                )
            ).scalars().one()
            doc_id = doc.id
        await process_asset(doc_id)
        if _warm_tasks:
            await asyncio.gather(*list(_warm_tasks), return_exceptions=True)

        det_halves = []
        for image_id in image_ids:
            img = await _get_asset(image_id)
            anchors = (img.meta or {}).get("visual_anchors")
            assert anchors and anchors["width"] > 0, f"deterministic half missing: {image_id}"
            det_halves.append(len(anchors["faces"]))
        async with AsyncSessionLocal() as db:
            rows = await _understanding_rows(db, user_id)
        row_c = next(r for r in rows if r.project_id == project_c_id)
        semantic = row_c.payload.get("visual_anchors") or []
        assert semantic, "semantic half (LLM labels) missing on image project"
        resolved = [v for v in semantic if v.get("asset_id")]
        assert resolved, f"no visual anchor resolved to an asset_id: {semantic[:1]}"
        known = {str(i) for i in image_ids}
        assert all(v["asset_id"] in known for v in resolved), "anchor joined to foreign asset"
        print(
            f"[leg 3] visual anchors: {len(semantic)} semantic rows "
            f"({len(resolved)} asset-joined) · deterministic faces per photo {det_halves}",
            flush=True,
        )

        print("verify_beat_map: ALL ACCEPTANCE CHECKS PASSED (三件套 + visual anchors 双半)", flush=True)
    finally:
        if not keep and user_id is not None:
            async with AsyncSessionLocal() as db:
                outputs = await _understanding_rows(db, user_id)
                for o in outputs:
                    await db.delete(o)
                assets = (
                    await db.execute(select(Asset).where(Asset.user_id == user_id))
                ).scalars().all()
                for a in assets:
                    await db.delete(a)
                projects = (
                    await db.execute(select(Project).where(Project.user_id == user_id))
                ).scalars().all()
                for p in projects:
                    await db.delete(p)
                user = await db.get(User, user_id)
                if user is not None:
                    await db.delete(user)
                await db.commit()
            for key in extra_keys:
                await delete(key)
            print("cleaned up (outputs → assets → projects → user, storage keys)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
