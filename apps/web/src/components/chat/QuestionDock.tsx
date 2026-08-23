/** QuestionDock — the pending question's home, docked above the input.
 *
 * The message list is the archive of *decided* things; the dock holds the
 * one *pending* decision (ask primitive — at most one at a time). The kind
 * selects the form (NAMING N-19: the use lives in `question.kind`, the
 * mechanism is the dock — no per-kind dock components):
 * - task_book: two rows (2026-08-06 rework; 2026-08-14 对齐参考定稿) — the
 *   confirm line on the top-left, the reserved credit slot on the top-right
 *   (the week-6 cost quote rides `estimate`), the actions (Cancel / Start)
 *   on the bottom row. No reasons line — the agent's inference bookkeeping
 *   (chain_default / clip_count_default) is not user copy; the plan card
 *   above carries the substance and the streamed echo carries the caveats.
 * - choice: the question line plus its options as full-width ROWS (letter
 *   badges mirror the deterministic autoResume mapping — typing "a" picks
 *   option a); long labels wrap, never overflow the card. With `joined`
 *   the dock fuses visually with the input below — the input IS the
 *   freeform "something else" row (its placeholder already switches), so
 *   the two read as one card.
 * Answering collapses the question into a QA pair in the flow.
 */

import { Check, ChevronDown, Loader2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { apiFetch } from "@/lib/api"

export type Autonomy = "auto" | "review"

/** The autonomy tier picker is hidden, not retired (2026-07-31): the concept
 * read as noise at confirm time ("switching it changes nothing"). The
 * plumbing stays — the tier still rides the start answer; flip this flag to
 * re-expose the picker. */
const SHOW_AUTONOMY_PICKER = false

/** One option on a choice question (mirrors the API's AskOption). */
export interface DockOption {
  id: string
  label: string
}

/** One clip's parked hook preview (期 4 钩子预览闸 — mirrors the API's
 * HookPreview): the ≤5s low-res render + the planned stills shots (the
 * 换图锚 control's addressing: index = shot_index) + the kept span (the
 * 调尾切点 seat). */
export interface HookPreviewItem {
  output_id: string
  url: string
  hook?: string | null
  shots?: string[]
  trim?: { start: number; end: number } | null
}

interface TaskBookDockProps {
  kind: "task_book"
  /** The confirm display line (localized). */
  question: string
  autonomy: Autonomy
  onAutonomyChange: (next: Autonomy) => void
  onStart: () => void
  /** Bail — a graceful exit (back to draft), never an error path. */
  onCancel: () => void
  starting: boolean
  startDisabled?: boolean
  /** Reserved anatomy (cost quote, week-8 计费线) — muted at the top-right
   * when present; the slot is the layout reservation. */
  estimate?: string | null
  /** Bare child of the dock shell's unified frosted container (D4 修订
   * 一体容器): no fill / rounding / margin of its own — the container owns
   * the chrome. */
  plain?: boolean
}

interface ChoiceDockProps {
  kind: "choice"
  /** The question's human text (LLM-written user data, shown as-is). */
  question: string
  options: DockOption[]
  /** 钩子预览闸 (期 4): one parked hook preview per clip — rendered between
   * the question line and the options. */
  previews?: HookPreviewItem[]
  /** Reserved anatomy (cost quote, v3) — shown muted when present. */
  estimate?: string | null
  onAnswer: (optionId: string) => void
  answering: boolean
  /** Bail affordance — only passed for interrupt questions (a run is
   * parked on the answer); plain chat asks get no bail (the next message
   * supersedes them anyway). A graceful exit, never an error path. */
  onBail?: () => void
  /** Fuse the dock with the input below (the input IS the freeform
   * "something else" row) — drops the bottom margin and rounding. */
  joined?: boolean
  /** Bare child of the dock shell's unified container (D4 修订 一体容器):
   * no fill / rounding / margin of its own — the container owns the chrome. */
  plain?: boolean
}

export type QuestionDockProps = TaskBookDockProps | ChoiceDockProps

const AUTONOMY_TIERS: Autonomy[] = ["auto", "review"]

function TaskBookForm({
  question,
  autonomy,
  onAutonomyChange,
  onStart,
  onCancel,
  starting,
  startDisabled,
  estimate,
  plain,
}: TaskBookDockProps) {
  const { t } = useTranslation()
  return (
    <div className={plain ? "px-4 py-3" : "mb-2 rounded-lg bg-muted px-5 py-4"}>
      {/* Top row: the confirm line (left) + the reserved credit slot
          (right). Copy stays one line — the plan card above carries the
          substance. */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <Check className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="truncate text-sm font-medium">{question}</span>
        </div>
        {estimate ? (
          <span className="shrink-0 text-xs text-muted-foreground">
            {estimate}
          </span>
        ) : null}
      </div>
      {/* Bottom row: the actions — Cancel quiet on the left, Start solid on
          the right (the one dark anchor, composer-bottom-row discipline).
          Both at the action-row h-9; Start gets px-5 presence — this bar is
          the confirm phase's single decision CTA, not a toolbar chip. */}
      <div className="mt-4 flex items-center justify-between gap-2">
        <Button
          variant="ghost"
          onClick={onCancel}
          disabled={starting}
          className="h-9 px-3 text-muted-foreground"
        >
          {t("common.cancel")}
        </Button>
        <div className="flex items-center gap-2">
          {SHOW_AUTONOMY_PICKER ? (
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 gap-1.5"
                    aria-label={t("questionDock.autonomy.label")}
                  />
                }
              >
                <span>{t(`questionDock.autonomy.${autonomy}`)}</span>
                <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" align="end">
                {AUTONOMY_TIERS.map((tier) => (
                  <DropdownMenuItem
                    key={tier}
                    onClick={() => onAutonomyChange(tier)}
                  >
                    <span className="flex-1">{t(`questionDock.autonomy.${tier}`)}</span>
                    {tier === autonomy ? <Check className="h-4 w-4" /> : null}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
          <Button
            disabled={startDisabled || starting}
            onClick={onStart}
            className="h-9 px-5"
          >
            {starting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("generationOverlay.starting")}
              </>
            ) : (
              t("generationOverlay.confirm")
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

/** One clip's adjust op against the parked spec (期 4): the same
 * user-callable ops endpoint the clip editor saves through. The server
 * detail rides apiFetch's default error toast; the boolean gates the
 * optimistic local update. */
async function applyHookOp(
  outputId: string,
  op: { op: string; params: Record<string, unknown> },
): Promise<boolean> {
  const res = await apiFetch(`/api/v1/outputs/${outputId}/operations`, {
    method: "POST",
    body: { ops: [op] },
  })
  return res.ok
}

/** One parked clip: the ≤5s low-res hook player (click-to-play — the hook
 * judgment needs the audio) + the hook line + the light adjust row
 * (换图锚 thumbnails for stills, 调尾切点 stepper for any clip). Adjustments
 * journal real ops against the parked spec; the preview honestly stays the
 * pre-adjustment cut (the strip's note says so once anything changes). */
function HookPreviewTile({
  preview,
  disabled,
  onAdjusted,
}: {
  preview: HookPreviewItem
  /** An answer is in flight — the release may already own the render, so
   * further adjustments could miss it. */
  disabled?: boolean
  onAdjusted: () => void
}) {
  const { t } = useTranslation()
  const [shots, setShots] = useState(preview.shots ?? [])
  const trimStart = preview.trim?.start ?? 0
  const initialEnd = preview.trim?.end ?? 0
  const [trimEnd, setTrimEnd] = useState(initialEnd)
  const [busy, setBusy] = useState(false)
  const locked = busy || disabled

  const swap = async (index: number) => {
    if (locked || index === 0) return
    setBusy(true)
    try {
      const ok = await applyHookOp(preview.output_id, {
        op: "swap_hook_shot",
        params: { shot_index: index },
      })
      if (ok) {
        setShots((prev) => [
          prev[index],
          ...prev.slice(0, index),
          ...prev.slice(index + 1),
        ])
        onAdjusted()
      }
    } finally {
      setBusy(false)
    }
  }

  const trim = async (delta: number) => {
    if (locked || !preview.trim) return
    const next = trimEnd + delta
    // Bounds: never under a 1s clip; the slack above the cut stays small —
    // the source tail beyond the span is unknowable here (期 2's post-pad
    // is 1.8s), so +5s is the honest room.
    if (next < trimStart + 1 || next > initialEnd + 5) return
    setBusy(true)
    try {
      const ok = await applyHookOp(preview.output_id, {
        op: "set_trim",
        params: { start: trimStart, end: next },
      })
      if (ok) {
        setTrimEnd(next)
        onAdjusted()
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex w-36 shrink-0 flex-col gap-1.5">
      <video
        src={preview.url}
        controls
        playsInline
        preload="metadata"
        className="h-36 w-auto max-w-full self-start rounded-md"
      />
      {preview.hook ? (
        <p className="line-clamp-2 text-xs text-muted-foreground">
          {preview.hook}
        </p>
      ) : null}
      {shots.length > 1 ? (
        <div className="flex flex-wrap gap-1">
          {shots.map((url, i) => (
            // Key carries the index: a beat plan may legitimately reuse an
            // image (图耗尽 reuse), so the URL alone is not unique.
            <button
              key={`${i}-${url}`}
              type="button"
              disabled={locked || i === 0}
              title={
                i === 0
                  ? t("hookGate.currentOpener")
                  : t("hookGate.makeOpener")
              }
              onClick={() => swap(i)}
              className={
                i === 0
                  ? "cursor-default"
                  : "cursor-pointer opacity-60 transition-opacity hover:opacity-100"
              }
            >
              <img
                src={url}
                alt=""
                className="h-9 w-9 rounded object-cover"
              />
            </button>
          ))}
        </div>
      ) : null}
      {preview.trim ? (
        <div className="flex items-center gap-1">
          <span className="text-[11px] text-muted-foreground">
            {t("hookGate.ending")}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-1.5 text-[11px]"
            disabled={locked || trimEnd - 1 < trimStart + 1}
            onClick={() => trim(-1)}
          >
            −1s
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-1.5 text-[11px]"
            disabled={locked || trimEnd + 1 > initialEnd + 5}
            onClick={() => trim(1)}
          >
            +1s
          </Button>
        </div>
      ) : null}
    </div>
  )
}

/** The 钩子预览闸's preview strip (期 4, §2.5): one tile per parked clip in
 * a horizontal scroll row — structure scans off the shot thumbnails, pacing
 * off the click-to-play low-res hook. */
function HookPreviewStrip({
  previews,
  disabled,
}: {
  previews: HookPreviewItem[]
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const [adjusted, setAdjusted] = useState(false)
  return (
    <div className="mt-3">
      <div className="no-scrollbar flex gap-3 overflow-x-auto pb-1">
        {previews.map((p) => (
          <HookPreviewTile
            key={p.output_id}
            preview={p}
            disabled={disabled}
            onAdjusted={() => setAdjusted(true)}
          />
        ))}
      </div>
      {adjusted ? (
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          {t("hookGate.adjustedNote")}
        </p>
      ) : null}
    </div>
  )
}

function ChoiceForm({
  question,
  options,
  previews,
  estimate,
  onAnswer,
  answering,
  onBail,
  joined,
  plain,
}: ChoiceDockProps) {
  const { t } = useTranslation()
  return (
    <div
      className={
        plain
          ? "px-4 py-3"
          : joined
            ? "rounded-t-lg bg-muted px-4 py-3"
            : "mb-2 rounded-lg bg-muted px-4 py-3"
      }
    >
      <div className="flex items-start gap-2 text-sm">
        <Check className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="min-w-0 break-words">{question}</span>
        {estimate ? (
          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
            {estimate}
          </span>
        ) : null}
      </div>
      {previews && previews.length > 0 ? (
        <HookPreviewStrip previews={previews} disabled={answering} />
      ) : null}
      {options.length > 0 ? (
        // Full-width rows, not pills: long option labels must wrap inside
        // the card (the old button row let them bleed past the right edge).
        <div className="mt-3 flex flex-col gap-2">
          {options.map((option) => (
            <Button
              key={option.id}
              variant="ghost"
              disabled={answering}
              onClick={() => onAnswer(option.id)}
              className="h-auto w-full items-start justify-start gap-2.5 whitespace-normal rounded-md bg-card px-3 py-2.5 text-left hover:bg-accent"
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-muted text-[11px] font-medium uppercase text-muted-foreground">
                {option.id}
              </span>
              <span className="min-w-0 break-words">{option.label}</span>
            </Button>
          ))}
          {answering || onBail ? (
            <div className="flex items-center gap-2">
              {answering ? (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              ) : null}
              {onBail ? (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 text-muted-foreground"
                  disabled={answering}
                  onClick={onBail}
                >
                  {t("questionDock.bail")}
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function QuestionDock(props: QuestionDockProps) {
  if (props.kind === "choice") return <ChoiceForm {...props} />
  return <TaskBookForm {...props} />
}
