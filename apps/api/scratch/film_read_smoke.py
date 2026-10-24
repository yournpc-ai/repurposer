"""R3 真实读图旅程 smoke — film 作品读取的端到端核验（隔离 fixture，绝不碰事故项目）。

三段分离（付费面只在 --run）：

  --seed     FREE. Seeds an isolated fixture: fresh user + project R (3 cloned
             web_page captures = 12 views, AT budget) + project B (+1 capture =
             14 views, OVER budget), each with a film Output whose provenance
             (run context board/params/digest/execution + render_spec frames)
             is a verbatim copy of a REAL executed film (source ids below).
             Cloned assets carry file_url=None and REUSE the source captures'
             storage keys READ-ONLY — project deletion unlinks only file_url
             (None → no-op) and the fixture's OWN prefixes (which hold
             nothing), so the source project's objects are never touched.
  --verify   FREE (no LLM, no API process needed). Runs the REAL
             output_spec_observation in-process against the seeded fixture
             with the gate flipped on in-memory: asserts the fact sheet, the
             image attachments (count/px/captions), the budget error shape on
             project B, and the scoped single-view high-res re-read.
  --run      PAID. Live chat turns against a GATE-ON API instance
             (scratch/run_api_gateon.py — a SECOND process on 127.0.0.1:8001
             with its own MiniMax request fence; the user's :8000 API and
             worker stay untouched). Legs L1-L6 + L7 law after every turn
             (auxiliary tripwires: no new runs/outputs/ledger rows;
             authorization law: reads leave the pending film state
             byte-unchanged, the seeded standing review hold is never
             released — including by a landed patch).
  --cleanup  Deletes the fixture projects via the API (harness seat).
  --selftest FREE. Proves the per-leg assertion kernel against stub
             StreamTurns (no model, no API).

PRODUCTION BLOCKING — TWO independent layers:

  1. TEST-INSTANCE BLOCKER (deterministic, state-independent): the gate-on
     launcher (scratch/run_api_gateon.py) replaces the sole WorkflowRun
     birthplace ``orchestrator.create_run`` with an in-process refusal that
     fires BEFORE any DB write or enqueue. It consults no hold, no wallet,
     no confirmation mode, no model output — through the 8001 instance no
     run can be born even if every product gate were open (its --selftest
     proves the refusal and its binding).
  2. PRODUCT LAW UNDER TEST: each fixture project's pending film state
     carries a STANDING review hold — evaluate_start_gate answers 422
     start.review_hold BEFORE create_run (pipeline/lifecycle.py) and
     create_run is flush-only, so no start gesture (chat start_run / dock
     pill / auto mode) can birth a run while the hold stands. The L7
     assertions verify THIS law on its own evidence (the hold never
     released, reads never mutating state) — the blocker must never mask
     an L7 failure, and cannot: L7 reads the database directly.

Zero wallet, ask/ask settings and the journey never sending an approval
word are AUXILIARY layers on top.

Usage (from apps/api):
  uv run python scratch/film_read_smoke.py --seed
  uv run python scratch/film_read_smoke.py --verify
  uv run python scratch/film_read_smoke.py --run --base http://127.0.0.1:8001/api/v1
  uv run python scratch/film_read_smoke.py --cleanup
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import chat_scenarios as cs  # noqa: E402  (the scenario harness: Ctx/check/etc.)
from sqlalchemy import delete, func, select  # noqa: E402

from app.models.database import AsyncSessionLocal  # noqa: E402
from app.models.tables import (  # noqa: E402
    Asset,
    AssetStatus,
    AssetType,
    CreditTransaction,
    Output,
    Project,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStep,
)

# ---- fixture sources (REAL executed film + captures, read-only) ------------
SRC_PROJECT = "14fa16b6-2875-422c-98f8-c7089599a8c5"
SRC_OUTPUT = "7bddff32-d17a-4b14-b755-7d89a5fc1e33"
# capture order = page order (created_at ASC): page0 snappify.com (6 shots),
# page1 /pricing (4), page2 /features/video-export (2)
SRC_ASSETS = [
    "b64301f2-b85b-4a1b-abc4-c6cf382c976a",
    "ed3eb886-2e6d-46a9-9169-5daa38e9ad93",
    "66fd14bf-2010-4236-8e95-26a78a74a115",
]
SRC_ASSET_EXTRA = "b4a22014-e718-41d0-95ee-7a72068c3745"  # 2 shots → project B = 14 views

STATE_FILE = Path("/tmp/film_read_smoke_fixture.json")

# Ground truth (established by eyeballing the real screenshots 2026-10-21):
# - fold (page0 shot0): big heading "We enable developers to create stunning
#   presentations", blue "Get started - It's free", "40k+ developers" line.
# - page0 shot1 ("Create next-level presentations"): LEFT = green panel with a
#   code-editor video (smoosh.py, play button); the card under "Learn more"
#   says "💡 Share interactive slides …"; element s1e15 = that card,
#   s1e14 = the "Learn more" button (scene s5's current focus).
# - film scene 1 (words) overlay lines appear in NO screenshot:
#   "Slide deck blues?" / "Same old slides." / "Almost there."
# - scene index 13 (s14, ui page0 shot5): authored 8.0s, executed 246f = 8.2s.

L7_NOTE = "no new runs / outputs / ledger rows; the seeded standing hold never released"


async def _seed_project(ctx: "cs.Ctx", title: str, asset_ids: list[str]) -> tuple[str, str]:
    """Clone the captures + film provenance into a fresh project. Returns
    (project_id, output_id)."""
    pid = await ctx.new_project(title)
    async with AsyncSessionLocal() as db:
        src_out = await db.get(Output, uuid.UUID(SRC_OUTPUT))
        assert src_out is not None, "source film output missing — fixture source drifted"
        src_step = await db.get(WorkflowStep, src_out.workflow_step_id)
        src_run = await db.get(WorkflowRun, src_step.run_id)
        ctx_copy = json.loads(json.dumps(src_run.context))
        spec_copy = json.loads(json.dumps(src_out.render_spec))
        payload_copy = json.loads(json.dumps(src_out.payload or {}))
        prov_copy = json.loads(json.dumps(src_out.provenance or {})) if src_out.provenance else None

        for aid in asset_ids:
            src_asset = await db.get(Asset, uuid.UUID(aid))
            assert src_asset is not None, f"source asset {aid} missing"
            db.add(
                Asset(
                    user_id=ctx.user_id,
                    project_id=uuid.UUID(pid),
                    type=AssetType.WEB_PAGE,
                    file_url=None,  # deletion no-op; meta keys reused READ-ONLY
                    title=src_asset.title,
                    extracted_text=src_asset.extracted_text,
                    meta=json.loads(json.dumps(src_asset.meta or {})),
                    processing_status=AssetStatus.COMPLETED,
                )
            )
            await db.flush()  # created_at ordering = capture order

        run = WorkflowRun(
            project_id=uuid.UUID(pid),
            status=WorkflowStatus.COMPLETED,
            progress=src_run.progress,
            context=ctx_copy,
        )
        db.add(run)
        await db.flush()
        step = WorkflowStep(
            run_id=run.id,
            kind=src_step.kind,
            status=src_step.status,
            seq=src_step.seq,
            spec=json.loads(json.dumps(src_step.spec or {})),
            inputs=json.loads(json.dumps(src_step.inputs or {})),
        )
        db.add(step)
        await db.flush()
        out = Output(
            project_id=uuid.UUID(pid),
            workflow_step_id=step.id,
            type="film",
            language=src_out.language,
            status=src_out.status,
            payload=payload_copy,
            render_spec=spec_copy,
            provenance=prov_copy,
        )
        db.add(out)
        await db.flush()

        # The PRODUCT-LAW layer (layer 2 of the smoke's production
        # blocking — see the module docstring): a standing review hold on
        # the pending film state. evaluate_start_gate answers 422
        # start.review_hold BEFORE create_run (pipeline/lifecycle.py) — and
        # create_run is flush-only — so NO start gesture (chat start_run,
        # dock pill, auto mode) can birth a run for this project while the
        # hold stands. (The state-independent test-instance blocker on the
        # 8001 launcher is layer 1; this hold is ALSO the authorization law
        # the smoke verifies — L7 asserts it is never released.) The film_*
        # keys mirror the run context's version exactly (same board bytes +
        # params → the pinned read's base_ref and the patch's
        # pending-resolved base agree by construction).
        project = await db.get(Project, uuid.UUID(pid))
        project.pending_brief = {
            # pending carries the board under its film_storyboard key (the
            # run context's twin is named prepared_storyboard)
            "film_storyboard": ctx_copy.get("prepared_storyboard"),
            **{
                k: ctx_copy[k]
                for k in (
                    "film_storyboard_fingerprint",
                    "film_storyboard_version",
                    "film_storyboard_params",
                    "film_storyboard_content_digest",
                    "film_storyboard_execution",
                )
                if k in ctx_copy
            },
            "film_created_via": "compose",
            "film_review_hold": True,
            "prompt": "R3 smoke fixture — standing review hold",
        }
        await db.commit()
        return pid, str(out.id)


async def seed() -> None:
    user_id = await cs.make_user()
    ctx = cs.Ctx(user_id, keep=True)
    try:
        await ctx.set_confirmation(execution="ask", credits="ask")
        pid_r, out_r = await _seed_project(ctx, "R3-smoke R (12 views)", SRC_ASSETS)
        pid_b, out_b = await _seed_project(
            ctx, "R3-smoke B (14 views)", [*SRC_ASSETS, SRC_ASSET_EXTRA]
        )
    finally:
        await ctx.close()
    STATE_FILE.write_text(
        json.dumps(
            {
                "user_id": str(user_id),
                "project_r": pid_r,
                "output_r": out_r,
                "project_b": pid_b,
                "output_b": out_b,
            },
            indent=2,
        )
    )
    print(f"seeded: user={user_id}")
    print(f"  project R (12 views): {pid_r}  output: {out_r}")
    print(f"  project B (14 views): {pid_b}  output: {out_b}")
    print(f"state file: {STATE_FILE}")


async def verify() -> None:
    """The REAL read seat end-to-end minus the LLM: DB rows + storage +
    resize + budget math, gate flipped in-process."""
    from app.chat.perception import executes
    from app.chat.perception.executes import GetOutputSpecParams
    from app.config import settings

    settings.film_edits_enabled = True  # in-process flip — verify leg only
    state = json.loads(STATE_FILE.read_text())

    async with AsyncSessionLocal() as db:
        for label, pid_key, out_key, expect_images in (
            ("R", "project_r", "output_r", 12),
            ("B", "project_b", "output_b", 0),
        ):
            project = await db.get(Project, uuid.UUID(state[pid_key]))
            text, images = await executes.output_spec_observation(
                db, project, GetOutputSpecParams(output_id=uuid.UUID(state[out_key]))
            )
            over_budget = "Image budget" in text
            print(f"\n=== project {label}: default read ===")
            print(f"  observation: {len(text)} chars, {len(text.splitlines())} lines")
            print(f"  images attached: {len(images)}")
            if images:
                import base64 as b64
                first = images[0]
                raw = b64.b64decode(first.data_url.split(",", 1)[1])
                print(f"  first image: {first.mime}, {len(raw)} bytes, caption={first.caption!r}")
            scene_rows = sum(1 for l in text.splitlines() if l.startswith("  [s"))
            checks = {
                "version line": "Storyboard version: 1" in text,
                "base_ref present (gate on)": "base_ref:" in text,
                "executed cut label": "executed cut" in text,
                "scene rows": scene_rows == 15,
                "two clocks split": "actual" in text and "authored 8s" in text,
                "catalog": "Candidate views" in text,
                "scene content verbatim": "Slide deck blues?" in text,
                "narration separate": 'narration: "Made for code, made to share."' in text,
            }
            if label == "B":
                checks["over-budget explicit error"] = over_budget
                checks["zero images on budget breach"] = len(images) == 0
                checks["remedy names scoped read"] = "views" in text and "page/shot" in text
                # The element detail rides WITH the images (ONE set) — the
                # over-budget default read carries neither, by design.
                checks["no orphan camera inventory"] = "camera targets:" not in text
            else:
                checks["at budget, no error"] = not over_budget
                checks["all views attached"] = len(images) == expect_images
                checks["camera targets printed"] = "camera targets:" in text
                checks["element ids listed"] = "s1e15" in text and "Learn more" in text
            for k, ok in checks.items():
                print(f"  [{'OK' if ok else 'FAIL'}] {k}")
                if not ok:
                    raise SystemExit(f"verify failed on project {label}: {k}")

        # scoped single-view high-res re-read on B
        project = await db.get(Project, uuid.UUID(state["project_b"]))
        text, images = await executes.output_spec_observation(
            db,
            project,
            GetOutputSpecParams(
                output_id=uuid.UUID(state["output_b"]),
                views=[{"page": 0, "shot": 1}],
            ),
        )
        import base64 as b64
        raw = b64.b64decode(images[0].data_url.split(",", 1)[1]) if images else b""
        ok = (
            len(images) == 1
            and len(raw) > 60_000  # 1280px JPEG is meaningfully larger than a 640px one
            and "s1e15" in text
            and "Image budget" not in text
        )
        print(f"\n=== project B: scoped single-view read ===")
        print(f"  images: {len(images)}, first image bytes: {len(raw)} (1280px hi-res)")
        print(f"  [{'OK' if ok else 'FAIL'}] one hi-res image + camera inventory, no budget error")
        if not ok:
            raise SystemExit("verify failed on scoped re-read")
    print("\nverify: ALL GREEN (read seat end-to-end minus the LLM)")


# ---- the live journey (PAID) -----------------------------------------------
#
# Activity capture rides the harness's chat_stream (kind/key/status per
# frame) — the assertion helpers below are PURE (StreamTurn + answer text
# in, verdict out) so --selftest proves them against stubs without a model.


def _read_frames(stream: "cs.StreamTurn", key_fragment: str) -> list[dict]:
    return [
        a
        for a in stream.activities
        if a.get("kind") == "read" and key_fragment in str(a.get("key", ""))
    ]


def _answer_of(stream: "cs.StreamTurn") -> str:
    env = (stream.completed or {}).get("assistant_message") or {}
    return env.get("content") or "".join(stream.deltas)


# Per-leg answer laws (pure — the smoke's checkable kernel). Each returns a
# list of (label, ok) pairs; the live legs feed the REAL turn, --selftest
# feeds crafted stubs.

def check_l1(answer: str, stream: "cs.StreamTurn") -> list[tuple[str, bool]]:
    return [
        ("L1: the get_output_spec read fired",
         bool(_read_frames(stream, "outputSpec"))),
        ("L1: answer names 15 scenes", "15" in answer),
        ("L1: answer names aspect 9:16", "9:16" in answer),
    ]


def check_l2(answer: str) -> list[tuple[str, bool]]:
    return [
        ("L2: the film's overlay words quoted from the READ",
         "Slide deck blues" in answer),
        ("L2: the screenshot's visible heading named (pixel knowledge)",
         "We enable developers" in answer),
    ]


def check_l3(answer: str) -> list[tuple[str, bool]]:
    low = answer.lower()
    return [
        ("L3: the card's text (element inventory)",
         "share interactive slides" in low),
        ("L3: the LEFT green code panel — pixel-only knowledge",
         "green" in low and ("code" in low or "smoosh" in low)),
    ]


def check_l6(answer: str) -> list[tuple[str, bool]]:
    return [
        ("L6: the ACTUAL executed duration (245f = 8.2s), not authored 8s",
         "8.2" in answer or "245" in answer),
    ]


def check_l5(answer: str) -> list[tuple[str, bool]]:
    """The honest shapes after a budget breach: the model re-reads scoped,
    or asks which views — never a pretend-full-view answer."""
    low = answer.lower()
    honest = (
        "12" in answer
        or "budget" in low
        or "limit" in low
        or "which" in low
        or "pricing" in low  # scoped straight at the asked page
    )
    return [
        ("L5: the answer acknowledges the cap or scopes — never pretends "
         "to have seen all 14 views", honest),
    ]


async def _pending_bytes(pid: str) -> bytes:
    """The pending film state's canonical bytes (the read-immutability and
    standing-hold assertions' substrate)."""
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(pid))
        pending = project.pending_brief if isinstance(project.pending_brief, dict) else {}
        return json.dumps(pending, sort_keys=True, ensure_ascii=False).encode()


