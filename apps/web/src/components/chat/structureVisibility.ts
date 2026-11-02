import { useLayoutEffect } from "react"

/** Direct registration from an actually open render path into ChatDock's ref.
 * There is no event bus or deferred React state between the DOM commit and
 * Stop's visible-frontier read. */
export type RegisterStructureVisibility = (
  serverMessageId: string,
  turnId: string,
  visible: boolean,
) => void

export function useStructureVisibilityRegistration({
  open,
  history = false,
  serverMessageId,
  turnId,
  register,
}: {
  open: boolean
  history?: boolean
  serverMessageId?: string
  turnId?: string
  register?: RegisterStructureVisibility
}) {
  useLayoutEffect(() => {
    if (!open || history || !serverMessageId || !turnId || !register) return
    register(serverMessageId, turnId, true)
    return () => register(serverMessageId, turnId, false)
  }, [open, history, serverMessageId, turnId, register])
}
