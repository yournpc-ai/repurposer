"""Targeted cleanup for retired text products, Film and legacy Clip history.

Dry-run is the default. --apply writes a resumable plan under /tmp, commits DB
changes before deleting object bytes, and never removes shared source material,
new Composition inputs, user prose, ledgers or migration history.
"""
from __future__ import annotations

# ruff: noqa: E402

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AsyncSessionLocal
from app.models.tables import (
    Asset,
    CompositionVersion,
    Message,
    Output,
    Publication,
    SourceSnapshot,
    WorkflowRun,
    WorkflowStep,
    WorkflowStatus,
)
from app.providers.storage import delete_file

COPY_TYPES = frozenset({"article", "post", "quote", "quotes", "quote_frame", "carousel"})
COPY_TASKS = frozenset({"write_post", "write_article", "write_quotes", "write_carousel", "revise_script", "research"})
CLIP_TASKS = frozenset({
    "select_clips", "cut_segments", "materialize_source", "translate_clip", "dub_clip",
    "remove_filler", "add_music", "reframe_clip", "align_stills",
})
RETIRED_TASKS = COPY_TASKS | CLIP_TASKS
OUTPUT_REF_KEYS = {"output_refs", "output_ids", "target_output_ids"}
SINGULAR_OUTPUT_KEYS = {"output_id", "target_output_id", "derived_from_output_id", "parent_output_id"}


@dataclass
class CleanupPlan:
    include_clips: bool
    output_ids: list[str] = field(default_factory=list)
    step_ids: list[str] = field(default_factory=list)
    storage_keys: list[str] = field(default_factory=list)
    preserved_output_ids: list[str] = field(default_factory=list)
    external_publications: list[dict] = field(default_factory=list)
    deleted_storage_keys: list[str] = field(default_factory=list)
    failed_storage_keys: dict[str, str] = field(default_factory=dict)


def output_files(output: Output) -> set[str]:
    keys = {
        value for value in (output.files or {}).values()
        if isinstance(value, str) and value and not value.startswith(("http://", "https://"))
    }
    cover = (output.publishing or {}).get("cover_image_url")
    if isinstance(cover, str) and cover and not cover.startswith(("http://", "https://")):
        keys.add(cover)
    return keys


def parents(output: Output) -> set[str]:
    return {str(item) for item in (output.source_ref or {}).get("parents", [])}


def scrub(value, output_ids: set[str], retired_tasks: frozenset[str] = RETIRED_TASKS):
    if isinstance(value, list):
        return [scrub(item, output_ids, retired_tasks) for item in value if not (
            isinstance(item, str) and item in output_ids
            or isinstance(item, dict) and item.get("tool") in retired_tasks
        )]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in OUTPUT_REF_KEYS and isinstance(item, list):
                result[key] = [ref for ref in item if str(ref) not in output_ids]
            elif key in SINGULAR_OUTPUT_KEYS and str(item) in output_ids:
                result[key] = None
            elif key == "mentions" and isinstance(item, list):
                result[key] = [mention for mention in item if not (
                    isinstance(mention, dict) and mention.get("type") == "output"
                    and str(mention.get("id")) in output_ids
                )]
            elif key == "focus_output" and isinstance(item, dict) and str(item.get("id")) in output_ids:
                result[key] = None
            else:
                result[key] = scrub(item, output_ids, retired_tasks)
        return result
    return value


async def used_snapshot_ids(db: AsyncSession) -> set[str]:
    rows = (await db.execute(select(CompositionVersion.sources))).scalars().all()
    return {
        str(binding.get("snapshot_id"))
        for sources in rows
        for binding in sources or []
        if isinstance(binding, dict) and binding.get("snapshot_id")
    }


