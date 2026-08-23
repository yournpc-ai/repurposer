"""Hook gate + render release — the 钩子预览闸 (产物质量线期 4, §2.5).

Craft's hook rules (延迟/节奏/强调/收束) are statically unverifiable — a text
storyboard is blind to pacing — and the hook is the highest-stakes segment.
So the review tier spends its ONE paid pre-render on it: before any full
render fans out, the run parks on a docked question carrying each clip's
≤5s low-res hook preview (the render service's black-box ``preview``
parameter — ADR-016 intact). Three answer paths (确认/调整/降级):

- 确认 (default — the TTL sweep auto-picks it, 离开不中断): release.
- 调整: not an option but an inline control on the dock — swap_hook_shot /
  set_trim ride the user-callable ops endpoint against the parked specs;
  the release then renders the ADJUSTED spec (the preview honestly stays
  the original cut).
- 降级: 标题卡开场 — the safer opener, journaled as real ``set_title`` ops
  (same mechanism as the 期 3 verify escalation).

Topology (compile-injected, review tier + a single plain select_clips chain
only — a modifier would rewrite specs AFTER the previews, showing pre-morph
footage): ``select_clips → verify → hook_gate → release_renders``.
select_clips suppresses its render fan-out when a gate sibling exists
(render_status stays NULL); release_renders pends + fans out after the
gate's confirm. Bailing the gate cascade-skips the release — the honest
"don't render these" exit, clips stay spec-only.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AskOption, AskPayload, HookPreview, HookTrim, WorkflowStatus
from app.models.tables import Output, Project, WorkflowRun, WorkflowStep
from app.pipeline.graph import NodeBase, estimate_free
from app.pipeline.morph import _pend_suppressed_base_renders
from app.pipeline.quality import _kept_span
from app.pipeline.step_context import _list_assets
from app.pipeline.step_display import _set_summary
from app.providers.storage import resolve_stored_url

logger = structlog.get_logger()

# 钩子预览时长 (§2.5 "前 3–5 秒"): the render service caps previews at 15s;
# the gate asks for 5.
_PREVIEW_SECONDS = 5.0


async def _clips_executor(db: AsyncSession, node: WorkflowStep) -> WorkflowStep:
    """The select_clips producer upstream of the gate chain. Compile wires it
    explicitly (gate inputs = [verify, executor]; release inputs = [gate]),
    so a bounded input walk finds it by kind."""
    seen: set[str] = set()
    frontier = [str(i) for i in (node.inputs or [])]
    while frontier:
        cur = frontier.pop()
        if cur in seen:
            continue
        seen.add(cur)
        upstream = await db.get(WorkflowStep, UUID(cur))
        if upstream is None:
            continue
        if upstream.kind == "select_clips":
            return upstream
        frontier.extend(str(i) for i in (upstream.inputs or []))
    raise ValueError(f"{node.kind} node {node.id} has no upstream select_clips")


async def _executor_outputs(db: AsyncSession, executor: WorkflowStep) -> list[Output]:
    """The executor's clip rows carrying a render spec (order preserved)."""
    rows: list[Output] = []
    for oid in executor.output_refs or []:
        row = await db.get(Output, UUID(str(oid)))
        if row is not None and row.render_spec:
            rows.append(row)
    return rows


async def _display_zh(db: AsyncSession, run: WorkflowRun, project: Project) -> bool:
    from app.pipeline.node_runners import _display_zh as _dz  # deferred: crew local

    return _dz(run, project, await _list_assets(db, project.id))


