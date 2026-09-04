/** QuestionDock — the pending question's home, docked above the input.
 *
 * The message list is the record of *decided* things; the dock holds the
 * one *pending* decision (提问机器 — at most one at a time). The kind
 * selects the form (NAMING N-19: the use lives in `question.kind`, the
 * mechanism is the dock — no per-kind dock components):
 * - task_book: ONE row (2026-09-02 stadium 化, ADR-051 条款 8 Ⓑ) — ✓ +
 *   the confirm line + the reserved credit slot (the week-6 cost quote
 *   rides `estimate`) + Start; Cancel retired (non-blocking pill = no
 *   negative action). No reasons line — the agent's inference bookkeeping
 *   (chain_default / clip_count_default) is not user copy; the plan card
 *   above carries the substance and the streamed echo carries the caveats.
 *   Rendered only for ≥2-task chains (任务书密度律 ADR-054 — a one-task
 *   book is pure prose; ChatDock owns the threshold).
 * - question (形态律 ADR-053 R1, 阻塞形态 2026-09-04 用户拍板翻回):
 *   while an OPTIONS question is pending the chat input row and the
 *   disclaimer HIDE — the dock IS the question (FLORA/Opus 双参照同款：两家
 *   的选项问都接管输入): the question line (the right-side × is the bail
 *   channel — the blocking state's exit), its options as full-width ROWS
 *   (letter badges mirror the deterministic autoResume mapping — typing "a"
 *   picks option a; long labels wrap, never overflow), and the tail pencil
 *   row for a freeform answer rendered as ONE MORE ITEM ROW (the pencil in
 *   the same badge tile — FLORA / Opus "Something else…" 同款解剖; Enter
 *   submits through the same send channel as the chat input — autoResume /
 *   judged settlement unchanged). No default-path subtitle line (同日拍板：
 *   两家参照均无此行——跳过语义由 × 承担，正常对话即可). 作答反馈座 = 点中
 *   的行本身（accent 填充 + 行尾 inline spinner，Opus 选中行解剖；作答失败
 *   自动复位），卡底不再另置孤 spinner（同日拍板）. The morph governs
 *   OPTIONS questions only: a text question (options-empty) is plain flow
 *   speech with the input live, and the task-book pill stays non-blocking
 *   (ADR-051 条款 8 Ⓑ).
 * Answering collapses the question into an answered-question block in the
 * flow.
 */

import { useState } from "react"
import { Check, ChevronDown, Loader2, Pencil, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
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

/** One option on a structured question (mirrors the API's Option). */
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

interface OptionDockProps {
  kind: "question"
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
  /** 尾行铅笔手输入 (ADR-053 R1 阻塞形态): Enter submits a freeform answer
   * through the same send channel as the chat input (the deterministic
   * letter/number/label autoResume mapping resolves a hit server-side,
   * zero LLM; anything else goes through the judged settlement). */
  onFreeform?: (text: string) => void
  freeformDisabled?: boolean
  /** Bare child of the floating question pill (2026-09-02 拆粘): no fill /
   * rounding / margin of its own — the pill owns the chrome. */
  plain?: boolean
}

export type QuestionDockProps = TaskBookDockProps | OptionDockProps

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
    // project. The task_book pill stays non-blocking even after the options
    // question's blocking morph returned (ADR-053 R1 翻回 2026-09-04): only
    // a BLOCKING question earns a negative action — the options question's
    // × (bail = the default path; interrupt = stops a live paid run).
    // Single-row content is also what makes the pill's rounded-full
    // stadium correct geometry.
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

function OptionForm({
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
}: OptionDockProps) {
  const { t } = useTranslation()
  const [freeform, setFreeform] = useState("")
  /** The clicked option's id — the picked row itself is the loading seat
   * (2026-09-04 用户拍板: feedback lives where the action happened — the
   * Opus selected-row anatomy — not a lone spinner at the card's bottom).
   * The highlight + inline spinner are gated on `answering`, so a failed
   * answer POST clears both honestly (nothing was picked server-side). */
  const [pickedId, setPickedId] = useState<string | null>(null)
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
              onClick={() => {
                setPickedId(option.id)
                onAnswer(option.id)
              }}
              className={cn(
                "h-auto w-full items-start justify-start gap-2.5 whitespace-normal rounded-md px-3 py-2.5 text-left hover:bg-accent",
                answering && pickedId === option.id
                  ? "bg-accent disabled:opacity-100"
                  : "bg-card"
              )}
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-muted text-[11px] font-medium uppercase text-muted-foreground">
                {option.id}
              </span>
              <span className="min-w-0 break-words">{option.label}</span>
              {answering && pickedId === option.id ? (
                <Loader2 className="ml-auto h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
              ) : null}
            </Button>
          ))}
          {/* 尾行铅笔手输入 (ADR-053 R1 阻塞形态) — the freeform channel
              while the input row is morphed away (freeform 恒在, 判词 5),
              rendered as ONE MORE ITEM ROW (2026-09-04 用户拍板, FLORA /
              Opus "Something else…" 同款解剖): the pencil sits in the same
              badge tile as the option letters, the input aligns with the
              option labels. Enter submits through the same send channel as
              the chat input — the server's deterministic letter/number/
              label autoResume mapping resolves a hit, anything else goes
              through the judged settlement. */}
          {onFreeform ? (
            <div className="flex w-full items-center gap-2.5 rounded-md bg-card px-3 py-2.5">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-muted text-muted-foreground">
                <Pencil className="h-3 w-3" />
              </span>
              {/* dark:bg-transparent is NOT redundant with bg-transparent:
                  the Input base carries bg-input/20 + dark:bg-input/30, and
                  a bare bg-transparent loses to the dark variant (the
                  variant-pairing law, same trap as hover) — without it the
                  "Something else…" field shows a filled box on the dark
                  theme (2026-09-04 用户拍板). */}
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
                className="h-5 min-w-0 flex-1 border-0 bg-transparent px-0 py-0 text-sm shadow-none focus-visible:ring-0 dark:bg-transparent"
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function QuestionDock(props: QuestionDockProps) {
  if (props.kind === "question") return <OptionForm {...props} />
  return <TaskBookForm {...props} />
}
