"""film_stage_ledger.py — 失败分类台账（MG D4；仪表层——诊断尺子，读数供人工
判读，永不阻塞部署）。

数据源 = film 链节点的 ``spec.failure``（stage/codes/detail，D2 storyboard 两座
+ D4 probe 闸一座，同一字段形状）+ 节点/产物终态。五段通过率：

    schema      LLM 出参 schema 关（两击拒收终态）
    grounding   接地关（validator 穷尽，codes 含 TEXT_NOT_GROUNDED）
    constraint  约束关（validator 穷尽，codes 不含 TEXT_NOT_GROUNDED——
                UNSUPPORTED_SCENE / INVALID_FOCUS / DURATION_INVALID /
                CONSTRAINT_VIOLATION）
    render      渲染服务段（render 镜像节点失败且无 spec.failure = 传输/渲染
                服务侧；run-less film 产物 FAILED 同座归此）
    probe       文件校验闸（render 镜像节点 spec.failure.stage='probe'）

计数口径（一座一行的归因纪律）：launch_film done = schema/grounding/constraint
各记一次通过（过闸即前段皆过；中途 repair 轮不持久化，不单独计数）；节点失败
记在其终态段一次。render 镜像 done = render+probe 各记一次通过（probe 闸先于
COMPLETED）。读数用途 = 归因（哪段漏修哪段）——报告禁写"模型能力"式归因。

Usage (from apps/api/, DB reachable):
    uv run python scripts/film_stage_ledger.py [--since-days N]
"""

import argparse
import asyncio
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import Output, WorkflowStep  # noqa: E402

STAGES = ["schema", "grounding", "constraint", "render", "probe"]
# Validator codes that belong to the grounding bucket; every other validator
# code is a constraint violation (the validator terminal carries both stages'
# codes under stage="grounding" — the bucket split rides the code set).
_GROUNDING_CODES = {"TEXT_NOT_GROUNDED"}


def _failure(step: WorkflowStep) -> dict[str, Any]:
    spec = step.spec if isinstance(step.spec, dict) else {}
    failure = spec.get("failure")
    return failure if isinstance(failure, dict) else {}


def _terminal(status: Any) -> str:
    return str(status).lower()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since-days", type=int, default=None)
    args = parser.parse_args()
    since = (
        datetime.now(UTC) - timedelta(days=args.since_days)
        if args.since_days
        else None
    )

    passes: Counter[str] = Counter()
    fails: Counter[str] = Counter()
    code_counts: Counter[str] = Counter()
    unattributed: list[str] = []

    async with AsyncSessionLocal() as db:
        # launch_film nodes (schema / grounding / constraint stages).
        q = select(WorkflowStep).where(WorkflowStep.kind == "launch_film")
        if since is not None:
            q = q.where(WorkflowStep.created_at >= since)
        film_nodes = list((await db.execute(q)).scalars().all())

        # Render mirror steps link their output via spec.output_id (not the
        # FK) — collect film output ids, then the mirrors pointing at them.
        q = select(Output.id).where(Output.type == "film")
        film_output_ids = {str(r) for r in (await db.execute(q)).scalars().all()}
        q = select(WorkflowStep).where(WorkflowStep.kind == "render")
        if since is not None:
            q = q.where(WorkflowStep.created_at >= since)
        render_steps = [
            s
            for s in (await db.execute(q)).scalars().all()
            if str((s.spec or {}).get("output_id") or "") in film_output_ids
        ]

        # Run-less film outputs (fixtures / manual renders — no mirror step).
        q = select(Output).where(
            Output.type == "film", Output.workflow_step_id.is_(None)
        )
        if since is not None:
            q = q.where(Output.created_at >= since)
        runless_outputs = list((await db.execute(q)).scalars().all())

    for step in film_nodes:
        status = _terminal(step.status)
        failure = _failure(step)
        if status.endswith("done"):
            passes["schema"] += 1
            passes["grounding"] += 1
            passes["constraint"] += 1
            continue
        if not status.endswith("failed"):
            continue  # in-flight rows are not ledger data
        stage = failure.get("stage")
        codes = failure.get("codes") or []
        code_counts.update(codes)
        if stage == "schema":
            fails["schema"] += 1
        elif stage == "grounding":
            bucket = (
                "grounding" if _GROUNDING_CODES & set(codes) else "constraint"
            )
            fails[bucket] += 1
        else:
            unattributed.append(f"launch_film {step.id} (no failure stamp)")

    for step in render_steps:
        status = _terminal(step.status)
        failure = _failure(step)
        if status.endswith("done"):
            passes["render"] += 1
            passes["probe"] += 1
            continue
        if not status.endswith("failed"):
            continue
        code_counts.update(failure.get("codes") or [])
        if failure.get("stage") == "probe":
            fails["probe"] += 1
        else:
            fails["render"] += 1

    for output in runless_outputs:
        status = _terminal(output.render_status)
        if status.endswith("completed"):
            passes["render"] += 1
            passes["probe"] += 1
        elif status.endswith("failed"):
            fails["render"] += 1  # run-less rows carry no failure stamp

    print(f"film stage ledger (since: {since.date() if since else 'all time'})")
    print(f"{'stage':<12}{'pass':>6}{'fail':>6}{'pass_rate':>11}")
    for stage in STAGES:
        p, f = passes[stage], fails[stage]
        total = p + f
        rate = f"{p / total:.0%}" if total else "—"
        print(f"{stage:<12}{p:>6}{f:>6}{rate:>11}")
    print(
        f"\nrows: launch_film={len(film_nodes)} render_mirrors={len(render_steps)} "
        f"run_less_outputs={len(runless_outputs)}"
    )
    if code_counts:
        print("\nfailure codes (top):")
        for code, n in code_counts.most_common(10):
            print(f"  {code:<28}{n}")
    if unattributed:
        print("\nunattributed failures (no spec.failure stamp — inspect manually):")
        for line in unattributed[:10]:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
