import { Children, type ReactNode } from "react"
import { AssistantResponse } from "./AssistantResponse"

/** The user boundary and assistant interior have separate layout owners. */
export function TurnBlock({
  user,
  turnMinimapId,
  children,
}: {
  user?: ReactNode
  turnMinimapId?: string
  children?: ReactNode
}) {
  return (
    <div
      data-slot="turn-block"
      data-turn-minimap-id={turnMinimapId}
      className="flex min-w-0 flex-col empty:hidden gap-6"
    >
      {user}
      {Children.toArray(children).length > 0 ? <AssistantResponse>{children}</AssistantResponse> : null}
    </div>
  )
}
