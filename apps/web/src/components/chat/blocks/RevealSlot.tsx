import type { ReactNode } from "react"

import {
  useStructureVisibilityRegistration,
  type RegisterStructureVisibility,
} from "../structureVisibility"
import { revealOpen, shouldAnimateEntrance } from "../timeline/reveal"

/** Keeps real DTO/media loading mounted but invisible until both gates open.
 * Removing `hidden` and adding the existing motion-safe entrance in the same
 * render starts the first entrance without remounting the child. History
 * hydrates in place with no entrance animation. */
export function RevealSlot({
  ready,
  priorDrained,
  history = false,
  structureId,
  structureTurnId,
  onStructureVisible,
  children,
}: {
  ready: boolean
  priorDrained: boolean
  history?: boolean
  /** Live server identity registered only after this open DOM commit. */
  structureId?: string
  structureTurnId?: string
  onStructureVisible?: RegisterStructureVisibility
  children: ReactNode
}) {
  const open = revealOpen({ ready, priorDrained })
  useStructureVisibilityRegistration({
    open,
    history,
    serverMessageId: structureId,
    turnId: structureTurnId,
    register: onStructureVisible,
  })
  return (
    <div
      hidden={!open}
      className={
        open && shouldAnimateEntrance(history)
          ? "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 motion-safe:duration-300"
          : undefined
      }
    >
      {children}
    </div>
  )
}
