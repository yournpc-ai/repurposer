/** QuestionDock — the pending question's home, docked above the input.
 *
 * Thin adapter projecting Repurposer's pending ask_user payload (single
 * option question, multi-item brief group, or media credit approval) onto
 * AffectUI Clean's DecisionCard and ApprovalCard components.
 */

import { useMemo } from "react"
import { useTranslation } from "react-i18next"

import { ApprovalCard } from "@/components/ui/approval-card-clean"
import {
  DecisionCard,
  type Decision,
  type DecisionAnswer,
  type DecisionCardLabels,
} from "@/components/ui/decision-card-clean"
import type { BriefAnswerItem, BriefQuestionItem } from "./timeline/types"

/** One option on a structured question (mirrors the API's Option). */
export interface DockOption {
  id: string
  label: string
  /** Optional one-line reason rendered muted under the label. */
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
  /** At most one option id the agent recommends. */
  recommendedId?: string | null
  onAnswer: (optionId: string) => void
  answering: boolean
  /** Bail/skip channel — the × in header or Skip in footer. */
  onBail?: () => void
  /** Accessible label for the bail/skip button. */
  bailLabel?: string
  /** Freeform answer callback for single-question mode. */
  onFreeform?: (text: string) => void
  freeformDisabled?: boolean
  /** Kept for caller compatibility; DecisionCard owns its Clean card chrome. */
  plain?: boolean
}

function useDecisionLabels(bailLabel?: string): Partial<DecisionCardLabels> {
  const { t } = useTranslation()
  return useMemo(
    () => ({
      needsYou: t("questionDock.needsYou"),
      later: t("questionDock.collapse"),
      show: t("questionDock.expand"),
      recommended: t("questionDock.recommended"),
      own: t("chat.choicePlaceholder"),
      send: t("questionDock.send"),
      previous: t("questionDock.previous"),
      next: t("questionDock.next"),
      submit: t("questionDock.submit"),
      skip: bailLabel ?? t("questionDock.skip"),
      dismiss: bailLabel ?? t("questionDock.bail"),
      waiting: (count: number) =>
        count === 1
          ? t("questionDock.waitingOne")
          : t("questionDock.waiting", { count }),
      of: (current: number, total: number) =>
        t("questionDock.page", { current, total }),
    }),
    [bailLabel, t],
  )
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
}: OptionDockProps) {
  const { t } = useTranslation()
  const labels = useDecisionLabels(bailLabel)

  const decisions = useMemo<Decision[]>(
    () => [
      {
        id: "single-question",
        question,
        allowOwn: Boolean(onFreeform) && !freeformDisabled,
        options: options.map((option) => ({
          id: option.id,
          title: option.label,
          summary: option.description,
          recommended: recommendedId === option.id,
        })),
      },
    ],
    [freeformDisabled, onFreeform, options, question, recommendedId],
  )

  if (mediaApproval) {
    return (
      <ApprovalCard
        title={question}
        status="pending"
        submitting={answering}
        approveLabel={options.find((option) => option.id === "approve")?.label}
        declineLabel={options.find((option) => option.id === "decline")?.label}
        onDecision={(allow) => onAnswer(allow ? "approve" : "decline")}
        onDismiss={onBail}
        dismissLabel={bailLabel ?? t("questionDock.bail")}
      />
    )
  }

  return (
    <DecisionCard
      decisions={decisions}
      mode="immediate"
      submitting={answering}
      onDismiss={onBail}
      labels={labels}
      onDecide={(_id, answer) => {
        if (typeof answer === "object" && answer.option) {
          onAnswer(answer.option)
        } else if (typeof answer === "object" && answer.text && onFreeform && !freeformDisabled) {
          onFreeform(answer.text)
        }
      }}
    />
  )
}

function QuestionGroupForm(props: OptionDockProps) {
  const items = props.items ?? []
  const answers = props.groupAnswers ?? []
  const labels = useDecisionLabels(props.bailLabel)

  const decisions = useMemo<Decision[]>(
    () =>
      items.map((item) => ({
        id: item.slot,
        task: props.question || undefined,
        question: item.question,
        allowOwn: item.allow_freeform !== false && !props.freeformDisabled,
        options: (item.options ?? []).map((option) => ({
          id: option.id,
          title: option.label,
          summary: option.description,
          recommended: item.recommended_id === option.id,
        })),
      })),
    [items, props.freeformDisabled, props.question],
  )

  const answerMap = useMemo<Record<string, DecisionAnswer | undefined>>(() => {
    const map: Record<string, DecisionAnswer | undefined> = {}
    for (const item of answers) {
      if (item.kind === "option" && item.option_id) {
        map[item.slot] = { option: item.option_id }
      } else if (item.kind === "freeform" && item.text) {
        map[item.slot] = { text: item.text }
      }
    }
    return map
  }, [answers])

  const answered = (slot: string) => {
    const candidate = answers.find((entry) => entry.slot === slot)
    return candidate?.kind === "option" ? !!candidate.option_id : !!(candidate?.text ?? "").trim()
  }
  const canSubmit = items.every((item) => item.required === false || answered(item.slot))

  const handleSelect = (slot: string, answer: DecisionAnswer | null) => {
    const next = answers.filter((entry) => entry.slot !== slot)
    if (answer && typeof answer === "object") {
      if (answer.option) {
        next.push({ slot, kind: "option", option_id: answer.option })
      } else if (answer.text) {
        next.push({ slot, kind: "freeform", text: answer.text })
      }
    }
    props.onGroupAnswersChange?.(next)
  }

  return (
    <DecisionCard
      decisions={decisions}
      mode="batch"
      resetKey={props.groupDigest}
      answers={answerMap}
      onSelect={handleSelect}
      onSubmitAll={() => {
        if (canSubmit && !props.answering) props.onGroupSubmit?.(answers)
      }}
      canSubmit={canSubmit}
      submitting={props.answering}
      onDismiss={props.onBail}
      labels={labels}
    />
  )
}

export function QuestionDock(props: OptionDockProps) {
  return props.items?.length ? <QuestionGroupForm {...props} /> : <OptionForm {...props} />
}
