/** RunTaskList — the run's task list (the Claude Code anatomy): ONE
 * persistent block — pinned bottom-most in the message flow while the run
 * is live, the archive of it once terminal. THE DYNAMIC ROW IS THE WHOLE
 * CHROME (2026-09-08 user ruling, twice — first merge, then the register
 * correction): the single row is the CC status line in ONE quiet register
 * — text-xs muted — and IT is the expand/collapse anchor. LIVE: ● shimmer
 * narrative (what's happening NOW — the text is dynamic by definition) +
 * its own stage elapsed. TERMINAL: the SAME line's receipt form — ✓ plan
 * title · total elapsed, same size same gray (降灰 reads as quiet, never
 * the retired header's text-sm/font-medium/ListChecks register — that
 * second row was the one ordered deleted, not archived). The steps render
 * FLAT under the one row (the "Preparation · n steps" group row died the
 * same way). BOTH poses default folded (2026-09-13 user ruling — the one
 * dynamic row is the whole at-a-glance surface; the rail tree opens on
 * click), the terminal frame always lands on the one-line receipt — and
 * the completion prose follows over SSE. Row text
 * is BUILDER-WRITTEN: spec.summary arrives preset from the server (the
 * static task name / slot tag) and is rewritten with the quantified line
 * when the step completes — the frontend renders spec fields, never
 * kind→copy dictionaries. The only frontend copy left is the PROGRESSIVE
 * fallback (stage hints / kind progressive) for the live narrative. */

