"""Standalone script to seed the demo project using the real pipeline.

Run from the api directory:
    uv run python scripts/seed_demo.py
    uv run python scripts/seed_demo.py --force   # delete existing outputs and regenerate

This is useful for (re)generating demo outputs without starting the full API.
The regular API startup also calls ``seed_demo_project()`` automatically.

After seeding, the script verifies the RunPlan invariants (acceptance gate):
run terminal state, node states, per-node metering, clip output lineage and
completeness, and the internal content_plan output. Any failure exits 1.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select

from app.models.database import AsyncSessionLocal
from app.models.schemas import RenderStatus, WorkflowStatus
from app.models.tables import Asset, Output, PlanNode, WorkflowRun
from app.services.demo_seed import DEMO_PROJECT_ID, seed_demo_project
from app.services.storage import delete_prefix, get_project_output_dir

GEN_NODE_KINDS = ("preprocess", "persona_bootstrap", "director_plan", "clips_pipeline")
# Nodes that unconditionally hit the LLM and must therefore be metered.
METERED_NODE_KINDS = ("director_plan", "clips_pipeline")


async def _reset_demo_outputs() -> None:
    """Delete existing demo outputs, runs, and rendered files.

    The demo Asset row is removed too: ``seed_demo_project`` skips ASR when the
    asset is already COMPLETED, so without this a swapped demo video would be
    re-generated from the OLD transcript. The asset is recreated as PENDING,
    which re-triggers ASR on whatever now lives at the demo video object key.
    """
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Output).where(Output.project_id == DEMO_PROJECT_ID))
        await db.execute(delete(WorkflowRun).where(WorkflowRun.project_id == DEMO_PROJECT_ID))
        await db.execute(delete(Asset).where(Asset.project_id == DEMO_PROJECT_ID))
        await db.commit()

    output_prefix = get_project_output_dir(DEMO_PROJECT_ID, "demo")
    await delete_prefix(output_prefix)


class _Verifier:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        mark = "✓" if ok else "✗"
        line = f"  {mark} {label}" + (f" — {detail}" if detail and not ok else "")
        print(line)
        if not ok:
            self.failures.append(label)


async def _verify_demo_run() -> bool:
    """Assert the RunPlan invariants on the demo project's latest run."""
    async with AsyncSessionLocal() as db:
        run = (
            await db.execute(
                select(WorkflowRun)
                .where(WorkflowRun.project_id == DEMO_PROJECT_ID)
                .order_by(WorkflowRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        nodes = list(
            (
                await db.execute(
                    select(PlanNode).where(PlanNode.run_id == run.id).order_by(PlanNode.seq)
                )
            ).scalars()
        ) if run else []
        outputs = list(
            (
                await db.execute(
                    select(Output).where(Output.project_id == DEMO_PROJECT_ID)
                )
            ).scalars()
        )

    v = _Verifier()
    print("\nseed_demo verification:")

    # 1. Run terminal state.
    status_label = run.status.value if run is not None else "no run"
    v.check(
        run is not None and run.status == WorkflowStatus.COMPLETED,
        "run COMPLETED",
        f"status={status_label} error={run.error if run else ''}",
    )
    if run is None:
        return False

    # 2. Node states: generation nodes done; render fan-out pending (the
    # worker renders in the background and mirrors terminal state later).
    by_kind: dict[str, list[PlanNode]] = {}
    for n in nodes:
        by_kind.setdefault(n.kind, []).append(n)
    for kind in GEN_NODE_KINDS:
        kind_nodes = by_kind.get(kind, [])
        v.check(
            len(kind_nodes) == 1 and kind_nodes[0].status == "done",
            f"node {kind} done",
            f"statuses={[n.status for n in kind_nodes]}",
        )
    render_nodes = by_kind.get("render", [])
    v.check(
        len(render_nodes) == 5 and all(n.status == "pending" for n in render_nodes),
        "5 render nodes pending (awaiting worker)",
        f"count={len(render_nodes)} statuses={[n.status for n in render_nodes]}",
    )

    # 3. Per-node metering (ADR-025): LLM nodes carry token usage.
    for kind in METERED_NODE_KINDS:
        node = by_kind.get(kind, [None])[0]
        cost = (node.cost if node else None) or {}
        v.check(
            bool(cost.get("prompt_tokens")),
            f"node {kind} cost metered",
            f"cost={cost}",
        )

    # 4. Clip outputs: lineage + completeness.
    pipeline_id = by_kind["clips_pipeline"][0].id if by_kind.get("clips_pipeline") else None
    clips = [o for o in outputs if o.type == "clip"]
    v.check(len(clips) == 5, "5 clip outputs", f"count={len(clips)}")
    for o in clips:
        problems = []
        if pipeline_id is not None and o.plan_node_id != pipeline_id:
            problems.append("plan_node_id")
        if o.render_status != RenderStatus.PENDING:
            problems.append(f"render_status={o.render_status}")
        if not o.payload.get("hook") or not o.payload.get("title_options"):
            problems.append("payload")
        if not (o.source_ref or {}).get("segment"):
            problems.append("source_ref")
        if not o.render_spec:
            problems.append("render_spec")
        if not (o.publishing or {}).get("title"):
            problems.append("publishing")
        score = o.score or {}
        if not isinstance(score.get("value"), int) or not 1 <= score["value"] <= 100:
            problems.append(f"score.value={score.get('value')}")
        if not score.get("reason"):
            problems.append("score.reason")
        v.check(not problems, f"clip {str(o.id)[:8]} lineage+complete", ",".join(problems))

    # 5. Internal content_plan output from the director node.
    director_id = by_kind["director_plan"][0].id if by_kind.get("director_plan") else None
    plans = [o for o in outputs if o.type == "content_plan"]
    v.check(
        len(plans) == 1 and plans[0].plan_node_id == director_id,
        "content_plan internal output present",
        f"count={len(plans)}",
    )

    print(
        "note: render nodes flip done and files.video fills in once the "
        "worker renders the queued clips in the background."
    )
    return not v.failures


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the demo project")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing demo outputs and regenerate from scratch",
    )
    args = parser.parse_args()

    if args.force:
        await _reset_demo_outputs()

    await seed_demo_project()

    if not await _verify_demo_run():
        sys.exit(1)
    print("\nseed_demo: all checks passed")


if __name__ == "__main__":
    asyncio.run(main())
