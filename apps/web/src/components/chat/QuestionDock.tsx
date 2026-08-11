/** QuestionDock — the pending question's home, docked above the input.
 *
 * The message list is the archive of *decided* things; the dock holds the
 * one *pending* decision (ask primitive — at most one at a time). The kind
 * selects the form (NAMING N-19: the use lives in `question.kind`, the
 * mechanism is the dock — no per-kind dock components):
 * - task_book: two rows (2026-08-06 rework) — the confirm line on the
 *   top-left, the reserved credit slot on the top-right (the week-6 cost
 *   quote rides `estimate`), the actions (Cancel / Start) on the bottom
 *   row; the needs-your-check reasons squeeze between as one compact line.
 * - choice: the question line plus its options as full-width ROWS (letter
 *   badges mirror the deterministic autoResume mapping — typing "a" picks
 *   option a); long labels wrap, never overflow the card. With `joined`
 *   the dock fuses visually with the input below — the input IS the
 *   freeform "something else" row (its placeholder already switches), so
 *   the two read as one card.
 * Answering collapses the question into a QA pair in the flow.
 */

import { Check, ChevronDown, Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
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
  /** needs_clarification reason keys — why confirmation is being asked
   * (回显: what the inference guessed). */
  reasons?: string[]
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
  /** Bail affordance — only passed for checkpoint questions (a run is
   * parked on the answer); plain chat asks get no bail (the next message
   * supersedes them anyway). A graceful exit, never an error path. */
  onBail?: () => void
  /** Fuse the dock with the input below (the input IS the freeform
   * "something else" row) — drops the bottom margin and rounding. */
  joined?: boolean
}

export type QuestionDockProps = TaskBookDockProps | ChoiceDockProps

const AUTONOMY_TIERS: Autonomy[] = ["auto", "review"]

function TaskBookForm({
  question,
  reasons,
  autonomy,
  onAutonomyChange,
  onStart,
  onCancel,
  starting,
  startDisabled,
  estimate,
}: TaskBookDockProps) {
  const { t } = useTranslation()
  const reasonLabels = (reasons ?? [])
    .map((reason) => t(`questionDock.reasons.${reason}`, { defaultValue: "" }))
    .filter(Boolean)
  return (
    <div className="mb-2 rounded-lg bg-muted px-4 py-3">
      {/* Top row: the confirm line (left) + the reserved credit slot
          (right). Copy stays one line — the plan card above carries the
          substance. */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <Check className="h-4 w-4 shrink-0 text-green-600 dark:text-green-400" />
          <span className="truncate">{question}</span>
        </div>
        {estimate ? (
          <span className="shrink-0 text-xs text-muted-foreground">
            {estimate}
          </span>
        ) : null}
      </div>
      {reasonLabels.length > 0 ? (
        <p className="mt-1.5 text-xs text-muted-foreground">
          {t("questionDock.reasons.title")} {reasonLabels.join(" · ")}
        </p>
      ) : null}
      {/* Bottom row: the actions — Cancel quiet on the left, Start solid on
          the right (the one dark anchor, composer-bottom-row discipline). */}
      <div className="mt-3 flex items-center justify-between gap-2">
        <Button
          variant="ghost"
          onClick={onCancel}
          disabled={starting}
          className="text-muted-foreground"
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
          <Button disabled={startDisabled || starting} onClick={onStart}>
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
  joined,
}: ChoiceDockProps) {
  const { t } = useTranslation()
  return (
    <div
      className={
        joined
          ? "rounded-t-lg bg-muted px-4 py-3"
          : "mb-2 rounded-lg bg-muted px-4 py-3"
      }
    >
      <div className="flex items-start gap-2 text-sm">
        <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-400" />
        <span className="min-w-0 break-words">{question}</span>
        {estimate ? (
          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
            {estimate}
          </span>
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
