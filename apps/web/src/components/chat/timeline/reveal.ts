import type { OverlayMessage, VideoStoryboardBlock } from "./types"

/** Existing pending_brief.video_presentation recovery facts. This is a read
 * projection of the server's pending/authorized receipt, not a client flag. */
export interface VideoPresentationRecoveryFact {
  authorized_revision_message_id?: string | null
  presented_message_id?: string | null
  composition_version_id?: string | null
  content_digest?: string | null
  presentation_complete?: boolean
}

export function shouldAcknowledgePresentation({
  history,
  pendingPlanMessageId,
  recovery,
  messageId,
  block,
}: {
  history: boolean
  pendingPlanMessageId: string | null
  recovery?: VideoPresentationRecoveryFact | null
  messageId: string
  block: VideoStoryboardBlock
}): boolean {
  if (block.presentation_complete === true) return false
  // A live first presentation is the ordinary ACK path. History is different:
  // mounting an old card proves nothing about authorization or recovery.
  if (!history) return true
  if (!pendingPlanMessageId || !recovery?.authorized_revision_message_id) return false
  if (recovery.presentation_complete === true) return false
  const presentedMessageId = block.presented_message_id ?? messageId
  return (
    recovery.presented_message_id === pendingPlanMessageId &&
    presentedMessageId === pendingPlanMessageId &&
    recovery.composition_version_id === block.composition_version_id &&
    recovery.content_digest != null &&
    recovery.content_digest === block.content_digest
  )
}

export function presentationAckReady({
  allowed,
  dtoReady,
  prosePresented,
  previewsReady,
}: {
  allowed: boolean
  dtoReady: boolean
  prosePresented: boolean
  previewsReady: boolean
}): boolean {
  return allowed && dtoReady && prosePresented && previewsReady
}

/** A delivery's own Output slot reads only that message's display facts.
 * Another delivery, Run terminal state and Worked seals are not inputs. */
export function deliveryOutputReveal(
  message: Pick<OverlayMessage, "hydrated" | "clientVisibleAtMs" | "proseDrainedAtMs">,
): { priorDrained: boolean; history: boolean } {
  return {
    priorDrained:
      message.hydrated === true ||
      message.clientVisibleAtMs != null ||
      message.proseDrainedAtMs != null,
    history: message.hydrated === true,
  }
}

/** Only a live first entrance animates. The leaf still owns motion-safe CSS,
 * so reduced-motion behavior is unchanged. */
export function shouldAnimateEntrance(history?: boolean): boolean {
  return history !== true
}

/** Pure reveal gate: transport arrival, Run terminal state and streaming=false
 * are deliberately absent. Callers must supply domain readiness and the actual
 * preceding display boundary. Motion preference never participates. */
export function revealOpen({
  ready,
  priorDrained,
}: {
  ready: boolean
  priorDrained: boolean
}): boolean {
  return ready && priorDrained
}
