/** QuestionDock — the pending question's home, docked above the input.
 *
 * The message list is the record of *decided* things; the dock holds the
 * one *pending* decision (the ask_user machinery — at most one at a time). The kind
 * selects the form (NAMING N-19: the use lives in `question.kind`, the
 * mechanism is the dock — no per-kind dock components):
 * - task_book: RETIRED (ADR-111, 2026-10-08 — the confirm dock card
 *   family is gone: the plan's review face is the canvas's draft nodes,
 *   the total estimate rides the dock echo's code-composed tail), and the
 *   confirm gesture is the user's own words — start_run via sendChat,
 *   口头确认律 ADR-092).
 * - question (形态律 ADR-053 R1, 阻塞形态 2026-09-04 用户拍板翻回): * - question (形态律 ADR-053 R1, 阻塞形态 2026-09-04 用户拍板翻回):
 *   while an OPTIONS question is pending the chat input row and the
 *   disclaimer HIDE — the dock IS the question (FLORA/Opus 双参照同款：两家
 *   的选项问都接管输入): the question line (the right-side × is the bail
 *   channel — the blocking state's exit), its options as full-width ROWS
 *   (letter badges mirror the deterministic autoResume mapping — typing "a"
 *   picks option a; long labels wrap, never overflow), and the tail pencil
 *   row for a freeform answer rendered as ONE MORE ITEM ROW (the pencil in
 *   the same badge tile — FLORA / Opus "Something else…" 同款解剖; Enter
 *   settles through the answer endpoint — a number/letter/label hit
 *   converts pre-post to the option pick, anything else records
 *   kind="freeform"). No default-path line anywhere (ADR-103: 散文零宣告
 *   ——跳过语义由 × 承担，可见面画蛇添足用户拍板取消). 作答反馈座 = 点中
 *   的行本身（accent 填充 + 行尾 inline spinner，Opus 选中行解剖；作答失败
 *   自动复位），卡底不再另置孤 spinner（同日拍板）. The morph governs
 *   OPTIONS questions only: a text question (options-empty) is plain flow
 *   speech with the input live.
 * Answering collapses the question into an answered-question block in the
 * flow.
 */

