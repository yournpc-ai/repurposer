import type { ActivityRowFrame, MessageBlock, OverlayMessage, QuestionMessage } from "./timeline/types"

type JourneyRow = Pick<QuestionMessage, "intent" | "seq">
type JourneyState = "active" | "complete" | "blocked" | "stopped"

export type JourneyMark = {
  openingId: string
  state: JourneyState
  seq: number
}

export function journeyMark(row: JourneyRow): JourneyMark | null {
  const intent = row.intent
  if (row.seq == null || !intent || typeof intent !== "object" || !("media_journey" in intent)) return null
  const mark = intent.media_journey
  if (!mark || typeof mark !== "object" || !("opening_id" in mark) || !("state" in mark)) return null
  if (typeof mark.opening_id !== "string" || !mark.opening_id) return null
  if (mark.state !== "active" && mark.state !== "complete" && mark.state !== "blocked" && mark.state !== "stopped") return null
  return { openingId: mark.opening_id, state: mark.state, seq: row.seq }
}

export function latestJourneyMark(rows: JourneyRow[], current: JourneyMark | null): JourneyMark | null {
  let latest = current
  for (const row of rows) {
    const next = journeyMark(row)
    if (!next || (latest?.openingId === next.openingId && latest.state === "stopped")) continue
    const completedInPlace = latest?.seq === next.seq && latest.openingId === next.openingId &&
      latest.state === "active" && next.state !== "active"
    if (!latest || next.seq > latest.seq || completedInPlace) latest = next
  }
  return latest
}

export function belongsToServerRow(row: OverlayMessage, id: string): boolean {
  return row.id === id || row.id === `${id}-echo` || row.serverMessageId === id ||
    row.serverIdAliases?.includes(id) === true
}

type JourneyMessage = JourneyRow & Partial<Pick<QuestionMessage, "blocks" | "content" | "answer" | "question" | "workflow_run_id" | "turn_id">>

export function preparationTool(row: JourneyMessage) {
  const state = journeyMark(row)?.state
  if ((state !== "active" && state !== "stopped") || !row.workflow_run_id ||
      row.question?.kind !== "task_book" || row.question.requires_confirmation || row.answer?.kind !== "start") return undefined
  const { tasks, suggestions, output_refs } = row.intent as {
    tasks?: { tool?: string }[]; suggestions?: unknown[]; output_refs?: unknown[]
  }
  if (suggestions?.length || output_refs?.length || row.blocks?.some((block) => block.kind !== "system_notice")) return undefined
  const tool = tasks?.[0]?.tool
  if (tasks && tasks.length > 1 && !tasks.every((task) => task.tool === "prepare_narration")) return undefined
  if (tool === "prepare_visual_assets" || tool === "prepare_narration" || tool === "prepare_music") return tool
}

export function preparationActivity(row: JourneyMessage & { created_at?: string }): ActivityRowFrame | undefined {
  const tool = preparationTool(row)
  if (!tool || !row.workflow_run_id) return undefined
  return {
    activity_id: row.workflow_run_id, kind: "run",
    status: journeyMark(row)?.state === "stopped" ? "cancelled" : "active",
    key: `chat.stepKinds.${tool}`, at: row.created_at,
  }
}

/** A public stage answer can also commit the worker to continue the same request. */
export function continuationTurnId(row: JourneyMessage, workerOpeningId?: string | null) {
  if (row.question || !row.content?.trim()) return undefined
  const type = (row.intent as { type?: string } | null)?.type
  if (type === "interim_prose" && row.turn_id === workerOpeningId) return workerOpeningId ?? undefined
  const mark = journeyMark(row)
  return type === "trigger_review" && mark?.state === "active" ? mark.openingId : undefined
}

export function mediaProgress(row: JourneyMessage): boolean {
  if (row.content?.trim()) return false
  const data = row.intent as { presentation?: string; prepared_audio?: { role?: string } } | null
  const state = journeyMark(row)?.state
  if ((state !== "active" && state !== "stopped") || row.question) return false
  return data?.presentation === "media_progress" || data?.presentation === "stage_summary" ||
    data?.prepared_audio?.role === "narration" || row.blocks?.some((b) =>
      b.kind === "audio_playback" && b.items.some((item) => item.role === "narration")) === true
}

export function chineseSceneNumber(index: number): string {
  const digits = "零一二三四五六七八九"
  if (index < 10) return digits[index]
  if (index >= 100) return String(index)
  const tens = Math.floor(index / 10)
  return (tens === 1 ? "" : digits[tens]) + "十" + (index % 10 ? digits[index % 10] : "")
}

export function sceneOrder(row: JourneyMessage): string[] | undefined {
  const order = (row.intent as { media_journey?: { scene_order?: unknown } } | null)?.media_journey?.scene_order
  return Array.isArray(order) && order.every((id) => typeof id === "string") ? order : undefined
}

export function journeyTranscriptRow<T extends JourneyMessage>(row: T): T {
  const mark = journeyMark(row)
  const blocks = row.blocks?.flatMap<MessageBlock>((block) => {
    if (row.question?.kind === "task_book" && block.kind === "system_notice") {
      // Old task books sometimes combined a version warning and a price in one notice.
      const text = block.text.trim()
      if (/^[（(]?\s*(?:估价|Estimated\s|Credits are priced when the run starts|注意：|Note:)/i.test(text)) {
        const warning = text.match(/注意：[\s\S]+?(?=开始时按上限预扣|开始后才计费)/) ??
          text.match(/note: [\s\S]+?(?=On start the high end|Billing begins only)/i)
        if (warning) return [{ ...block, text: warning[0].trim() }]
        if (/^[（(]?\s*(?:估价|Estimated\s|Credits are priced when the run starts)/i.test(text)) return []
      }
    }
    return [block]
  })
  const task = preparationTool(row)
  if (!task && blocks?.length === row.blocks?.length && !blocks?.some((block, i) => block !== row.blocks?.[i])) return row
  return { ...row, blocks, ...(task ? { content: "", turn_id: row.turn_id ?? mark?.openingId } : {}) }
}
