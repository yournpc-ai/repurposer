/** QuestionDock — the pending question's home, docked above the input.
 *
 * The message list is the archive of *decided* things; the dock holds the
 * one *pending* decision (ask primitive — at most one at a time). The kind
 * selects the form (NAMING N-19: the use lives in `question.kind`, the
 * mechanism is the dock — no per-kind dock components):
 * - task_book: the plan's Start/Cancel decision plus the autonomy tier
 *   (Auto/Review), the needs-your-check reasons, and the leave note.
 * - choice: the question line plus its options as a button group (letter
 *   badges mirror the deterministic autoResume mapping — typing "a" picks
 *   option a); free text rides the input (autoResume).
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
}

interface ChoiceDockProps {
  kind: "choice"
  /** The question's human text (LLM-written user data, shown as-is). */
  question: string
  options: DockOption[]
  /** Reserved anatomy (cost quote, v3) — shown muted when present. */
  costHint?: string | null
  onAnswer: (optionId: string) => void
  answering: boolean
  /** Bail affordance — only passed for checkpoint questions (a run is
   * parked on the answer); plain chat asks get no bail (the next message
   * supersedes them anyway). A graceful exit, never an error path. */
  onBail?: () => void
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
}: TaskBookDockProps) {
  const { t } = useTranslation()
  const reasonLabels = (reasons ?? [])
    .map((reason) => t(`questionDock.reasons.${reason}`, { defaultValue: "" }))
    .filter(Boolean)
  return (
    <div className="mb-2 rounded-lg bg-muted/50 px-4 py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <Check className="h-4 w-4 shrink-0 text-green-600 dark:text-green-400" />
          <span className="truncate">{question}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
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
          <Button variant="ghost" onClick={onCancel} disabled={starting}>
            {t("common.cancel")}
          </Button>
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
      {reasonLabels.length > 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">
          {t("questionDock.reasons.title")} {reasonLabels.join(" · ")}
        </p>
      ) : null}
      <p className="mt-2 text-xs text-muted-foreground">
        {t("generationOverlay.leaveNote")}
      </p>
    </div>
  )
}

function ChoiceForm({
  question,
  options,
  costHint,
  onAnswer,
  answering,
  onBail,
}: ChoiceDockProps) {
  const { t } = useTranslation()
  return (
    <div className="mb-2 rounded-lg bg-muted/50 px-4 py-3">
      <div className="flex items-start gap-2 text-sm">
        <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-600 dark:text-green-400" />
        <span>{question}</span>
        {costHint ? (
          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
            {costHint}
          </span>
        ) : null}
      </div>
      {options.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {options.map((option) => (
            <Button
              key={option.id}
              variant="outline"
              size="sm"
              className="h-9 gap-1.5"
              disabled={answering}
              onClick={() => onAnswer(option.id)}
            >
              <span className="text-xs uppercase text-muted-foreground">
                {option.id}
              </span>
              {option.label}
            </Button>
          ))}
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
  )
}

export function QuestionDock(props: QuestionDockProps) {
  if (props.kind === "choice") return <ChoiceForm {...props} />
  return <TaskBookForm {...props} />
}