async def _side_effect_assertions(pid: str, user_id: uuid.UUID, label: str) -> None:
    """L7 — after EVERY leg. Two families:

    AUXILIARY tripwires (the deterministic boundary is the 8001 instance's
    create_run blocker — state-independent; the fixture's standing
    review_hold is the product law under test): zero new runs, zero new
    outputs, zero ledger rows for the fixture user.

    AUTHORIZATION law: the standing review hold is NEVER released — not by
    reads, not by an edit (a patch carries no new hold and never releases a
    standing one). Note this is NOT 'no hold ever appears': the fixture
    seeds the hold and it must still stand at the end of every leg.
    """
    runs = await cs.count_runs(pid)
    cs.check(runs == 1, f"{label}: exactly the seeded run exists (no new run)", runs)
    films = await cs.outputs_of(pid, "film")
    cs.check(len(films) == 1, f"{label}: exactly the seeded film output exists", len(films))
    async with AsyncSessionLocal() as db:
        ledger = await db.scalar(
            select(func.count())
            .select_from(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
        )
        cs.check((ledger or 0) == 0, f"{label}: zero credit ledger rows", ledger)
        project = await db.get(Project, uuid.UUID(pid))
        pending = project.pending_brief if isinstance(project.pending_brief, dict) else {}
        cs.check(
            pending.get("film_review_hold") is True,
            f"{label}: the standing review hold still stands (never released "
            "by a read or an edit)",
            pending.get("film_review_hold"),
        )


async def run_journey(base: str) -> None:
    state = json.loads(STATE_FILE.read_text())
    user_id = uuid.UUID(state["user_id"])
    pid_r, pid_b = state["project_r"], state["project_b"]

    # Point the harness at the gate-on instance.
    cs.BASE = base
    ctx = cs.Ctx(user_id, keep=True)
    log = Path("/tmp/r3_smoke_transcript.md")
    rec: list[str] = []
    try:
        await ctx.set_confirmation(execution="ask", credits="ask")

        async def leg(
            label: str, pid: str, message: str, *, read_only: bool = True
        ) -> "cs.StreamTurn":
            """One turn: stream it, then the L7 law. ``read_only`` legs
            additionally assert the pending film state is BYTE-UNCHANGED
            (a read never writes). Per-leg answer laws run at the call site."""
            before = await _pending_bytes(pid)
            print(f"\n--- {label}: {message[:80]}")
            stream = await ctx.chat_stream(pid, message)
            answer = _answer_of(stream)
            cs.check(stream.failed is None, f"{label}: turn did not fail", stream.failed)
            reads = [a for a in stream.activities if a.get("kind") == "read"]
            rec.append(
                f"\n## {label}\n\n**user**: {message}\n\n**assistant**: {answer}\n\n"
                f"activity frames: {[(a.get('kind'), a.get('key'), a.get('status')) for a in stream.activities]}\n"
            )
            print(f"  assistant: {answer[:240]}")
            print(f"  read activities: {[a.get('key') for a in reads]}")
            if read_only:
                after = await _pending_bytes(pid)
                cs.check(
                    after == before,
                    f"{label}: a read leaves the pending film state byte-unchanged",
                    "pending_brief drifted",
                )
            await _side_effect_assertions(pid, user_id, label)
            return stream

        # L1 — naming the film reads THAT version
        s = await leg(
            "L1 read the named film",
            pid_r,
            "There's a film in this project. Read its current state and tell "
            "me: what storyboard version is it on, how many scenes does it "
            "have, and what aspect ratio is it?",
        )
        for chk_label, ok in check_l1(_answer_of(s), s):
            cs.check(ok, chk_label, _answer_of(s)[:400])

        # L2 — film overlay words vs the screenshot's own text (two sources)
        s = await leg(
            "L2 overlay vs screenshot text",
            pid_r,
            "Two different things, please: (1) the film's OPENING scene "
            "animates a few word lines — quote them exactly; (2) in the "
            "captured fold view of the homepage, what is the big heading "
            "actually visible at the top of the page?",
        )
        for chk_label, ok in check_l2(_answer_of(s)):
            cs.check(ok, chk_label, _answer_of(s)[:400])

        # L3 — view-specific read consumes the screenshot (pixel-only facts)
        s = await leg(
            "L3 scoped view read",
            pid_r,
            "Look closely at the homepage's second captured view (page 0, "
            "shot 1 — the 'Create next-level presentations' section). What's "
            "on the LEFT side of that section, and what does the little card "
            "below the 'Learn more' link say?",
        )
        for chk_label, ok in check_l3(_answer_of(s)):
            cs.check(ok, chk_label, _answer_of(s)[:400])

        # L4 — a framing edit references ids from the ACTUAL read. NOT
        # read-only: a landed patch legitimately bumps the pending version —
        # the standing hold must survive it (asserted in L7).
        s = await leg(
            "L4 framing edit with real element id",
            pid_r,
            "Scene 5 walks the 'Create next-level presentations' view and its "
            "camera pushes to the 'Learn more' button. Change that scene's "
            "camera focus to the 'Share interactive slides' card instead.",
            read_only=False,
        )
        answer = _answer_of(s)
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, uuid.UUID(pid_r))
            pending = project.pending_brief if isinstance(project.pending_brief, dict) else {}
            board = pending.get("film_storyboard") or {}
            version = pending.get("film_storyboard_version")
            scenes = board.get("scenes") or []
            scene5 = scenes[4] if len(scenes) >= 5 else {}
            focuses = scene5.get("focuses") or []
            focus_ids = [f.get("element") for f in focuses if isinstance(f, dict)]
        print(f"  pending version: {version}, scene5 focuses: {focus_ids}")
        rec.append(f"L4 pending version={version} scene5 focuses={focus_ids}\n")
        if version == 2 and focus_ids:
            cs.check(
                focus_ids == ["s1e15"],
                "L4: the new focus is the element id FROM THE READ INVENTORY "
                "(never a guessed id)",
                focus_ids,
            )
            # The patch beat's activity wiring (server wire law): the edit
            # landed, so a draft-kind span must have opened and settled
            # (T16-B — the harness's stream laws already swept dangling
            # actives) — AND it must speak the EDIT pair: a targeted edit
            # reads as 调整, never as a fresh 设计 (the compose pair would
            # be a copy lie on the persisted receipt).
            draft_keys = [
                a.get("key") for a in s.activities if a.get("kind") == "draft"
            ]
            cs.check(
                "chat.activity.storyboardEdit" in draft_keys
                and "chat.activity.storyboardEditDone" in draft_keys,
                "L4: the landed patch's span speaks the edit copy pair "
                "(storyboardEdit → storyboardEditDone)",
                draft_keys,
            )
        else:
            rec.append(
                f"L4 SOFT-FAIL: model did not land the edit (version={version}); "
                f"answer excerpt: {answer[:300]}\n"
            )
            print("  L4 SOFT-FAIL: edit not landed — see transcript (model "
                  "behavior, not a safety breach)")

        # L6 — authored design seconds vs the actual executed cut
        s = await leg(
            "L6 authored vs actual duration",
            pid_r,
            "How long does scene 14 actually play in the delivered film? "
            "I mean the real rendered duration, not the design figure.",
        )
        for chk_label, ok in check_l6(_answer_of(s)):
            cs.check(ok, chk_label, _answer_of(s)[:400])

        # L5 — over-budget default read → scoped re-read (project B, 14 views)
        s = await leg(
            "L5 budget breach re-scopes",
            pid_b,
            "Pull up every captured view of the site so you can see them "
            "all, then tell me what the pricing page's fold shows.",
        )
        reads = _read_frames(s, "outputSpec")
        rec.append(f"L5 read-frame count={len(reads)}\n")
        print(f"  L5 read frames: {len(reads)}")
        for chk_label, ok in check_l5(_answer_of(s)):
            cs.check(ok, chk_label, _answer_of(s)[:400])

    finally:
        log.write_text("\n".join(rec))
        print(f"\ntranscript: {log}")
        await ctx.close()
    print("\njourney: ALL HARD ASSERTIONS GREEN (L4 soft-fail possible — see transcript)")