class HookGate(NodeBase):
    kind = "hook_gate"
    task_name = "Preview hooks"
    task_name_zh = "钩子预览"

    def estimate(self, ctx: dict) -> dict | None:
        """Unquotable at compile time (P4 NULL): the preview count is the
        mid-run clip count, and the preview render units ride the render
        chain's born-mid-run precedent."""
        return None

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        from app.pipeline.orchestrator import Suspend  # deferred: import cycle

        spec = node.spec or {}
        if spec.get("answer") is not None:
            await self._apply_answer(db, run, node, project)
            return []

        executor = await _clips_executor(db, node)
        outputs = await _executor_outputs(db, executor)
        zh = await _display_zh(db, run, project)
        if not outputs:
            await _set_summary(node.id, "没有短片可预览" if zh else "No clips to preview")
            return []

        # The ONE paid pre-render (§2.5): a ≤5s low-res hook per clip,
        # best-effort per clip — a failure never fails the gate.
        from app.pipeline.rendering import render_hook_preview  # deferred: heavy

        previews: list[HookPreview] = []
        for output in outputs:
            # 期 4 bug #3: delete the previous hook_preview object (if any)
            # before re-rendering — a retry or re-render would otherwise leave
            # the old object as storage garbage (the new key overwrites the
            # row's files dict but not the bucket).
            prev_key = (output.files or {}).get("hook_preview")
            key = await render_hook_preview(
                project_id=project.id,
                user_id=project.user_id,
                output_id=output.id,
                render_spec=output.render_spec,
                seconds=_PREVIEW_SECONDS,
                previous_key=prev_key,
            )
            if key is None:
                continue
            output.files = {**(output.files or {}), "hook_preview": key}
            source = output.render_spec.get("source") or {}
            shots = [
                resolved
                for s in source.get("image_shots") or []
                if (resolved := resolve_stored_url(s.get("image_url")))
            ][:6]
            span = _kept_span(output.render_spec)
            src_dur = ((output.render_spec or {}).get("source") or {}).get("duration")
            source_duration = float(src_dur) if isinstance(src_dur, (int, float)) else None
            previews.append(
                HookPreview(
                    output_id=output.id,
                    url=resolve_stored_url(key) or "",
                    hook=(output.payload or {}).get("hook") or None,
                    shots=shots,
                    trim=HookTrim(start=span[0], end=span[1]) if span else None,
                    source_duration=source_duration,
                )
            )
        # Single transaction for the entire park (期 4 bug #4): preview keys,
        # the docked question message, the node → waiting, and the run →
        # WAITING_HUMAN all land in one commit. The previous 3-transaction
        # split (preview commit / dock-commit / node-waiting commit) had a
        # race window where a crash between any two left the run stuck
        # RUNNING with previews already saved — node.status was still
        # "running" and the worker would never reclaim it. Committing here
        # makes the park atomic; the orchestrator's Suspend catch branch
        # remains a no-op fallback (it reads committed state).
        await db.commit()

        if not previews:
            # Honest degrade: nothing to show, so nothing to park on — the
            # release downstream fans the renders out as if no gate existed.
            await _set_summary(
                node.id,
                "预览生成失败 · 直接放行渲染" if zh else "Preview failed · releasing anyway",
            )
            logger.warning("hook_gate_degraded", node_id=str(node.id), clips=len(outputs))
            return []

        missed = len(outputs) - len(previews)
        # Non-previewed siblings (期 4 v0 边界): translate_clip / dub_clip fork
        # off the select_clips outputs and render their own derived rows
        # independently — the gate's preview only covers the EN base. Name
        # them so the user isn't surprised by auto-renders landing while the
        # dock sits waiting for their call.
        pending_subs: list[str] = [
            str(lang) for lang in (spec.get("pending_subs") or []) if isinstance(lang, str) and lang
        ]
        pending_dubs: list[str] = [
            str(lang) for lang in (spec.get("pending_dubs") or []) if isinstance(lang, str) and lang
        ]
        also_parts: list[str] = []
        if pending_subs:
            also_parts.append(
                f"{len(pending_subs)} 个字幕版" if zh
                else f"{len(pending_subs)} translated version(s)"
            )
        if pending_dubs:
            also_parts.append(
                f"{len(pending_dubs)} 个配音版" if zh
                else f"{len(pending_dubs)} dubbed version(s)"
            )
        also_suffix = ""
        if also_parts:
            also_suffix = (
                "另外，" + "、".join(also_parts) + " 不经预览直接渲染。"
                if zh
                else " Also rendering without preview: " + " + ".join(also_parts) + "."
            )
        question_text = (
            f"钩子预览好了——{len(previews)} 条短片各取前 5 秒的低清版。"
            "看着没问题就放行渲染；想要更稳的开场，可以让它加标题卡。"
            + (f"（{missed} 条预览没生成出来，放行后照常渲染。）" if missed else "")
            + also_suffix
            if zh
            else
            f"Hook previews are in — the first 5 seconds of {len(previews)} "
            "clip(s), low-res. Release the renders if they look right, or have "
            "them open with a title card for a safer start."
            + (f" ({missed} preview(s) didn't render — they release normally.)" if missed else "")
            + also_suffix
        )
        confirm_label = "放行渲染" if zh else "Release renders"
        title_label = "标题卡开场" if zh else "Open with a title card"
        payload = AskPayload(
            kind="choice",
            options=[AskOption(id="a", label=confirm_label), AskOption(id="b", label=title_label)],
            allow_freeform=False,
            previews=previews,
        )

        from app.chat.service import (  # deferred: import cycle
            dock_interrupt_question,
            finalize_bailed_runs,
        )

        # Dock the question on the SAME session so preview keys + the
        # message + node → waiting + run → WAITING_HUMAN all commit in one
        # transaction (see the comment above the preview-key commit). The
        # message row's workflow_run_id is the dispatch marker — the answer
        # endpoint recognizes a hook-gate question by it and resumes the
        # parked run (answer = resume).
        message, bailed_run_ids = await dock_interrupt_question(
            db,
            UUID(str(project.user_id)),
            UUID(str(project.id)),
            UUID(str(run.id)),
            question_text,
            payload,
        )
        question_message_id = str(message.id)
        # Park the node and the run in the SAME session (the suspend_payload
        # rides the node's spec — execute_step's Suspend catch branch will
        # re-read it and write it again, idempotently).
        node.status = "waiting"
        node.spec = {
            **(node.spec or {}),
            "suspend_payload": {
                "question_message_id": question_message_id,
                "options": [
                    # argument_id=None marks the default (the TTL sweep's
                    # auto-answer) — 确认放行 keeps 离开不中断.
                    {"id": "a", "label": confirm_label, "argument_id": None},
                    {"id": "b", "label": title_label, "argument_id": "title_card"},
                ],
            },
        }
        if run.status != WorkflowStatus.WAITING_HUMAN:
            run.status = WorkflowStatus.WAITING_HUMAN
        await db.commit()
        # Docking superseded an older parked question (single-pending
        # invariant) — its run was cascade-bailed in the same stroke; settle
        # it AFTER the commit so finalize reads the new state.
        await finalize_bailed_runs(bailed_run_ids)
        raise Suspend(
            {
                "question_message_id": question_message_id,
                "options": [
                    {"id": "a", "label": confirm_label, "argument_id": None},
                    {"id": "b", "label": title_label, "argument_id": "title_card"},
                ],
            }
        )

    async def _apply_answer(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> None:
        """The answer branch: 确认 (default/expired) only records; 标题卡开场
        journals a real ``set_title`` op per clip (operations ledger, ADR-032).
        Neither pends the render — release_renders downstream owns that."""
        spec = node.spec or {}
        answer = spec.get("answer") or {}
        options = (spec.get("suspend_payload") or {}).get("options") or []
        chosen = answer.get("option_id")
        action = next(
            (o.get("argument_id") for o in options if o.get("id") == chosen), None
        )
        zh = await _display_zh(db, run, project)
        if action != "title_card":
            await _set_summary(
                node.id, "钩子已确认 · 放行渲染" if zh else "Hooks confirmed · releasing"
            )
            return

        from app.operations.service import apply_operations  # deferred: heavy

        executor = await _clips_executor(db, node)
        outputs = await _executor_outputs(db, executor)
        applied = 0
        for output in outputs:
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
            applied += 1
        await db.flush()
        await _set_summary(
            node.id,
            f"已改标题卡开场 · {applied} 条" if zh else f"Title-card openers on {applied} clip(s)",
        )
        logger.info("hook_gate_title_card", node_id=str(node.id), applied=applied)


class ReleaseRenders(NodeBase):
    """放行渲染: the gate's downstream — pend the suppressed clip renders and
    fan out one render node per clip (the select_clips fan-out's shape,
    deferred until the human's pick)."""

    kind = "release_renders"
    task_name = "Release renders"
    task_name_zh = "放行渲染"

    def estimate(self, ctx: dict) -> dict | None:
        return estimate_free()  # pure bookkeeping: pend + step inserts

    async def run(
        self, db: AsyncSession, run: WorkflowRun, node: WorkflowStep, project: Project
    ) -> list[UUID]:
        executor = await _clips_executor(db, node)
        outputs = await _executor_outputs(db, executor)
        stale = [o for o in outputs if o.render_status is None]
        if stale:
            # The gate chain compiles only when no modifiers exist, so no
            # later morph can own these renders — defer is False by topology.
            await _pend_suppressed_base_renders(
                db, run, node, outputs, defer_to_later_morph=False
            )
        zh = await _display_zh(db, run, project)
        await _set_summary(
            node.id,
            f"渲染已放行 · {len(stale)} 条" if zh else f"Released {len(stale)} render(s)",
        )
        logger.info("renders_released", node_id=str(node.id), count=len(stale))
        return []