import { useEffect, useState } from "react"
import type { TFunction } from "i18next"
import { Check, CircleHelp, Loader2, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"
import type { WorkflowStep } from "@/lib/types"

import { StatusLine } from "./StatusLine"

/** Ticking clock for the elapsed counters — null until mounted (SSR-safe:
 * the server render and the first client render both show no elapsed), and
 * frozen once `live` goes false (the terminal frame keeps its last read).
 * Shared by the checklist's row AND the dock's ThinkingRow (one clock, one
 * hydration contract — 2026-09-05 减法批). */
export function useNow(live: boolean): number | null {
  const [now, setNow] = useState<number | null>(null)
  useEffect(() => {
    if (!live) return
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [live])
  return now
}

/** "1m 6s" / "45s" / "1h 3m" — the Claude Code elapsed shorthand, the ONE
 * copy (the thinking row consumed a byte-identical twin until the same
 * subtraction batch). */
export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

/** The live narrative's step pick + progressive copy chain (the dynamic
 * row's reading material): the running step wins; a parked interrupt
 * (review tier) has no running step and reads through the same chain
 * ("waiting for your direction", not the queued fallback). Copy chain: the
 * runner's stage hint → the kind's progressive form → the preset task name
 * → the raw kind.
 * Honesty carve-out (2026-09-04): the preprocess node's "Analyzing your
 * uploads…" is a lie on a zero-upload (copy-writer) run — it validates
 * material and admits the writer lift, so it reads the generic
 * "Preparing generation…" instead. */
function runNarrative(
  steps: WorkflowStep[],
  t: TFunction,
  hasUploads: boolean,
): { running: WorkflowStep | null; waiting: WorkflowStep | null; label: string | null } {
  const running = steps.find((s) => s.status === "running") ?? null
  const waiting = steps.find((s) => s.status === "waiting") ?? null
  const step = running ?? waiting
  const label = step
    ? step.kind === "preprocess" && !hasUploads
      ? t("results.stepper.prepare")
      : (step.stage ? t(`results.stepper.${step.stage}`, { defaultValue: "" }) : "") ||
        t(`chat.stepKinds.${step.kind}`, { defaultValue: "" }) ||
        step.summary ||
        step.kind
    : null
  return { running, waiting, label }
}

export function RunTaskList({
  steps,
  title,
  runStartedAt,
  terminal,
  failed,
  narrativeFallback,
  hasUploads,
}: {
  steps: WorkflowStep[]
  /** The plan's summary line — the receipt row's resting title. */
  title: string
  runStartedAt: string | null
  terminal: boolean
  /** The run's terminal failure pose (2026-09-13 user ruling): the receipt
   * header itself carries the failure — red ✗ chip + red title — and the
   * reason lives on the failed step row inside the rail tree. NO separate
   * "generation failed" message item ever follows the receipt. */
  failed: boolean
  /** What the narrative line says when no step is running yet (assets still
   * processing / the run still queued) — the caller knows which. */
  narrativeFallback: string
  /** Honest preprocess copy: with zero uploads the "Analyzing your
   * uploads…" progressive is a lie (chat-flow-sequencing 验收 5). */
  hasUploads: boolean
}) {
  const { t } = useTranslation()
  const now = useNow(!terminal)
  const { running, label: narrativeLabel } = runNarrative(steps, t, hasUploads)
  // 交接缝的措辞 (2026-09-29 走查拍板): a between-steps gap (previous
  // committed, next not yet claimed — worker tick + SSE tail) reads the
  // plain thinking word — not the queued fallback (the run IS advancing,
  // 「正在排队」 is a lie mid-run). The genuinely-unstarted run (every step
  // still pending) keeps the caller's fallback (assets processing / truly
  // queued — truthful there).
  const runStarted = steps.some((s) => s.status !== "pending")
  const liveLabel =
    narrativeLabel ??
    (runStarted ? t("chat.thinking") : null) ??
    narrativeFallback
  const startedMs = runStartedAt ? Date.parse(runStartedAt) : null
  // The archive frame (mounting an already-terminal run) has no ticking
  // clock — the total reads off the last step's finish instead.
  const endMs = terminal
    ? Math.max(
        startedMs ?? 0,
        ...steps
          .map((s) => Date.parse((s.finished_at ?? s.started_at ?? "") as string))
          .filter((ms) => !Number.isNaN(ms)),
      )
    : now
  const elapsed =
    endMs != null && startedMs != null && !Number.isNaN(endMs)
      ? formatElapsed(endMs - startedMs)
      : null

  const runningMs = running?.started_at ? Date.parse(running.started_at) : null
  const stageElapsed =
    now != null && runningMs != null ? formatElapsed(now - runningMs) : null

  // THE dynamic row IS the anchor (2026-09-08 层级翻案): userOpen null =
  // follow the pose — EXPANDED while live (2026-09-29 user ruling: the rail
  // tree IS the run's live reading — the single narrative row alone buried
  // the step-by-step advance), folded at the settle (落档即收: the terminal
  // flip resets an untouched toggle so the archive always lands on the
  // one-line receipt; an explicit post-settle click re-opens it).
  const [userOpen, setUserOpen] = useState<boolean | null>(null)
  useEffect(() => {
    if (terminal) setUserOpen(null)
  }, [terminal])
  const open = userOpen ?? !terminal

  return (
    <div className="w-full">
      {/* THE ONE ROW — the run's seat of the shared StatusLine (2026-09-09
          一座两行; 2026-09-10 层级重铸 — the receipt is the OWNER row): live
          = shimmer narrative + its stage clock; terminal = the receipt pose.
          ONE anatomy across the settle (2026-09-25 user ruling — 完成和 ing
          同一个样式，以 ing 为准): the terminal leading mark is the SAME
          12px seat the live dot occupies (✓ success / red ✗ failure — the
          ActivityRow settled glyph's own size), the 16px circle stamp
          retired (it restyled the whole row at the settle moment — the
          style flip the user caught). The settled title reads MUTED like
          the rest of the chrome (2026-09-24 user ruling — the foreground +
          font-medium pose read as content prose, not chrome; red stays for
          the failed pose), total elapsed + chevron right. It is itself the
          expand/collapse toggle for the railed checklist below. */}
      <StatusLine
        label={
          terminal ? (
            <span
              className={cn(failed ? "text-destructive" : "text-muted-foreground")}
            >
              {title}
            </span>
          ) : (
            liveLabel
          )
        }
        active={!terminal}
        leading={
          terminal ? (
            failed ? (
              // The failed mark — the same 12px seat as the ✓, red says
              // failure; the failed step row inside the tree says why.
              <X className="h-3 w-3 shrink-0 text-destructive" />
            ) : (
              <Check className="h-3 w-3 shrink-0" />
            )
          ) : (
            // The live dot RIDES the same 12px seat the terminal marks
            // occupy, centered (2026-09-27 user ruling: the bare 6px span
            // left-shifted live labels 6px against the settled rows and
            // missed the checklist guide's 5.5px center), and takes the
            // label's own ink — bg-primary's solid black read as a second
            // register next to the muted text.
            <span className="flex h-3 w-3 shrink-0 items-center justify-center">
              <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
            </span>
          )
        }
        trailing={(terminal ? elapsed : stageElapsed) || null}
        onClick={() => setUserOpen(!open)}
        open={open}
        quiet
      />

      {/* The checklist — the rail tree (2026-09-10 提案 A 拍板): a 1px guide
          drops from the leading mark's center (12px glyph → 5.5px, same law
          the 16px chip's 7px followed), the steps indent under it — parentage
          is GEOMETRY, not repetition. Steps carry NO per-row ✓ (success is
          the default and says nothing per row; the chip above already said
          it once): live rows keep their spinner, failed rows open red,
          waiting keeps its ?, pending stays a quiet dash. Voice tiers:
          no-op rows (status skipped || spec.noop — the runner's structured
          declaration, never a string match) read whisper + line-through
          ("this step was crossed off the plan"); work rows keep the normal
          muted register, their quantified values doing the talking. */}
      {open ? (
        <div className="mt-2 ml-[5.5px] flex flex-col gap-1.5 border-l border-foreground/15 pl-3.5">
          {steps.map((step) => (
            <TaskRow key={step.id} step={step} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function TaskRow({ step }: { step: WorkflowStep }) {
  const noop = step.status === "skipped" || step.noop === true
  const icon =
    step.status === "running" ? (
      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
    ) : step.status === "failed" ? (
      <X className="h-3.5 w-3.5 text-destructive" />
    ) : step.status === "waiting" ? (
      <CircleHelp className="h-3.5 w-3.5 text-primary" />
    ) : null
  // Builder-written text: done rows carry the runner's quantified rewrite,
  // everything else the creation-time preset (static task name / slot tag).
  const label = step.summary ?? step.kind
  return (
    <div className="flex items-baseline gap-2 text-xs">
      {/* Fixed icon slot — present only where a marker means something
          (running / failed / waiting), so the texts of unmarked rows share
          the rail's left line. */}
      <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center self-center">
        {icon}
      </span>
      <span
        className={cn(
          "min-w-0 break-words",
          noop
            ? "text-meta-foreground line-through decoration-foreground/25"
            : step.status === "done"
              ? "text-muted-foreground"
              : step.status === "failed"
                ? "text-destructive"
                : "text-muted-foreground/70",
          step.status === "running" && "shimmer text-muted-foreground",
        )}
      >
        {step.status === "failed" && step.error
          ? `${label} — ${step.error}`
          : label}
      </span>
    </div>
  )
}