async def select_targets(db: AsyncSession, include_clips: bool) -> tuple[list[Output], list[Output]]:
    outputs = list((await db.execute(select(Output))).scalars().all())
    by_id = {str(output.id): output for output in outputs}
    composition_outputs = {str(output.id) for output in outputs if output.composition_version_id is not None}
    targets = {
        str(output.id) for output in outputs
        if output.type in COPY_TYPES | {"film"} and str(output.id) not in composition_outputs
    }
    if include_clips:
        targets.update(
            str(output.id) for output in outputs
            if output.type == "clip" and str(output.id) not in composition_outputs
        )
        targets.update(str(output.id) for output in outputs if output.type in {"storyboard", "craft_skeleton", "content_plan"})
    else:
        for output in outputs:
            source = output.source_ref or {}
            if output.type == "clip" and (source.get("quote_card") or source.get("quote_chain")):
                targets.add(str(output.id))
        steps = list((await db.execute(select(WorkflowStep).where(WorkflowStep.kind == "write_quotes"))).scalars().all())
        targets.update(str(ref) for step in steps for ref in step.output_refs or [])
    targets.difference_update(composition_outputs)
    changed = True
    while changed:
        changed = False
        for output in outputs:
            if str(output.id) not in composition_outputs and str(output.id) not in targets and parents(output) & targets:
                targets.add(str(output.id))
                changed = True
    used = await used_snapshot_ids(db)
    preserved = set()
    snapshots = list((await db.execute(select(SourceSnapshot))).scalars().all())
    for snapshot in snapshots:
        origin = (snapshot.meta or {}).get("origin")
        output_id = str(origin.get("output_id") or "") if isinstance(origin, dict) else ""
        if output_id in targets and str(snapshot.id) in used:
            preserved.add(output_id)
    for output in outputs:
        if output.type == "video":
            preserved.update(parents(output) & targets)
    pending = list(preserved)
    while pending:
        output_id = pending.pop()
        for parent_id in parents(by_id[output_id]) & targets - preserved:
            preserved.add(parent_id)
            pending.append(parent_id)
    doomed = [by_id[output_id] for output_id in sorted(targets - preserved)]
    kept = [by_id[output_id] for output_id in sorted(preserved)]
    return doomed, kept


async def target_steps(db: AsyncSession, include_clips: bool, output_ids: set[str]) -> list[WorkflowStep]:
    steps = list((await db.execute(select(WorkflowStep))).scalars().all())
    kinds = RETIRED_TASKS if include_clips else COPY_TASKS
    return [
        step for step in steps
        if step.kind in kinds
        or str((step.spec or {}).get("output_id") or "") in output_ids
        or (step.kind == "write_quotes" and not include_clips)
    ]


async def external_publications(db: AsyncSession, output_ids: set[str]) -> list[Publication]:
    rows = list((await db.execute(select(Publication).where(Publication.output_id.in_(output_ids)))).scalars().all())
    return [row for row in rows if row.published_at is not None or row.platform_post_id or row.platform_post_url]


async def shared_storage_keys(db: AsyncSession, doomed_output_ids: set[str]) -> set[str]:
    shared = set((await db.execute(select(SourceSnapshot.storage_key))).scalars().all())
    shared.update((await db.execute(select(Asset.file_url))).scalars().all())
    query = select(Output)
    if doomed_output_ids:
        query = query.where(Output.id.notin_(list(doomed_output_ids)))
    rows = list((await db.execute(query)).scalars().all())
    for output in rows:
        shared.update(output_files(output))
    return {key for key in shared if isinstance(key, str) and key}


async def make_plan(db: AsyncSession, include_clips: bool) -> CleanupPlan:
    doomed, preserved = await select_targets(db, include_clips)
    output_ids = {str(output.id) for output in doomed}
    external = await external_publications(db, output_ids)
    external_ids = {str(row.output_id) for row in external}
    doomed = [output for output in doomed if str(output.id) not in external_ids]
    output_ids = {str(output.id) for output in doomed}
    steps = await target_steps(db, include_clips, output_ids)
    shared = await shared_storage_keys(db, output_ids)
    keys = sorted({key for output in doomed for key in output_files(output) if key not in shared})
    return CleanupPlan(
        include_clips=include_clips,
        output_ids=sorted(output_ids),
        step_ids=[str(step.id) for step in steps],
        storage_keys=keys,
        preserved_output_ids=[str(output.id) for output in preserved],
        external_publications=[{
            "id": str(row.id),
            "output_id": str(row.output_id),
            "state": str(row.state),
            "platform_post_id": row.platform_post_id,
            "platform_post_url": row.platform_post_url,
        } for row in external],
    )


async def print_plan(db: AsyncSession, plan: CleanupPlan) -> None:
    print(f"scope: {'copy + Film + legacy Clip' if plan.include_clips else 'copy + Film + quote derivatives'}")
    print(f"outputs: {len(plan.output_ids)}")
    print(f"run/render steps: {len(plan.step_ids)}")
    print(f"storage objects: {len(plan.storage_keys)}")
    print(f"preserved shared Outputs: {len(plan.preserved_output_ids)}")
    if plan.output_ids:
        print("output ids:", ", ".join(plan.output_ids))
    if plan.preserved_output_ids:
        print("preserved ids:", ", ".join(plan.preserved_output_ids))
    if plan.external_publications:
        print("EXTERNAL PUBLICATIONS — left untouched, requires separate decision:")
        for publication in plan.external_publications:
            print(json.dumps(publication, ensure_ascii=False))