def _stub_turn(activities: list[dict], answer: str) -> "cs.StreamTurn":
    return cs.StreamTurn(
        deltas=[answer],
        thinking=[],
        previews=[],
        completed={"assistant_message": {"content": answer}},
        failed=None,
        checkpoints=[],
        checkpoints_pre_read=[],
        activities=activities,
        raw_events=[],
        row_events=[],
    )


def selftest() -> None:
    """FREE proof of the capture + assertion kernel (no model, no API):
    crafted StreamTurn stubs must pass/fail the per-leg laws as designed."""
    read_frame = {"kind": "read", "key": "chat.inspecting.outputSpec",
                  "status": "completed", "activity_id": "a1", "seq": 1}

    def expect(fn_answer_pairs, want_all: bool, label: str) -> None:
        results = [ok for _, ok in fn_answer_pairs]
        got = all(results)
        assert got == want_all, f"{label}: want {want_all}, got {results}"
        print(f"[selftest] {label}: {'pass' if want_all else 'fail'} as designed")

    # L1 law
    good = _stub_turn([read_frame], "It is on version 1 with 15 scenes, aspect 9:16.")
    expect(check_l1(_answer_of(good), good), True, "L1 good stub passes")
    blind = _stub_turn([], "It has 15 scenes, aspect 9:16.")  # no read frame
    expect(check_l1(_answer_of(blind), blind), False, "L1 read-less stub fails")
    wrong = _stub_turn([read_frame], "8 scenes, 16:9.")
    expect(check_l1(_answer_of(wrong), wrong), False, "L1 wrong-facts stub fails")

    # L2 law (two sources must BOTH appear)
    expect(check_l2('The opening animates "Slide deck blues?" …; the fold shows '
                    '"We enable developers to create stunning presentations".'),
           True, "L2 two-source stub passes")
    expect(check_l2("The opening shows We enable developers…"),
           False, "L2 single-source stub fails")

    # L3 law (pixel-only leg is the discriminator)
    expect(check_l3("Left is a green panel with a code editor (smoosh.py); the card "
                    "says Share interactive slides…"),
           True, "L3 full stub passes")
    expect(check_l3("The card says Share interactive slides…"),
           False, "L3 text-only stub fails (no pixel knowledge)")

    # L6 law (actual, not authored)
    expect(check_l6("Scene 14 plays 8.2s in the delivered film (245 frames)."),
           True, "L6 actual-duration stub passes")
    expect(check_l6("Scene 14 plays 8 seconds."), False, "L6 authored-only stub fails")

    # L5 law (honest scoping vs pretend-full-view)
    expect(check_l5("The read caps at 12 views — I scoped to the pricing page's "
                    "views instead."), True, "L5 scoped stub passes")
    expect(check_l5("Here is what every view shows: …"), False,
           "L5 pretend-full-view stub fails")

    print("[selftest] capture + assertion kernel: all stubs behave as designed")


