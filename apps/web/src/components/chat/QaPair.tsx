/** QaPair — the archived form of an answered question (ask primitive).
 *
 * Pending questions live in the QuestionDock above the input; once answered
 * they collapse into this Q/A double block in the message flow (Opus
 * pattern). The caller resolves both display strings (i18n) — this component
 * is pure layout.
 */

import { useTranslation } from "react-i18next"

import { Message, MessageContent } from "@/components/ui/message"

/** The typed answer payload mirrored from the API (messages.answer). */
export interface QaAnswer {
  kind: "option" | "freeform" | "bail" | "start"
  option_id?: string | null
  text?: string | null
  answered_at?: string
}

/** Resolve an answer payload to its display line. Bail variants are
 * localized (a graceful exit, never an error); freeform shows its text. */
export function qaAnswerText(
  answer: QaAnswer,
  t: (key: string) => string,
  /** The answered question carried a run (checkpoint): its bail stops the
   * run, it doesn't send the project back to draft — different copy. */
  hasRun?: boolean,
): { text: string; muted: boolean } {
  if (answer.kind === "bail") {
    if (answer.text === "superseded") {
      return { text: t("chat.qa.superseded"), muted: true }
    }
    return hasRun
      ? { text: t("chat.qa.stopped"), muted: true }
      : { text: t("chat.qa.cancelled"), muted: true }
  }
  // The checkpoint expiry sweep's auto-answer (machine marker, same pattern
  // as "superseded") — a system decision, rendered muted.
  if (answer.kind === "option" && answer.text === "expired") {
    return { text: t("chat.qa.expired"), muted: true }
  }
  // Task-book confirmation: "start" is a first-class answer kind (C1); the
  // option_id form is the phase-1 spelling, kept for pre-migration rows.
  if (
    answer.kind === "start" ||
    (answer.kind === "option" && answer.option_id === "start")
  ) {
    return { text: t("chat.qa.started"), muted: false }
  }
  return { text: answer.text || answer.option_id || "", muted: false }
}

interface QaPairProps {
  /** Human question line (already localized / user data). */
  question: string
  /** Secondary question detail (e.g. the plan summary), muted. */
  questionDetail?: string
  /** Resolved answer line. */
  answer: string
  /** Bail/supersede answers render muted — a graceful exit, not a failure. */
  muted?: boolean
}

export function QaPair({ question, questionDetail, answer, muted }: QaPairProps) {
  const { t } = useTranslation()
  return (
    <Message align="start">
      <MessageContent>
        <div className="w-full max-w-[85%] space-y-2 rounded-lg bg-muted px-3 py-2.5 text-sm motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300">
          <div className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {t("chat.qa.q")}
            </span>
            <div className="min-w-0">
              <p className="leading-relaxed text-muted-foreground">{question}</p>
              {questionDetail ? (
                <p className="mt-0.5 truncate text-xs text-muted-foreground/70">
                  {questionDetail}
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {t("chat.qa.a")}
            </span>
            <p
              className={`leading-relaxed ${
                muted ? "text-muted-foreground" : "text-foreground"
              }`}
            >
              {answer}
            </p>
          </div>
        </div>
      </MessageContent>
    </Message>
  )
}
