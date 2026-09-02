"""Verify — the 质检环 v2 node (产物质量线期 3, docs/tasks/output-quality-line.md §2.4).

One verify node trails every generation executor at compile time
(``spec.for`` = the executor's output type). The loop runs entirely on the
graph's own machinery (ADR-047 节点内有界环 — never a tool-loop):

1. **确定性优先**: the per-type matrix (``pipeline/quality.py``) is zero-LLM;
   the LLM judge (quotes readability, §2.7 discipline) is advisory-only until
   the human calibration set lands — its verdicts record as ``cls="judge"``
   (the 机制信号 ledger), never gate.
2. **逐轮独立打分 + best-not-last**: every round is checked independently; a
   regressed repair round restores the BEST earlier round from the snapshot
   (``spec.rounds``) instead of keeping the worse last round.
3. **字段白名单最小 diff**: the bounce feedback names the flagged outputs and
   their failed checks; the next round's ``repair_scope`` surveillance check
   flags rewrites outside that whitelist (drift = a new failure).
4. **首轮通过即跳轮**: a clean first round never bounces (by construction).
5. **双败升级**: the bounce budget is 2 (the executor runs at most 3 times).
   Exhausted FIDELITY failures write the non-blocking ``needs_human``
   verdict; exhausted CRAFT failures on clips dock an escalation question
   (降级接受 default — the TTL sweep auto-accepts, 离开不中断 / 标题卡开场 —
   journaled as a real ``set_title`` op + re-render) and park via ``Suspend``
   (the direction interrupt's waiting seat, generalized to any kind).
6. **失败路由判据**: what a node-internal repair can fix rides the bounce;
   what needs information beyond the executor's domain is what the escalation
   hands back to the user (the replanning edge itself belongs to the
   自适应重规划 pool item, not this node).

Verify judges and bounces — it never edits content itself (修归 executor).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import bindparam, delete, text as _text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import Agent
from app.models.schemas import (
    AskOption,
    AskPayload,
    AssetType,
    QuoteReadability,
    RenderStatus,
)
from app.models.tables import Output, WorkflowStep, Project, WorkflowRun
from app.pipeline.edges import _load_understanding, _upstream_by_kind
from app.pipeline.graph import NodeBase, estimate_agent, estimate_free
from app.pipeline.quality import (
    CheckResult,
    _kept_span,
    _normalize,
    failed_checks,
    run_checks,
)
from app.pipeline.step_context import _list_assets
from app.pipeline.step_display import _set_summary
from app.platform.project_context import collect_asset_texts, resolve_persona
from app.providers.storage import stream_url

logger = structlog.get_logger()

# 打回预算 (旧简报期 3 保留): verify attempts 1–2 may bounce; the attempt that
# exceeds the budget takes the terminal verdict (executor runs ≤ 3 times).
_MAX_BOUNCES = 2


def _assemble_judge(items: list[dict[str, Any]]):
    """Judge inputs — content only, no ids / round / provenance (§2.7 盲)."""
    return ({"items": items}, [])


verify_judge: Agent[QuoteReadability] = Agent(
    name="verify_judge",
    prompt="verify_judge.j2",
    schema=QuoteReadability,
    system=(
        "You are a meticulous readability reviewer for quote cards. You cite "
        "the context before you judge, and you never score."
    ),
    temperature=0.0,  # §2.7: temp 0 + structured output
    assemble=_assemble_judge,
)


def _quote_context(quote: str, source_texts: list[str], window: int = 2) -> str:
    """The quote's source neighborhood (±window sentences around the best
    fuzzy match) — the judge's context evidence."""
    needle = _normalize(quote)
    if not needle:
        return "(no quote text)"
    best_ratio, best_sents, best_idx = 0.0, [], 0
    for source in source_texts:
        sents = [
            s.strip()
            for s in re.split(r"[.?!。！？;；\n]+", source or "")
            if s.strip()
        ]
        for i, sent in enumerate(sents):
            ratio = SequenceMatcher(None, needle, _normalize(sent)).ratio()
            if ratio > best_ratio:
                best_ratio, best_sents, best_idx = ratio, sents, i
    if not best_sents:
        return "(quote not found in the source material)"
    lo, hi = max(0, best_idx - window), min(len(best_sents), best_idx + window + 1)
    return " … ".join(best_sents[lo:hi])