import { useEffect, useState } from "react"
import { ArrowLeft, ArrowRight, Check, Loader2, Pencil, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import { ApprovalCard } from "@/components/ui/approval-card-clean"
import { Button } from "@/components/ui/button-clean"
import { TextField } from "@/components/ui/text-field-clean"
import { Card } from "@/components/ui/card-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import type { BriefAnswerItem, BriefQuestionItem } from "./timeline/types"

/** One option on a structured question (mirrors the API's Option). */
export interface DockOption {
  id: string
  label: string
  /** 一问拍一体化 (2026-09-27): the option's one-line reason, rendered
   * muted under the label. Absent on legacy rows / code-built options. */
  description?: string
}

interface OptionDockProps {
  kind: "question"
  mediaApproval?: boolean
  /** The question's human text (LLM-written user data, shown as-is). */
  question: string
  options: DockOption[]
  items?: BriefQuestionItem[]
  groupDigest?: string | null
  groupAnswers?: BriefAnswerItem[]
  onGroupAnswersChange?: (answers: BriefAnswerItem[]) => void
  onGroupSubmit?: (answers: BriefAnswerItem[]) => void
  /** 推荐标记 (2026-09-27 一问拍一体化): at most one option id the agent
   * recommends — its row carries the muted 推荐 suffix. */
  recommendedId?: string | null
  onAnswer: (optionId: string) => void
  answering: boolean
  /** Bail affordance — the question line's × (ADR-051): for an interrupt
   * question it stops the parked run; for a plain chat ask it skips the
   * question. A graceful exit, never an error path. */
  onBail?: () => void
  /** The ×'s aria-label — the caller knows the context (stop vs skip). */
  bailLabel?: string
  /** 尾行铅笔手输入 (ADR-053 R1 阻塞形态): Enter settles a freeform answer
   * through the ANSWER endpoint (kind="freeform") — the same settlement
   * machine as an option click; a typed letter/number/label hit converts
   * pre-post to the option pick (client mirror of the server's autoResume
   * mapping), zero LLM. */
  onFreeform?: (text: string) => void
  freeformDisabled?: boolean
  /** Bare child of the floating question pill (2026-09-02 拆粘): no fill /
   * rounding / margin of its own — the pill owns the chrome. */
  plain?: boolean
}

function OptionForm({
  question,
  mediaApproval,
  options,
  recommendedId,
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
    <div className={mediaApproval ? undefined : plain ? "p-4 sm:p-5" : "mb-2 rounded-lg bg-muted p-4 sm:p-5"}>
      {/* Question line — no ✓ (ADR-051); the × on the right IS the bail
          channel. */}
      <div className="flex items-start gap-3 text-sm leading-6">
        {mediaApproval ? (
          <ApprovalCard title={question} status="pending" submitting={answering}
            approveLabel={options.find((option) => option.id === "approve")?.label}
            declineLabel={options.find((option) => option.id === "decline")?.label}
            onDecision={(allow) => onAnswer(allow ? "approve" : "decline")}
          />
        ) : <span className="min-w-0 flex-1 break-words">{question}</span>}
        {onBail ? (
          <IconButton
            icon={<X />}
            label={bailLabel ?? t("questionDock.bail")}
            disabled={answering}
            onClick={onBail}
          />
        ) : null}
      </div>
      {options.length > 0 && (!mediaApproval || onFreeform) ? (
        // Full-width options keep long labels within the dock.
        <div className="mt-4 flex flex-col gap-1.5">
          {!mediaApproval && options.map((option, index) => (
            <Card key={option.id} selected={answering && pickedId === option.id}>
              <button
                type="button"
                disabled={answering}
                onClick={() => {
                  setPickedId(option.id)
                  onAnswer(option.id)
                }}
                className="flex w-full items-start gap-3 rounded-[inherit] p-3 text-start disabled:opacity-60"
              >
                {/* Position numbers also support typed option selection. */}
                <span className="flex size-5 shrink-0 items-center justify-center self-start text-xs tabular-nums text-meta-foreground">
                  {index + 1}
                </span>
                <span className="min-w-0 break-words leading-5">
                  {option.label}
                  {recommendedId === option.id ? (
                    <span className="ml-1.5 text-xs text-muted-foreground">
                      · {t("questionDock.recommended")}
                    </span>
                  ) : null}
                  {/* 一问拍一体化 (2026-09-27): the reason line rides UNDER the
                    label (Claude-Card parity) — muted, wrapping with the
                    row, never a second color of text. */}
                  {option.description ? (
                    <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">
                      {option.description}
                    </span>
                  ) : null}
                </span>
                {answering && pickedId === option.id ? (
                  <Loader2 className="ml-auto size-3.5 shrink-0 animate-spin text-muted-foreground" />
                ) : null}
              </button>
            </Card>
          ))}
          {/* Freeform answers share the option text alignment and submit on Enter. */}
          {onFreeform ? (
            <TextField
              prefix={<Pencil />}
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
            />
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function QuestionDock(props: OptionDockProps) {
  return props.items?.length ? <QuestionGroupForm {...props} /> : <OptionForm {...props} />
}

function QuestionGroupForm(props: OptionDockProps) {
  const { t } = useTranslation()
  const items = props.items ?? []
  const answers = props.groupAnswers ?? []
  const [page, setPage] = useState(0)
  const pageCount = items.length
  const pageIndex = Math.min(page, pageCount - 1)
  const item = items[pageIndex]
  const answer = answers.find((candidate) => candidate.slot === item.slot)

  const lastPage = pageIndex === pageCount - 1

  useEffect(() => {
    setPage(0)
  }, [props.groupDigest])

  const answered = (slot: string) => {
    const answer = answers.find((candidate) => candidate.slot === slot)
    return answer?.kind === "option" ? !!answer.option_id : !!(answer?.text ?? "").trim()
  }
  const canSubmit = items.every((item) => item.required === false || answered(item.slot))
  const updateAnswer = (slot: string, answer?: BriefAnswerItem) => {
    const next = answers.filter((candidate) => candidate.slot !== slot)
    if (answer) next.push(answer)
    props.onGroupAnswersChange?.(next)
  }
  const submit = () => {
    if (canSubmit && !props.answering) props.onGroupSubmit?.(answers)
  }

  return (
    <div
      className={props.plain ? "p-4 sm:p-5" : "mb-2 rounded-lg bg-muted p-4 sm:p-5"}
      role="group"
      aria-label={props.question}
    >
      <div className="flex items-start gap-3 text-xs leading-5 text-muted-foreground">
        <span className="min-w-0 flex-1 break-words">{props.question}</span>
        {props.onBail ? (
          <IconButton
            icon={<X />}
            label={props.bailLabel ?? t("questionDock.bail")}
            disabled={props.answering}
            onClick={props.onBail}
          />
        ) : null}
      </div>
      <div className="mt-3 flex flex-col gap-4">
        <fieldset key={item.slot} className="min-w-0">
          <legend className="mb-3 max-w-full whitespace-normal break-words text-sm font-medium leading-6 text-foreground">
            {item.question}
          </legend>
          <div className="flex flex-col gap-1.5">
            {(item.options ?? []).map((option, index) => {
              const selected = answer?.kind === "option" && answer.option_id === option.id
              return (
                <Card key={option.id} selected={selected}>
                  <button
                    type="button"
                    disabled={props.answering}
                    aria-pressed={selected}
                    onClick={() => {
                      updateAnswer(item.slot, { slot: item.slot, kind: "option", option_id: option.id })
                      if (!lastPage) setPage((current) => Math.min(pageCount - 1, current + 1))
                    }}
                    className="flex w-full items-start gap-3 rounded-[inherit] p-3 text-start disabled:opacity-60"
                  >
                    <span className="flex size-5 shrink-0 items-center justify-center self-start text-xs tabular-nums text-meta-foreground">
                      {index + 1}
                    </span>
                    <span className="min-w-0 flex-1 break-words leading-5">
                      {option.label}
                      {item.recommended_id === option.id ? (
                        <span className="ml-1.5 text-xs text-muted-foreground">
                          · {t("questionDock.recommended")}
                        </span>
                      ) : null}
                      {option.description ? (
                        <span className="mt-0.5 block text-xs leading-snug text-muted-foreground">
                          {option.description}
                        </span>
                      ) : null}
                    </span>
                    {selected ? <Check className="size-4 shrink-0 self-center" aria-hidden="true" /> : null}
                  </button>
                </Card>
              )
            })}
            {item.allow_freeform !== false ? (
              <TextField
                prefix={<Pencil />}
                value={answer?.kind === "freeform" ? (answer.text ?? "") : ""}
                onChange={(event) => {
                  const text = event.target.value
                  updateAnswer(item.slot, text ? { slot: item.slot, kind: "freeform", text } : undefined)
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                    event.preventDefault()
                    if (lastPage) submit()
                    else setPage((current) => Math.min(pageCount - 1, current + 1))
                  }
                }}
                placeholder={t("chat.choicePlaceholder")}
                aria-label={item.question}
                disabled={props.answering || props.freeformDisabled}
              />
            ) : null}
          </div>
        </fieldset>
      </div>
      <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-center gap-3 border-t border-subtle pt-3">
        <Button
          variant="ghost"
          size="sm"
          className="justify-self-start gap-1.5 px-2 text-muted-foreground hover:text-foreground"
          disabled={page === 0 || props.answering}
          onClick={() => setPage((current) => Math.max(0, current - 1))}
        >
          <ArrowLeft className="size-3.5" />
          {t("questionDock.previous")}
        </Button>
        <span className="text-xs tabular-nums text-meta-foreground" aria-live="polite">
          {t("questionDock.page", { current: pageIndex + 1, total: pageCount })}
        </span>
        {lastPage ? (
          <Button
            size="sm"
            className="justify-self-end px-4 font-normal"
            disabled={!canSubmit || props.answering}
            onClick={submit}
          >
            {props.answering ? <Loader2 className="size-3.5 animate-spin" /> : null}
            {t("questionDock.submit")}
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="justify-self-end gap-1.5 px-2 font-normal"
            disabled={props.answering}
            onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
          >
            {t("questionDock.next")}
            <ArrowRight className="size-3.5" />
          </Button>
        )}
      </div>
    </div>
  )
}
