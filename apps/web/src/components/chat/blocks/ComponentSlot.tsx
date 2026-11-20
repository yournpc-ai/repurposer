import { useCallback, useState } from "react"

import { Message, MessageContent } from "@/components/ui/message"
import { AnchorCards } from "../AnchorCards"
import { ImagePreview } from "../video/ImagePreview"
import { AudioPlaybackSurface } from "../video/AudioPlaybackSurface"
import { StoryboardCard } from "../video/StoryboardCard"
import type { ComponentSlot as ComponentSlotFact } from "../timeline/types"
import {
  shouldAcknowledgePresentation,
  type VideoPresentationRecoveryFact,
} from "../timeline/reveal"
import { RevealSlot } from "./RevealSlot"
import type { RegisterStructureVisibility } from "../structureVisibility"

/** The only structured-slot dispatcher. Each branch adapts an existing domain
 * component; there is no model-authored component name, props wire or event
 * bus. */
export function ComponentSlot({
  slot,
  onRunStarted,
  onOpen,
  pendingPlanMessageId = null,
  presentationRecovery,
  structureId,
  structureTurnId,
  onStructureVisible,
}: {
  slot: ComponentSlotFact
  onRunStarted?: (runId: string) => void
  onOpen?: (outputId: string) => void
  pendingPlanMessageId?: string | null
  presentationRecovery?: VideoPresentationRecoveryFact | null
  structureId?: string
  structureTurnId?: string
  onStructureVisible?: RegisterStructureVisibility
}) {
  if (slot.kind === "output") {
    return (
      <RevealSlot
        ready={slot.outputs.length > 0}
        priorDrained={slot.priorDrained}
        history={slot.history}
        structureId={structureId}
        structureTurnId={structureTurnId}
        onStructureVisible={onStructureVisible}
      >
        <AnchorCards outputs={slot.outputs} onOpen={onOpen ?? (() => {})} />
      </RevealSlot>
    )
  }
  if (slot.kind === "systemNotice") {
    return (
      <Message align="start">
        <MessageContent>
          <RevealSlot
            ready
            priorDrained={slot.priorDrained}
            history={slot.history}
            structureId={structureId}
            structureTurnId={structureTurnId}
            onStructureVisible={onStructureVisible}
          >
            <p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
              {slot.block.text}
            </p>
          </RevealSlot>
        </MessageContent>
      </Message>
    )
  }
  if (slot.kind === "mediaPreview") {
    return (
      <Message align="start">
        <MessageContent>
          <RevealSlot
            ready={slot.block.kind === "image_preview" || slot.block.items.length > 0}
            priorDrained={slot.priorDrained}
            history={slot.history}
            structureId={structureId}
            structureTurnId={structureTurnId}
            onStructureVisible={onStructureVisible}
          >
            {slot.block.kind === "image_preview" ? <ImagePreview block={slot.block} /> : <AudioPlaybackSurface block={slot.block} />}
          </RevealSlot>
        </MessageContent>
      </Message>
    )
  }
  return (
    <StoryboardSlot
      slot={slot}
      onRunStarted={onRunStarted}
      pendingPlanMessageId={pendingPlanMessageId}
      presentationRecovery={presentationRecovery}
      onStructureVisible={onStructureVisible}
    />
  )
}

function StoryboardSlot({
  slot,
  onRunStarted,
  pendingPlanMessageId = null,
  presentationRecovery,
  onStructureVisible,
}: {
  slot: Extract<ComponentSlotFact, { kind: "storyboard" }>
  onRunStarted?: (runId: string) => void
  pendingPlanMessageId?: string | null
  presentationRecovery?: VideoPresentationRecoveryFact | null
  onStructureVisible?: RegisterStructureVisibility
}) {
  const versionId = slot.block.composition_version_id
  const [readyVersionId, setReadyVersionId] = useState<string | null>(null)
  const handleReady = useCallback(
    (nextReady: boolean) => setReadyVersionId(nextReady ? versionId : null),
    [versionId],
  )
  const { message } = slot
  const priorDrained = message.hydrated === true || message.proseDrainedAtMs != null
  const prosePresented = priorDrained && message.content.trim().length > 0
  const allowPresentationAck = shouldAcknowledgePresentation({
    history: message.hydrated === true,
    pendingPlanMessageId,
    recovery: presentationRecovery,
    messageId: message.id,
    block: slot.block,
  })

  return (
    <Message align="start">
      <MessageContent>
        <RevealSlot
          ready={readyVersionId === versionId}
          priorDrained={priorDrained}
          history={message.hydrated}
          structureId={message.serverMessageId}
          structureTurnId={message.turnId}
          onStructureVisible={onStructureVisible}
        >
          <StoryboardCard
            key={versionId}
            block={slot.block}
            messageId={message.id}
            prosePresented={prosePresented}
            allowPresentationAck={allowPresentationAck}
            onRunStarted={onRunStarted}
            onReady={handleReady}
          />
        </RevealSlot>
      </MessageContent>
    </Message>
  )
}