async def cleanup() -> None:
    state = json.loads(STATE_FILE.read_text())
    ctx = cs.Ctx(uuid.UUID(state["user_id"]), keep=False)
    ctx.project_ids = [state["project_r"], state["project_b"]]
    try:
        await ctx.cleanup()
    finally:
        await ctx.close()
    # the fixture user itself
    async with AsyncSessionLocal() as db:
        from app.models.tables import User

        await db.execute(delete(User).where(User.id == uuid.UUID(state["user_id"])))
        await db.commit()
    STATE_FILE.unlink(missing_ok=True)
    print("fixture deleted (projects via API, user row direct)")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--selftest", action="store_true",
                        help="assertion-kernel stub proof (free, no model/API)")
    parser.add_argument("--base", default=None, help="gate-on API base (e.g. http://127.0.0.1:8001/api/v1)")
    args = parser.parse_args()
    if args.selftest:
        selftest()
    if args.seed:
        await seed()
    if args.verify:
        await verify()
    if args.run:
        if not args.base:
            print("--run needs --base pointing at the GATE-ON API instance", file=sys.stderr)
            return 2
        await run_journey(args.base)
    if args.cleanup:
        await cleanup()
    if not any((args.seed, args.verify, args.run, args.cleanup, args.selftest)):
        parser.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
