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
 * - choice (ADR-051 形态切换): while a choice question is pending the chat
 *   input row and the disclaimer HIDE — the dock IS the question: the
 *   question line (no ✓; the right-side × is the bail channel), its options
 *   as full-width ROWS (letter badges mirror the deterministic autoResume
 *   mapping — typing "a" picks option a; long labels wrap, never overflow),
 *   and the tail pencil row for a freeform answer (Enter submits through the
 *   same send channel as the chat input).
 * Answering collapses the question into a QA pair in the flow.
 */

import { useState } from "react"
import { Check, ChevronDown, Loader2, Pencil, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

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

interface TaskBookDockProps {
  kind: "task_book"
  /** The confirm display line (localized). */
  question: string
  autonomy: Autonomy
  onAutonomyChange: (next: Autonomy) => void
  onStart: () => void
  starting: boolean
  startDisabled?: boolean
  /** Reserved anatomy (cost quote, week-8 计费线) — muted at the top-right
   * when present; the slot is the layout reservation. */
  estimate?: string | null
  /** Chromeless content for the floating question pill (2026-09-02 拆粘):
   * no fill / rounding / margin of its own — the pill owns the chrome. */
  plain?: boolean
}

interface ChoiceDockProps {
  kind: "choice"
  /** The question's human text (LLM-written user data, shown as-is). */
  question: string
  options: DockOption[]
  /** Reserved anatomy (cost quote, v3) — shown muted when present. */
  estimate?: string | null
  onAnswer: (optionId: string) => void
  answering: boolean
  /** Bail affordance — the question line's × (ADR-051): for an interrupt
   * question it stops the parked run; for a plain chat ask it skips the
   * question. A graceful exit, never an error path. */
  onBail?: () => void
  /** The ×'s aria-label — the caller knows the context (stop vs skip). */
  bailLabel?: string
  /** 尾行铅笔手输入 (ADR-051): Enter submits a freeform answer through the
   * same send channel as the chat input (the deterministic letter/number/
   * label autoResume mapping resolves it server-side, zero LLM). */
  onFreeform?: (text: string) => void
  freeformDisabled?: boolean
  /** Bare child of the floating question pill (2026-09-02 拆粘): no fill /
   * rounding / margin of its own — the pill owns the chrome. */
  plain?: boolean
}

export type QuestionDockProps = TaskBookDockProps | ChoiceDockProps

const AUTONOMY_TIERS: Autonomy[] = ["auto", "review"]

function TaskBookForm({
  question,
  autonomy,
  onAutonomyChange,
  onStart,
  starting,
  startDisabled,
  estimate,
  plain,
}: TaskBookDockProps) {
  const { t } = useTranslation()
  return (
    // ONE row (2026-09-02 stadium 化): ✓ + confirm line … Start — the FLORA
    // "Save & continue" pill anatomy. Cancel retired the same day: the pill
    // is NON-blocking (the input group stays live below), so "don't start"
    // is said by simply not starting — keep chatting (chat revision always
    // wins), walk away (the plan stays honestly pending), or delete the
    // project. A negative action earns its place only when the question
    // BLOCKS the input (the choice morph's × keeps it: hidden input row +
    // bailing stops a live paid run). Single-row content is also what makes
    // the pill's rounded-full stadium correct geometry.
    <div className={plain ? "py-2 pl-4 pr-2" : "mb-2 rounded-lg bg-muted px-5 py-4"}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <Check className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="truncate text-sm font-medium">{question}</span>
          {estimate ? (
            <span className="shrink-0 text-xs text-muted-foreground">
              {estimate}
            </span>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
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
          {/* Start = the pill's single decision CTA (composer-bottom-row
              discipline: one solid anchor, h-9, px-5 presence). */}
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

function ChoiceForm({
  question,
  options,
  estimate,
  onAnswer,
  answering,
  onBail,
  bailLabel,
  onFreeform,
  freeformDisabled,
  plain,
}: ChoiceDockProps) {
  const { t } = useTranslation()
  const [freeform, setFreeform] = useState("")
  const submitFreeform = () => {
    const text = freeform.trim()
    if (!text || !onFreeform || freeformDisabled || answering) return
    onFreeform(text)
    setFreeform("")
  }
  return (
    <div className={plain ? "px-4 py-3" : "mb-2 rounded-lg bg-muted px-4 py-3"}>
      {/* Question line — no ✓ (ADR-051); the × on the right IS the bail
          channel. */}
      <div className="flex items-start gap-2 text-sm">
        <span className="min-w-0 flex-1 break-words">{question}</span>
        {estimate ? (
          <span className="shrink-0 text-xs text-muted-foreground">
            {estimate}
          </span>
        ) : null}
        {onBail ? (
          <Button
            variant="ghost"
            size="icon"
            className="-mr-1 -mt-1 h-6 w-6 shrink-0"
            aria-label={bailLabel ?? t("questionDock.bail")}
            disabled={answering}
            onClick={onBail}
          >
            <X className="size-3.5" />
          </Button>
        ) : null}
      </div>
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
          {answering ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          ) : null}
        </div>
      ) : null}
      {/* 尾行铅笔手输入 (ADR-051) — Enter submits freeform through the same
          send channel as the chat input; the server's deterministic
          letter/number/label autoResume mapping is unchanged. */}
      {onFreeform ? (
        <div className="mt-2 flex items-center gap-2.5">
          <Pencil className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <Input
            value={freeform}
            onChange={(e) => setFreeform(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                e.preventDefault()
                submitFreeform()
              }
            }}
            placeholder={t("chat.choicePlaceholder")}
            aria-label={t("chat.choicePlaceholder")}
            disabled={answering || freeformDisabled}
            className="h-8 border-0 bg-transparent px-0 text-sm shadow-none focus-visible:ring-0"
          />
        </div>
      ) : null}
    </div>
  )
}

export function QuestionDock(props: QuestionDockProps) {
  if (props.kind === "choice") return <ChoiceForm {...props} />
  return <TaskBookForm {...props} />
}