class Verify(NodeBase):
    kind = "verify"
    task_name = "Check quality"
    task_name_zh = "质检"
    agents = (verify_judge,)
    # 质检是产物的属性，不是图上的独立节点 (ADR-041 D6 修订):
    # 通过时安静投影到产物卡，失败时产物卡变红/带徽章。
    canvas_hidden = True

    def estimate(self, ctx: dict) -> dict | None:
        """Free for the deterministic matrix; the quotes judge adds one small
        text-only call (advisory)."""
        if (ctx["spec"] or {}).get("for") == "quotes":
            return estimate_agent([600, 3000], [150, 600])
        return estimate_free()

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        from app.pipeline.orchestrator import QualityBounce  # deferred: import cycle

        spec = node.spec or {}
        if spec.get("answer") is not None:
            # Escalation resume (双败升级): apply the picked degrade path.
            await self._apply_escalation_answer(db, run, node, project)
            return []

        executor = await self._executor(db, node)
        outputs = await self._executor_outputs(db, executor)
        zh = await self._zh(db, run, project)
        if not outputs:
            await _set_summary(node.id, "没有产物可检" if zh else "No outputs to check")
            return []

        for_type = str(spec.get("for") or "")
        verdicts = await self._check(db, run, project, executor, outputs, for_type)

        # 字段白名单最小 diff 监视 (upgrade 3): this round vs the last
        # snapshot — unflagged outputs must stand byte-identical, and the
        # set's shape must not change.
        rounds: list[dict] = list(spec.get("rounds") or [])
        if rounds:
            self._repair_scope_surveillance(outputs, rounds[-1], verdicts)

        per_output_failed = [failed_checks(v) for v in verdicts]
        total_failed = sum(len(f) for f in per_output_failed)

        if total_failed == 0:
            # 首轮通过即跳轮 (upgrade 4): a clean round writes passed and ends.
            self._write_verdicts(outputs, verdicts, node, status="passed")
            await db.flush()
            n = sum(1 for v in verdicts for c in v if c.ok is True)
            await _set_summary(
                node.id, f"质检通过 · {n} 项检查" if zh else f"Passed · {n} checks"
            )
            logger.info("verify_passed", node_id=str(node.id), checks=n)
            return []

        # best-not-last (upgrade 2): a regressed round restores the best
        # earlier candidate instead of keeping the worse last one.
        best_prev = min(rounds, key=lambda r: r["fails"]) if rounds else None
        if best_prev is not None and best_prev["fails"] < total_failed:
            logger.info(
                "verify_best_not_last_restore",
                node_id=str(node.id),
                round_fails=total_failed,
                restored_fails=best_prev["fails"],
            )
            outputs = await self._restore_snapshot(db, run, executor, best_prev)
            verdicts = [[CheckResult(**c) for c in v] for v in best_prev["verdicts"]]
            per_output_failed = [failed_checks(v) for v in verdicts]
            await self._terminal(
                db, run, node, project, executor, outputs, verdicts,
                per_output_failed, zh, restored=True,
            )
            return []

        if (node.attempt or 1) <= _MAX_BOUNCES:
            # Bounce: snapshot this round (outputs + verdicts — the 机制信号
            # ledger survives the executor's delete-and-rewrite), then hand
            # the structured feedback to the executor's next run. The commit
            # precedes the raise (the exception unwinds this session — an
            # uncommitted flush would roll back).
            rounds.append(self._snapshot(outputs, verdicts))
            node.spec = {**spec, "rounds": rounds}
            await db.commit()
            feedback = self._feedback_text(per_output_failed, node.attempt or 1)
            logger.info(
                "verify_bounce",
                node_id=str(node.id),
                executor_id=str(executor.id),
                fails=total_failed,
                attempt=node.attempt,
            )
            raise QualityBounce(executor.id, feedback)

        await self._terminal(
            db, run, node, project, executor, outputs, verdicts,
            per_output_failed, zh, restored=False,
        )
        return []

    # ---- check assembly ------------------------------------------------------

    async def _executor(self, db: AsyncSession, node: WorkflowStep) -> WorkflowStep:
        """The upstream generation executor (compile wires it as inputs[0])."""
        for upstream_id in node.inputs or []:
            upstream = await db.get(WorkflowStep, UUID(str(upstream_id)))
            if upstream is not None and upstream.output_refs is not None:
                return upstream
        raise ValueError(f"Verify node {node.id} has no upstream executor")

    @staticmethod
    async def _executor_outputs(
        db: AsyncSession, executor: WorkflowStep
    ) -> list[Output]:
        rows: list[Output] = []
        for oid in executor.output_refs or []:
            row = await db.get(Output, UUID(str(oid)))
            if row is not None:
                rows.append(row)
        return rows

    @staticmethod
    async def _zh(db: AsyncSession, run: WorkflowRun, project: Project) -> bool:
        from app.pipeline.node_runners import _display_zh  # deferred: crew local

        return _display_zh(run, project, await _list_assets(db, project.id))

    async def _check(
        self,
        db: AsyncSession,
        run: WorkflowRun,
        project: Project,
        executor: WorkflowStep,
        outputs: list[Output],
        for_type: str,
    ) -> list[list[CheckResult]]:
        """Assemble the check context and run the deterministic matrix; the
        quotes judge appends its advisory verdicts on top."""
        ctx = run.context or {}
        ex_spec = executor.spec or {}
        slot = ex_spec.get("slot") or {}
        persona = await resolve_persona(db, project)
        check_ctx: dict[str, Any] = {
            "source_texts": await collect_asset_texts(db, project.id),
            "target_language": (
                slot.get("language")
                or ex_spec.get("target_language")
                or ctx.get("target_language", "en")
            ),
            "avoid": list(persona.avoid_words or []) if persona else [],
            "expected_count": slot.get("count"),
        }

        if for_type == "clips":
            items = await self._clip_items(db, project, executor, outputs)
        elif for_type == "quotes":
            items = [{"quotes": (o.payload or {}).get("quotes") or []} for o in outputs]
        elif for_type in ("post", "article"):
            items = [{"text": (o.payload or {}).get("content") or ""} for o in outputs]
        elif for_type == "carousel":
            items = [{"slides": (o.payload or {}).get("slides") or []} for o in outputs]
        else:
            items = []

        verdicts = run_checks(for_type, items, check_ctx)
        if for_type == "quotes":
            await self._judge_quotes(check_ctx["source_texts"], items, verdicts)
        return verdicts

    async def _clip_items(
        self,
        db: AsyncSession,
        project: Project,
        executor: WorkflowStep,
        outputs: list[Output],
    ) -> list[dict[str, Any]]:
        """Per-clip check items: span words / emphasis evidence / face anchors.

        The emphasis evidence channels stay side by side (语义 emphasis_words
        + 声学 prosody peaks — the 铁律 split), joined into one time list only
        as the alignment check's distance targets.
        """
        understanding = None
        try:
            plan_node = await _upstream_by_kind(db, executor, "plan")
            understanding = await _load_understanding(db, plan_node)
        except ValueError:
            logger.warning("verify_understanding_missing", executor_id=str(executor.id))

        assets = await _list_assets(db, project.id)
        by_id = {str(a.id): a for a in assets}
        anchors_by_url: dict[str, dict] = {}
        for a in assets:
            anchors = (a.meta or {}).get("visual_anchors")
            if a.type == AssetType.IMAGE and anchors and a.file_url:
                url = stream_url(a.file_url)
                if url:
                    anchors_by_url[url] = anchors

        items: list[dict[str, Any]] = []
        for output in outputs:
            spec = output.render_spec or {}
            span = _kept_span(spec)
            source_asset = by_id.get(str((spec.get("source") or {}).get("asset_id") or ""))
            words = ((source_asset.meta or {}).get("words") or []) if source_asset else []
            cues = spec.get("caption_track") or []
            if span is not None:
                lo, hi = span[0] - 0.75, span[1] + 0.75
                span_words = [
                    str(w.get("word") or "")
                    for w in words
                    if lo <= float(w.get("start", 0)) and float(w.get("end", 0)) <= hi
                ]
                hint_times = self._hint_times(understanding, source_asset, span)
            else:
                span_words, hint_times = [], []
            if not span_words and cues:
                # The caption track IS the span's word stream when captions
                # are enabled — the fidelity basis survives a missing asset.
                span_words = [str(c.get("text") or "") for c in cues]
            items.append(
                {
                    "spec": spec,
                    "source_text": str(
                        ((output.source_ref or {}).get("segment") or {}).get("source_text") or ""
                    ),
                    "span_words": span_words,
                    "hint_times": hint_times,
                    "anchors_by_url": anchors_by_url,
                }
            )
        return items

    @staticmethod
    def _hint_times(understanding, source_asset, span: tuple[float, float]) -> list[float]:
        """Semantic (understanding) + acoustic (prosody) emphasis times inside
        the clip span — the two channels gathered side by side, never merged
        into a score."""
        times: list[float] = []
        if understanding is not None:
            for e in understanding.emphasis_words:
                if e.start is not None and span[0] <= e.start <= span[1]:
                    times.append(float(e.start))
        prosody = ((source_asset.meta or {}).get("prosody") or {}) if source_asset else {}
        for p in prosody.get("emphasis_peaks") or []:
            t = p.get("t")
            if t is not None and span[0] <= float(t) <= span[1]:
                times.append(float(t))
        return times

    async def _judge_quotes(
        self,
        source_texts: list[str],
        items: list[dict[str, Any]],
        verdicts: list[list[CheckResult]],
    ) -> None:
        """The §2.7 judge, advisory: verdicts record as cls="judge" (ledger +
        tooltip evidence) and never gate until the calibration set lands. A
        judge failure degrades to silence — never fails the verify node."""
        judge_items = [
            {
                "quote": q.get("quote") or "",
                "attribution": q.get("attribution") or "",
                "context": _quote_context(q.get("quote") or "", source_texts),
            }
            for item in items
            for q in (item.get("quotes") or [])
        ]
        if not judge_items:
            return
        try:
            verdict = await verify_judge.call(items=judge_items)
        except Exception as e:  # noqa: BLE001 — the advisory path never gates
            logger.warning("verify_judge_failed", error=str(e))
            return
        by_quote = {j.quote: j for j in verdict.judgments}
        for item, checks in zip(items, verdicts, strict=False):
            for q in item.get("quotes") or []:
                j = by_quote.get(q.get("quote") or "")
                if j is None or j.standalone:
                    continue
                checks.append(
                    CheckResult(
                        "judge_quote_readability",
                        False,
                        f"'{(q.get('quote') or '')[:24]}…': {j.issue or 'not standalone'}",
                        cls="judge",
                    )
                )

    # ---- best-not-last + whitelist surveillance -------------------------------

    @staticmethod
    def _snapshot(outputs: list[Output], verdicts: list[list[CheckResult]]) -> dict:
        """One round's full snapshot (spec.rounds entry): the outputs' content
        columns + their verdicts + the fail profile — the ledger survives the
        executor's delete-and-rewrite."""
        return {
            "fails": sum(len(failed_checks(v)) for v in verdicts),
            "outputs": [
                {
                    "type": o.type,
                    "language": o.language,
                    "provenance": o.provenance,
                    "payload": o.payload,
                    "files": o.files or {},
                    "source_ref": o.source_ref,
                    "render_spec": o.render_spec,
                    "score": o.score,
                    "publishing": o.publishing or {},
                }
                for o in outputs
            ],
            "verdicts": [
                [
                    {"id": c.id, "ok": c.ok, "detail": c.detail, "cls": c.cls}
                    for c in v
                ]
                for v in verdicts
            ],
        }

    @staticmethod
    def _repair_scope_surveillance(
        outputs: list[Output],
        last: dict,
        verdicts: list[list[CheckResult]],
    ) -> None:
        """Whitelist min-diff surveillance (upgrade 3): against the previous
        round's snapshot, unflagged outputs must be unchanged and the set's
        shape must hold. Drift appends a bounce-worthy ``repair_scope``
        failure to that output's checks."""
        prev_outputs = last.get("outputs") or []
        prev_verdicts = last.get("verdicts") or []
        flagged = {
            i
            for i, v in enumerate(prev_verdicts)
            if any(c.get("ok") is False and c.get("cls") != "judge" for c in v)
        }
        if len(outputs) != len(prev_outputs):
            if verdicts:
                verdicts[0].append(
                    CheckResult(
                        "repair_scope",
                        False,
                        f"output count changed {len(prev_outputs)} → {len(outputs)} — "
                        "a repair round must not re-plan the set",
                    )
                )
            return
        for i, output in enumerate(outputs):
            prev = prev_outputs[i]
            if i in flagged:
                # Flagged output: only identity fields are frozen — the
                # flagged content is exactly what may change.
                drift = (
                    output.type != prev.get("type")
                    or output.language != prev.get("language")
                )
            else:
                drift = (
                    output.payload != prev.get("payload")
                    or output.source_ref != prev.get("source_ref")
                    or output.type != prev.get("type")
                    or output.language != prev.get("language")
                )
            if drift:
                verdicts[i].append(
                    CheckResult(
                        "repair_scope",
                        False,
                        f"output #{i + 1} was rewritten though only "
                        f"{sorted(j + 1 for j in flagged) or 'none'} were flagged — "
                        "keep repairs inside the whitelist",
                    )
                )

    async def _restore_snapshot(
        self,
        db: AsyncSession,
        run: WorkflowRun,
        executor: WorkflowStep,
        snap: dict,
    ) -> list[Output]:
        """best-not-last restore: replace the regressed round's outputs with
        the best earlier round's snapshot (fresh ids; the snapshot's rendered
        files ride along; pending render nodes of the doomed round are
        skipped — select_clips' own cancel dance).

        Targeted regens (executor ``spec.target_id``) restore IN PLACE: the
        user addressed that row — its identity and operations chain survive,
        only the content columns roll back."""
        rows = snap.get("outputs") or []
        target_id = (executor.spec or {}).get("target_id")
        if target_id and rows:
            output = await db.get(Output, UUID(str(target_id)))
            if output is not None and rows:
                row = rows[0]
                output.payload = row.get("payload") or {}
                output.files = dict(row.get("files") or {})
                output.source_ref = row.get("source_ref")
                output.render_spec = row.get("render_spec")
                output.score = row.get("score")
                output.publishing = row.get("publishing") or {}
                output.updated_at = datetime.now(UTC)
            await db.flush()
            return [output] if output is not None else []

        doomed = [UUID(str(oid)) for oid in (executor.output_refs or [])]
        if doomed:
            await db.execute(
                _text(
                    "UPDATE workflow_steps SET status = 'skipped', updated_at = now() "
                    "WHERE run_id = :rid AND kind = 'render' AND status = 'pending' "
                    "AND spec->>'output_id' IN :oids"
                ).bindparams(bindparam("oids", expanding=True)),
                {"rid": str(run.id), "oids": [str(oid) for oid in doomed]},
            )
            await db.execute(delete(Output).where(Output.id.in_(doomed)))
        restored: list[Output] = []
        for row in snap.get("outputs") or []:
            files = dict(row.get("files") or {})
            render_spec = row.get("render_spec")
            if files.get("video"):
                render_status = RenderStatus.COMPLETED  # the rendered file rides along
            elif render_spec:
                render_status = RenderStatus.PENDING
            else:
                render_status = None
            output = Output(
                project_id=run.project_id,
                workflow_step_id=executor.id,
                type=row.get("type") or "clip",
                language=row.get("language") or "en",
                provenance=row.get("provenance") or "generated",
                payload=row.get("payload") or {},
                files=files,
                source_ref=row.get("source_ref"),
                render_spec=render_spec,
                render_status=render_status,
                score=row.get("score"),
                publishing=row.get("publishing") or {},
            )
            db.add(output)
            restored.append(output)
        await db.flush()
        executor.output_refs = [str(o.id) for o in restored]
        await db.flush()
        return restored

    # ---- terminal paths -------------------------------------------------------

    @staticmethod
    def _write_verdicts(
        outputs: list[Output],
        verdicts: list[list[CheckResult]],
        node: WorkflowStep,
        *,
        status: str,
    ) -> None:
        """The terminal verdict lands on the product rows (Output.quality)."""
        now = datetime.now(UTC).isoformat()
        for output, checks in zip(outputs, verdicts, strict=False):
            output.quality = {
                "status": status,
                "checks": [
                    {"id": c.id, "ok": c.ok, "detail": c.detail, "cls": c.cls}
                    for c in checks
                ],
                "attempt": node.attempt or 1,
                "checked_at": now,
            }

    @staticmethod
    def _feedback_text(
        per_output_failed: list[list[CheckResult]],
        attempt: int,
    ) -> str:
        """The bounce payload (rides the executor's spec.feedback → the agent
        funnel's repair echo): failed checks per flagged output + the
        whitelist discipline line."""
        lines = [f"Quality gate round {attempt}: the following checks failed."]
        for i, fails in enumerate(per_output_failed):
            if not fails:
                continue
            lines.append(f"Output #{i + 1}:")
            for c in fails:
                lines.append(f"- {c.id}: {c.detail}")
        flagged = [i + 1 for i, f in enumerate(per_output_failed) if f]
        lines.append(
            f"Repair scope: ONLY outputs {', '.join(f'#{i}' for i in flagged)} "
            "are flagged, and only their flagged content may change — keep "
            "every other output and every other field identical to your "
            "previous proposal. Do not rewrite the whole set."
        )
        return "\n".join(lines)

    async def _terminal(
        self,
        db: AsyncSession,
        run: WorkflowRun,
        node: WorkflowStep,
        project: Project,
        executor: WorkflowStep,
        outputs: list[Output],
        verdicts: list[list[CheckResult]],
        per_output_failed: list[list[CheckResult]],
        zh: bool,
        *,
        restored: bool,
    ) -> None:
        """The exhausted path (升级 5): the verdict is needs_human either way
        (non-blocking); CRAFT-class failures on clips additionally dock the
        escalation question and park via Suspend. Commits before any raise —
        the Suspend unwind would roll a flush back."""
        self._write_verdicts(outputs, verdicts, node, status="needs_human")
        failing_ids = sorted({c.id for f in per_output_failed for c in f})
        craft_failed = any(c.cls == "craft" for f in per_output_failed for c in f)
        suffix = (
            "（已回退到最优轮）" if restored and zh
            else " (restored the best round)" if restored
            else ""
        )
        await _set_summary(
            node.id,
            f"需人工复核 · {len(failing_ids)} 项未过{suffix}"
            if zh
            else f"Needs human · {len(failing_ids)} failing{suffix}",
        )
        await db.commit()
        logger.info(
            "verify_needs_human",
            node_id=str(node.id),
            failing=failing_ids,
            craft=craft_failed,
            restored=restored,
        )
        if craft_failed and (node.spec or {}).get("for") == "clips":
            await self._escalate(db, run, node, project, per_output_failed, zh)

    async def _escalate(
        self,
        db: AsyncSession,
        run: WorkflowRun,
        node: WorkflowStep,
        project: Project,
        per_output_failed: list[list[CheckResult]],
        zh: bool,
    ) -> None:
        """Craft double-fail → the docked escalation question (interrupt 机制
        复用): 降级接受 (default — the TTL sweep auto-picks it) / 标题卡开场.
        Never a fabricated hook (顾问姿态: 带理由纠偏)."""
        from app.chat.service import (  # deferred: import cycle
            dock_interrupt_question,
            finalize_bailed_runs,
        )
        from app.models.database import AsyncSessionLocal
        from app.pipeline.orchestrator import Suspend  # deferred: import cycle

        details = [
            c.detail for f in per_output_failed for c in f if c.cls == "craft"
        ][:2]
        question_text = (
            (
                "这条短片的节奏检查两轮都没过"
                + (f"（{'; '.join(details)}）" if details else "")
                + "。产物已照常落地，你可以降级接受，或让它用标题卡开场（更稳的收法）。"
            )
            if zh
            else (
                "The clip's pacing checks failed twice"
                + (f" ({'; '.join(details)})" if details else "")
                + ". The output landed anyway — accept it as-is, or have it "
                "open with a title card (the safer cut)."
            )
        )
        accept_label = "降级接受" if zh else "Accept as-is"
        title_label = "标题卡开场" if zh else "Open with a title card"
        payload = AskPayload(
            kind="choice",
            options=[AskOption(id="a", label=accept_label), AskOption(id="b", label=title_label)],
            allow_freeform=False,
        )
        async with AsyncSessionLocal() as s:
            message, bailed_run_ids = await dock_interrupt_question(
                s,
                UUID(str(project.user_id)),
                UUID(str(project.id)),
                UUID(str(run.id)),
                question_text,
                payload,
            )
            question_message_id = str(message.id)
            await s.commit()
        # Docking superseded an older parked question (single-pending
        # invariant) — its run was cascade-bailed in the same stroke; settle it.
        await finalize_bailed_runs(bailed_run_ids)
        raise Suspend(
            {
                "question_message_id": question_message_id,
                "options": [
                    # argument_id=None marks the default (the TTL sweep's
                    # auto-answer) — 降级接受 keeps 离开不中断.
                    {"id": "a", "label": accept_label, "argument_id": None},
                    {"id": "b", "label": title_label, "argument_id": "title_card"},
                ],
            }
        )

    async def _apply_escalation_answer(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> None:
        """The escalation's answer branch: 降级接受 (default/expired) only
        records; 标题卡开场 journals a real ``set_title`` op per clip
        (operations ledger, ADR-032) and re-pends the render."""
        spec = node.spec or {}
        answer = spec.get("answer") or {}
        options = (spec.get("suspend_payload") or {}).get("options") or []
        chosen = answer.get("option_id")
        action = next(
            (o.get("argument_id") for o in options if o.get("id") == chosen), None
        )
        zh = await self._zh(db, run, project)
        if action != "title_card":
            await _set_summary(
                node.id, "质检：已降级接受" if zh else "Quality: accepted as-is"
            )
            return

        from app.operations.service import apply_operations  # deferred: heavy

        executor = await self._executor(db, node)
        outputs = await self._executor_outputs(db, executor)
        applied = 0
        for output in outputs:
            if not output.render_spec:
                continue
            payload = output.payload or {}
            title = (
                payload.get("hook")
                or (payload.get("title_options") or [""])[0]
                or ""
            ).strip()
            if not title:
                continue
            await apply_operations(
                db,
                output.id,
                [{"op": "set_title", "params": {"text": title, "enabled": True}}],
                source="system",
                commit=False,
            )
            output.render_status = RenderStatus.PENDING
            output.render_error = None
            applied += 1
        await db.flush()
        await _set_summary(
            node.id,
            f"质检：已改标题卡开场 · {applied} 条"
            if zh
            else f"Quality: title-card openers on {applied} clip(s)",
        )
        logger.info(
            "verify_escalation_title_card", node_id=str(node.id), applied=applied
        )
