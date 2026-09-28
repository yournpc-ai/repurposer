/** Answer-stream envelope settlement (ADR-093 §1 信封对账补全): the answer
 * SSE path's terminal-frame seam, extracted as PURE functions so the branch
 * matrix is testable (historyReplay.ts 同款先例 — ChatDock imports them
 * back, one source).
 *
 * 对账完整律: the envelope always wins = identity stamping (runId /
 * streaming reset / at re-anchor) + CONTENT TRUTH REPLACEMENT (the
 * envelope's prose replaces the preview's typed text) — both halves, one
 * discipline across every SSE settle path (sendChat's finalizePreview is
 * the parity reference). 同一不变量: the prose the typewriter paces toward
 * IS the prose the splice stamps — the preview never settles on a
 * divergent text (a stale typed text replaying against the archive is the
 * live-only double-paragraph bug class). */

import type { OverlayMessage, QuestionMessage } from "./historyReplay"

/** 信封散文真值: the follow-up row's prose truth, RAW (the DB's verbatim
 * content — trim only judges emptiness and the bare-question comparison,
 * never enters the replacement value, so the live bubble and the archive
 * replay stay byte-identical). An unsettled question row's prose is its
 * echo (content when it differs from the bare question — questionEcho's
 * semantics); a plain row's prose is its content. "" = the envelope
 * carries no prose (a code-composed bare-question row — the pill's title
 * already says it). */
export function answerEnvelopeProse(followUp: QuestionMessage): string {
  const raw = followUp.content ?? ""
  if (raw.trim() === "") return ""
  if (followUp.question && !followUp.answer) {
    const bare = (followUp.question.question ?? "").trim()
    if (raw.trim() === bare) return ""
  }
  return raw
}

/** 打字机律最后闸门 (answer 线 — sendChat's paceSettledProse /
 * paceUnstreamedTail twin): given the envelope's prose truth and what the
 * preview bubble already shows, what must still ride the typewriter BEFORE
 * the splice — the full text on a zero-delta turn, the unseen tail when
 * the envelope extends the streamed prefix (打字机律·工具线重述), nothing
 * otherwise (same-value happy path; a non-prefix flip is REPLACED speech
 * whose reconciliation is the splice itself, never a pace). */
export function planEnvelopePacing(opts: {
  envelopeProse: string
  previewStreamed: boolean
  previewText: string
}): { paceText: string } | null {
  const { envelopeProse, previewStreamed, previewText } = opts
  if (!envelopeProse) return null
  if (!previewStreamed) return { paceText: envelopeProse }
  if (
    previewText &&
    envelopeProse.length > previewText.length &&
    envelopeProse.startsWith(previewText)
  ) {
    return { paceText: envelopeProse.slice(previewText.length) }
  }
  return null
}

/** The terminal splice (Envelope wins — 原地落定, same discipline as
 * sendChat's finalizePreview): the optimistic QA block becomes the real
 * answered row AT ITS OWN INDEX (same key — never a remount) and the
 * streaming preview settles static under the SAME key with the envelope's
 * content stamped over the typed text. Both rows' absence is tolerated
 * (a zero-delta turn may never have birthed the preview bubble; a
 * task_book / text-question answer carries no QA archive row). */
export function spliceAnswerEnvelope(
  prev: OverlayMessage[],
  args: {
    optimisticId: string
    previewId: string
    answeredRow: Omit<OverlayMessage, "id"> | null
    followUp: QuestionMessage | null
  },
): OverlayMessage[] {
  const { optimisticId, previewId, answeredRow, followUp } = args
  const prose = followUp ? answerEnvelopeProse(followUp) : ""
  return prev.flatMap((m) => {
    if (m.id === optimisticId)
      // Keep the optimistic block's KEY — a fresh id unmounts the DOM node
      // and replays the entrance animation (the 2026-09-08 post-typewriter
      // QA flicker). "At its own index" means same index AND same key.
      return answeredRow ? [{ ...answeredRow, id: m.id }] : []
    if (m.id === previewId)
      return [
        {
          ...m,
          // 内容真值替换 — the parity half this seam used to miss: same-value
          // in the happy path (zero visual change); on a flip the envelope
          // wins (that IS the reconciliation). Empty prose keeps the typed
          // text (a prose-less follow-up stamps identity only).
          content: prose || m.content,
          runId: followUp?.workflow_run_id ?? m.runId,
          // Re-anchor on the server row's created_at — the preview's client
          // clock was only a stand-in (finalizePreview parity).
          at: followUp?.created_at ?? m.at,
          streaming: false,
        },
      ]
    return [m]
  })
}