async def apply_plan(db: AsyncSession, plan: CleanupPlan, *, cancel_queued: bool) -> None:
    output_uuids = [uuid.UUID(item) for item in plan.output_ids]
    step_uuids = [uuid.UUID(item) for item in plan.step_ids]
    active = list((await db.execute(select(WorkflowStep).where(
        WorkflowStep.status.in_(["pending", "running", "waiting"]),
        WorkflowStep.kind.in_(RETIRED_TASKS if plan.include_clips else COPY_TASKS),
    ))).scalars().all())
    if active and not cancel_queued:
        raise RuntimeError(f"retired tasks are still active: {[str(step.id) for step in active]}")
    if active:
        await db.execute(update(WorkflowStep).where(
            WorkflowStep.id.in_([step.id for step in active])
        ).values(status="cancelled"))
        await db.execute(update(WorkflowRun).where(
            WorkflowRun.id.in_(list({step.run_id for step in active}))
        ).values(status=WorkflowStatus.CANCELLED))
    messages = list((await db.execute(select(Message))).scalars().all())
    output_ids = set(plan.output_ids)
    for message in messages:
        message.intent = scrub(message.intent, output_ids)
        message.mentions = scrub(message.mentions, output_ids)
        message.focus_output = scrub(message.focus_output, output_ids)
        message.question = scrub(message.question, output_ids)
        message.blocks = scrub(message.blocks, output_ids)
    runs = list((await db.execute(select(WorkflowRun))).scalars().all())
    for run in runs:
        run.context = scrub(run.context, output_ids)
    if output_uuids:
        if await db.scalar(text("SELECT to_regclass('public.operations')")):
            await db.execute(text("DELETE FROM operations WHERE output_id = ANY(:ids)"), {"ids": output_uuids})
        await db.execute(delete(Publication).where(Publication.output_id.in_(output_uuids)))
    if step_uuids:
        await db.execute(delete(WorkflowStep).where(WorkflowStep.id.in_(step_uuids)))
    if output_uuids:
        await db.execute(delete(Output).where(Output.id.in_(output_uuids)))
    await db.commit()


async def delete_storage(plan: CleanupPlan) -> None:
    remaining = set(plan.storage_keys) - set(plan.deleted_storage_keys) - set(plan.failed_storage_keys)
    for key in sorted(remaining):
        try:
            await delete_file(key)
        except Exception as exc:
            plan.failed_storage_keys[key] = str(exc)
        else:
            plan.deleted_storage_keys.append(key)


def plan_path(plan: CleanupPlan) -> Path:
    return Path(f"/tmp/retired-products-cleanup-{plan.output_ids[0][:12] if plan.output_ids else 'empty'}.json")


def save_plan(plan: CleanupPlan, path: Path) -> None:
    path.write_text(json.dumps(plan.__dict__, ensure_ascii=False, indent=2))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--legacy-clips", action="store_true", help="Also remove ordinary old Clip history")
    parser.add_argument("--cancel-queued", action="store_true", help="Cancel active retired tasks before cleanup")
    parser.add_argument("--resume", type=Path, help="Resume storage deletion from a previous plan")
    args = parser.parse_args()
    if args.resume:
        plan = CleanupPlan(**json.loads(args.resume.read_text()))
        await delete_storage(plan)
        if plan.failed_storage_keys:
            print("remaining failures:", plan.failed_storage_keys)
            save_plan(plan, args.resume)
            raise SystemExit(1)
        args.resume.unlink()
        print("cleanup complete")
        return
    async with AsyncSessionLocal() as db:
        plan = await make_plan(db, args.legacy_clips)
        await print_plan(db, plan)
        if not args.apply:
            print("DRY-RUN only; use --apply to commit the listed targets")
            return
        path = plan_path(plan)
        save_plan(plan, path)
        await apply_plan(db, plan, cancel_queued=args.cancel_queued)
        await delete_storage(plan)
        if plan.failed_storage_keys:
            save_plan(plan, path)
            print(f"storage failures; resume with --resume {path}: {plan.failed_storage_keys}")
            raise SystemExit(1)
        path.unlink(missing_ok=True)
        print(f"committed {len(plan.output_ids)} Outputs; deleted {len(plan.deleted_storage_keys)} objects")


if __name__ == "__main__":
    asyncio.run(main())
