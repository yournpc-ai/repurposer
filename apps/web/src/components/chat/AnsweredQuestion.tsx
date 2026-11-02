/** AnsweredQuestion — an answered question collapsed into the message flow.
 *
 * Pending questions live in the QuestionDock above the input; once answered
 * they collapse into this question/answer double block in the message flow
 * (Opus pattern). The caller resolves both display strings (i18n) — this
 * component is pure layout.
 */

import { useTranslation } from "react-i18next"

import { Message, MessageContent } from "@/components/ui/message"
import { cn } from "@/lib/utils"
import { shouldAnimateEntrance } from "./timeline/reveal"

interface AnsweredQuestionProps {
  /** Human question line (already localized / user data). */
  question: string
  /** Secondary question detail (e.g. the plan summary), muted. */
  questionDetail?: string
  /** Resolved answer line. */
  answer: string
  /** Bail/supersede answers render muted — a graceful exit, not a failure. */
  muted?: boolean
  hydrated?: boolean
}

export function AnsweredQuestion({
  question,
  questionDetail,
  answer,
  muted,
  hydrated,
}: AnsweredQuestionProps) {
  const { t } = useTranslation()
  return (
    <Message align="end">
      <MessageContent className="items-end">
        {/* The settled choice belongs to the user's side of the transcript,
            including the question context quoted above it. The Q/A chips stay
            on the left, so the original optical padding does not mirror with
            the bubble's host alignment. */}
        <div className={cn(
          "w-fit max-w-[85%] space-y-2 rounded-lg bg-muted py-2.5 pl-3 pr-10 text-sm",
          shouldAnimateEntrance(hydrated) &&
            "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300",
        )}>
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
